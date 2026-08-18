"""
KRX 전종목 PER/PBR/배당수익률 CSV 검증 (Phase 5-8 CSV 임포터 방식)

================================================================================
【변경 이력】
================================================================================
【2026-08-17】최초 생성
- 배경: data.krx.co.kr의 내부 JSON API(krx_data.py)가 브라우저에서만 발급되는
  세션 쿠키(mdc.client_session=true로 추정)를 요구해서 순수 HTTP 스크립트로는
  더 이상 접근할 수 없다는 게 실측으로 확인됨(모든 요청이 HTTP 400 + "LOGOUT").
  사용자가 제안한 대안: 사람이 KRX 정보데이터시스템([12021] PER/PBR/배당수익률
  (개별종목), 조회구분=전종목)에서 CSV를 수동 다운로드해 서버 폴더에 넣으면
  프로그램이 파싱/검증/DB반영을 자동으로 처리하는 구조로 전환.
- 이 모듈은 "검증"만 담당한다(파싱/저장은 krx_importer.py). 사용자가 실수로 전날
  파일을 다시 올리거나, 화면이 바뀌어 컬럼이 달라지거나, 종목 수가 비정상적으로
  적은 경우(예: 화면 필터가 잘못 걸려 20종목만 나온 경우) 등을 잡아내는 게 목적.
- 검증 기준은 실제 사용자가 첨부한 2026-08-17자 파일 2개(KOSPI 914종목, KOSDAQ
  1802종목, data.krx.co.kr [12021] 전종목 다운로드)를 직접 열어서 확인한 실측
  컬럼 구성을 기준으로 삼았다:
    헤더: 종목코드,종목명,종가,대비,등락률,EPS,PER,BPS,PBR,주당배당금,배당수익률
    인코딩: CP949, 모든 필드 큰따옴표로 감쌈
    EPS/PER/BPS/PBR: 값이 없으면 완전히 빈 문자열(",,")로 옴 - "-"가 아님
    배당수익률: 배당이 없어도 "0.00"으로 명시 표기됨(빈 값으로 온 적 없음) -
      즉 0.00은 결측이 아니라 "배당 없음"이라는 실제 값
- 최소 종목 수 임계치(KOSPI 700 / KOSDAQ 1300)는 실측값(914/1802)보다 넉넉히
  낮게 잡았다 - 상장/상폐로 종목 수가 자연스럽게 변동해도 오탐하지 않으면서,
  화면이 잘못돼 20종목만 받아온 것 같은 명백한 사고는 잡아내기 위함.
================================================================================
"""

from dataclasses import dataclass, field
from typing import Dict, List

REQUIRED_COLUMNS = [
    "종목코드", "종목명", "종가", "대비", "등락률",
    "EPS", "PER", "BPS", "PBR", "주당배당금", "배당수익률",
]

# 실측(2026-08-17): KOSPI 914종목, KOSDAQ 1802종목. 상장폐지/신규상장으로 자연
# 변동은 있을 수 있으니 여유 있게 하한선만 둔다(상한선은 없음 - 종목이 느는 건
# 문제가 아님).
MIN_ROW_COUNT = {"KOSPI": 700, "KOSDAQ": 1300}


@dataclass
class ValidationResult:
    ok: bool
    market: str
    trade_date: str
    total_rows: int
    per_present_count: int
    pbr_present_count: int
    dividend_present_count: int
    duplicate_codes: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    def summary(self) -> str:
        lines = [
            "KRX CSV 검증 결과",
            "─" * 24,
            f"기준일       : {self.trade_date}",
            f"시장         : {self.market}",
            f"전체 종목    : {self.total_rows}",
            f"PER 정상     : {self.per_present_count}",
            f"PBR 정상     : {self.pbr_present_count}",
            f"배당 정상    : {self.dividend_present_count}",
            f"중복 종목    : {len(self.duplicate_codes)}",
            f"오류         : {len(self.errors)}",
            f"상태         : {'OK' if self.ok else 'FAIL'}",
        ]
        if self.errors:
            lines.append("")
            lines.extend(f"  - {e}" for e in self.errors)
        return "\n".join(lines)


def validate_header(header: List[str]) -> List[str]:
    """필수 컬럼이 전부 있는지 확인. 순서는 안 따진다(KRX가 순서를 바꿔도
    컬럼명 기준으로 찾아 쓰면 되므로) - 문제가 있으면 에러 메시지 리스트를
    돌려준다(없으면 빈 리스트)."""
    missing = [c for c in REQUIRED_COLUMNS if c not in header]
    if missing:
        return [f"필수 컬럼 누락: {missing} (실제 헤더: {header})"]
    return []


def validate(market: str, trade_date: str, rows: List[Dict[str, object]]) -> ValidationResult:
    """파싱된 행 목록(rows, 각 행은 symbol/per/pbr/dividend_yield 등을 담은 dict)을
    검증한다. krx_importer.parse_krx_csv()가 만들어낸 rows를 그대로 받는 걸 전제."""
    errors: List[str] = []

    total = len(rows)
    min_required = MIN_ROW_COUNT.get(market)
    if min_required is not None and total < min_required:
        errors.append(
            f"종목 수가 비정상적으로 적음: {total}건 (최소 기대치 {min_required}건) "
            f"- 화면 조회 조건이 잘못됐거나 잘못된 파일일 수 있음"
        )

    codes = [r["symbol"] for r in rows]
    seen = set()
    duplicates = []
    for c in codes:
        if c in seen:
            duplicates.append(c)
        seen.add(c)
    if duplicates:
        errors.append(f"중복 종목코드 발견: {duplicates}")

    per_present = sum(1 for r in rows if r.get("per") is not None)
    pbr_present = sum(1 for r in rows if r.get("pbr") is not None)
    dividend_present = sum(1 for r in rows if r.get("dividend_yield") is not None)

    return ValidationResult(
        ok=(len(errors) == 0),
        market=market,
        trade_date=trade_date,
        total_rows=total,
        per_present_count=per_present,
        pbr_present_count=pbr_present,
        dividend_present_count=dividend_present,
        duplicate_codes=duplicates,
        errors=errors,
    )
