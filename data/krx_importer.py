"""
KRX 전종목 PER/PBR/배당수익률 CSV 임포터 (Phase 5-8 CSV 임포터 방식)

================================================================================
【변경 이력】
================================================================================
【2026-08-17】최초 생성 - data/krx_data.py(라이브 API 방식)를 대체
- 배경: data.krx.co.kr의 [12021] PER/PBR/배당수익률(개별종목, 전종목 조회) 화면을
  브라우저 개발자도구로 직접 분석한 결과, 실제 브라우저와 필드까지 동일하게
  맞춘 요청도 전부 "HTTP 400 + LOGOUT"으로 거부됨을 확인했다. 브라우저 쿠키에는
  JSESSIONID 외에 mdc.client_session=true 같은, 페이지의 자바스크립트가 별도로
  세팅하는 것으로 보이는 값이 있었고 순수 GET 워밍업으로는 이걸 얻을 수 없었다
  (requests 같은 HTTP 클라이언트로는 재현 불가한 안티봇 조치로 판단, KRX가
  2026-03-27 "시스템 개편" 즈음 추가한 것으로 추정 - data/krx_data.py 상단
  변경이력 참고). pykrx 같은 라이브러리 방식도 마찬가지로 막혔을 가능성이 큼.
- 대안(사용자 제안, 채택): 장 마감 후 사람이 KRX 화면에서 CSV를 직접 다운로드해
  data/krx/incoming/ 폴더에 넣으면, 이 모듈이 자동으로 감지·검증·정규화해서
  data/krx/latest/에 반영한다. 원본은 data/krx/archive/에 그대로(수정 없이)
  영구 보관한다 - "8월 17일 KRX 원본이 뭐였지?"를 나중에 다시 확인할 수 있도록.
- 실제 다운로드 파일 2개(KOSPI 914종목, KOSDAQ 1802종목, 2026-08-17자)를 직접
  열어서 실측한 형식: CP949 인코딩, 모든 필드 큰따옴표, 헤더는
  종목코드,종목명,종가,대비,등락률,EPS,PER,BPS,PBR,주당배당금,배당수익률.
  EPS/PER/BPS/PBR은 값이 없으면 빈 문자열(",,")로 옴("-" 아님). 배당수익률은
  배당이 없어도 "0.00"으로 명시되어 있어 빈 값으로 온 적이 없었음 - 즉
  배당수익률의 0.00은 결측이 아니라 "배당 없음"이라는 실제 값으로 그대로 둔다
  (EPS/PER/BPS/PBR의 빈 문자열만 None으로 취급).
- KRX 다운로드 파일 자체에는 시장구분(KOSPI/KOSDAQ) 컬럼이 없다 - 조회할 때
  화면에서 시장을 선택해서 받는 것이라 파일 내용만 봐서는 구분이 안 됨. 그래서
  incoming/ 폴더에 넣는 파일명 규칙으로 시장과 기준일을 명시하도록 했다:
  "kospi_YYYYMMDD.csv" / "kosdaq_YYYYMMDD.csv" (대소문자 무관, 언더스코어 위치는
  유연하게 허용 - 파일명에 kospi/kosdaq 문자열과 8자리 날짜만 들어있으면 됨).
- 안전장치: (1) krx_validator.validate()가 실패하면(종목 수 비정상적으로 적음,
  필수 컬럼 누락, 중복 종목코드 등) latest/는 절대 갱신하지 않는다(archive에는
  원본을 그대로 남겨 나중에 확인 가능하게 해둠). (2) 이미 저장된 latest보다 더
  오래된 기준일의 파일을 임포트하려 하면(예: 실수로 전날 파일을 다시 올림)
  기본적으로 거부하고, force=True를 명시해야만 덮어쓴다.
================================================================================
"""

import csv
import json
import logging
import re
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from data.krx_validator import ValidationResult, validate, validate_header

logger = logging.getLogger(__name__)

_BASE_DIR = Path(__file__).resolve().parent / "krx"
_INCOMING_DIR = _BASE_DIR / "incoming"
_ARCHIVE_DIR = _BASE_DIR / "archive"
_LATEST_DIR = _BASE_DIR / "latest"

_MARKET_PATTERNS = {"KOSPI": re.compile(r"kospi", re.IGNORECASE), "KOSDAQ": re.compile(r"kosdaq", re.IGNORECASE)}
_DATE_PATTERN = re.compile(r"(20\d{6})")  # 8자리 YYYYMMDD, 2000년대 한정으로 오탐 줄임

# 정수/실수 파싱 시 KRX 표기(콤마 포함, 예: "1,234")를 위해 콤마 제거
_NUMERIC_STRIP = str.maketrans("", "", ",")


class KrxImportError(Exception):
    """파일명에서 시장/기준일을 못 읽거나, 인코딩이 깨졌거나 하는 등 임포트
    자체를 진행할 수 없는 경우(검증 실패와는 다름 - 검증 실패는 예외를 던지지
    않고 ValidationResult.ok=False로 표현한다)."""


@dataclass
class ImportOutcome:
    validation: ValidationResult
    archived_path: Optional[str]
    latest_updated: bool
    message: str


def _parse_market_and_date(filename: str) -> Tuple[str, str]:
    market = None
    for name, pattern in _MARKET_PATTERNS.items():
        if pattern.search(filename):
            market = name
            break
    if market is None:
        raise KrxImportError(
            f"파일명에서 시장 구분을 못 찾았습니다: '{filename}' "
            f"(파일명에 kospi 또는 kosdaq 문자열이 포함되어야 합니다 - 예: kospi_20260817.csv)"
        )

    date_match = _DATE_PATTERN.search(filename)
    if not date_match:
        raise KrxImportError(
            f"파일명에서 기준일(YYYYMMDD)을 못 찾았습니다: '{filename}' "
            f"(예: kospi_20260817.csv)"
        )
    return market, date_match.group(1)


def _to_float_or_none(raw: str) -> Optional[float]:
    raw = (raw or "").strip()
    if raw == "" or raw == "-":
        return None
    try:
        return float(raw.translate(_NUMERIC_STRIP))
    except ValueError:
        return None


def parse_krx_csv(path: str) -> List[Dict[str, object]]:
    """KRX [12021] PER/PBR/배당수익률(전종목) 다운로드 CSV 하나를 읽어 행 목록으로
    변환한다. 인코딩은 CP949(엑셀 다운로드 표준) 고정 - 실제 다운로드 파일로
    확인함. EPS/PER/BPS/PBR은 빈 문자열이면 None(결측)으로, 배당수익률은
    KRX가 "배당 없음"도 "0.00"으로 명시하므로 빈 문자열이 아닌 한 그대로 float로
    취급한다(0.00을 결측으로 오인하지 않음)."""
    with open(path, encoding="cp949", newline="") as f:
        reader = csv.DictReader(f)
        header = reader.fieldnames or []
        header_errors = validate_header(header)
        if header_errors:
            raise KrxImportError(f"{path}: " + "; ".join(header_errors))

        rows = []
        for raw_row in reader:
            symbol = (raw_row.get("종목코드") or "").strip()
            if not symbol:
                continue
            rows.append({
                "symbol": symbol,
                "name": (raw_row.get("종목명") or "").strip(),
                "close": _to_float_or_none(raw_row.get("종가")),
                "eps": _to_float_or_none(raw_row.get("EPS")),
                "per": _to_float_or_none(raw_row.get("PER")),
                "bps": _to_float_or_none(raw_row.get("BPS")),
                "pbr": _to_float_or_none(raw_row.get("PBR")),
                "dps": _to_float_or_none(raw_row.get("주당배당금")),
                "dividend_yield": _to_float_or_none(raw_row.get("배당수익률")),
            })
        return rows


def _latest_path(market: str, base_dir: Path) -> Path:
    return base_dir / "latest" / f"{market.lower()}.json"


def _archive_path(market: str, trade_date: str, base_dir: Path) -> Path:
    return base_dir / "archive" / f"{market.lower()}_{trade_date}.csv"


def import_file(
    path: str,
    base_dir: Optional[Path] = None,
    force: bool = False,
) -> ImportOutcome:
    """CSV 파일 하나를 검증하고 latest/에 반영한다. base_dir을 안 넘기면
    data/krx/ 를 쓴다(테스트에서는 임시 디렉터리를 넘겨서 실제 데이터 폴더를
    건드리지 않게 한다)."""
    base_dir = base_dir or _BASE_DIR
    (base_dir / "archive").mkdir(parents=True, exist_ok=True)
    (base_dir / "latest").mkdir(parents=True, exist_ok=True)

    filename = Path(path).name
    market, trade_date = _parse_market_and_date(filename)

    rows = parse_krx_csv(path)
    result = validate(market, trade_date, rows)

    archive_dest = _archive_path(market, trade_date, base_dir)
    shutil.copyfile(path, archive_dest)

    if not result.ok:
        logger.warning(f"⚠️  {market} {trade_date} 검증 실패 - latest는 갱신하지 않음\n{result.summary()}")
        return ImportOutcome(
            validation=result,
            archived_path=str(archive_dest),
            latest_updated=False,
            message="검증 실패 - 원본은 archive에 보관했으나 latest는 갱신하지 않았습니다.",
        )

    latest_dest = _latest_path(market, base_dir)
    if latest_dest.exists() and not force:
        try:
            existing = json.loads(latest_dest.read_text(encoding="utf-8"))
            existing_date = existing.get("trade_date", "")
            if existing_date and existing_date > trade_date:
                msg = (
                    f"현재 latest의 기준일({existing_date})이 임포트하려는 파일의 "
                    f"기준일({trade_date})보다 최신입니다 - 예전 파일을 실수로 다시 "
                    f"올리신 게 아닌지 확인해주세요. 의도적이라면 force=True로 다시 "
                    f"실행하세요."
                )
                logger.warning(f"⚠️  {msg}")
                return ImportOutcome(
                    validation=result,
                    archived_path=str(archive_dest),
                    latest_updated=False,
                    message=msg,
                )
        except (json.JSONDecodeError, OSError):
            pass  # latest 파일이 깨져있으면 그냥 새로 씀

    payload = {
        "market": market,
        "trade_date": trade_date,
        "imported_at": datetime.now().isoformat(),
        "source_file": filename,
        "rows": {r["symbol"]: r for r in rows},
    }
    latest_dest.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    logger.info(f"✅ {market} {trade_date} 임포트 완료 - {result.total_rows}종목, latest 갱신됨")
    return ImportOutcome(
        validation=result,
        archived_path=str(archive_dest),
        latest_updated=True,
        message=f"임포트 완료 ({result.total_rows}종목)",
    )


def scan_incoming(base_dir: Optional[Path] = None) -> List[ImportOutcome]:
    """incoming/ 폴더의 모든 CSV를 임포트한다. 성공/실패와 무관하게 처리한
    파일은 incoming/에서 지운다(원본은 어차피 archive/에 복사돼 있으므로) -
    단, 파일명 규칙 자체를 못 읽어서 KrxImportError가 나는 경우는 incoming/에
    그대로 남겨서 사용자가 파일명을 고칠 수 있게 한다."""
    base_dir = base_dir or _BASE_DIR
    incoming = base_dir / "incoming"
    incoming.mkdir(parents=True, exist_ok=True)

    outcomes = []
    for path in sorted(incoming.glob("*.csv")):
        try:
            outcome = import_file(str(path), base_dir=base_dir)
            outcomes.append(outcome)
            path.unlink()
        except KrxImportError as e:
            logger.warning(f"⚠️  {path.name} 건너뜀 - {e}")
    return outcomes


def get_dividend_yields(market: str, base_dir: Optional[Path] = None) -> Dict[str, float]:
    """valuation_collector.py의 dividend_fetcher 인터페이스와 동일한 시그니처
    (market: str) -> {종목코드: 배당수익률(%)}. data/krx_data.py(라이브 API)가
    쓰던 것과 같은 인터페이스라 그냥 교체해 끼우면 된다. latest/에 아직 아무것도
    임포트된 적이 없으면 빈 딕셔너리를 돌려준다(파이프라인이 깨지지 않게)."""
    base_dir = base_dir or _BASE_DIR
    path = _latest_path(market, base_dir)
    if not path.exists():
        logger.warning(f"⚠️  {market} latest 배당 데이터가 아직 없음 - CSV를 한 번도 임포트하지 않은 것으로 보임")
        return {}

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        logger.warning(f"⚠️  {market} latest 파일을 읽는 중 오류 - {e}")
        return {}

    trade_date = payload.get("trade_date", "?")
    logger.info(f"💰 {market} 배당수익률 - CSV 임포트 데이터 사용 (기준일 {trade_date})")

    result = {}
    for symbol, row in payload.get("rows", {}).items():
        yield_value = row.get("dividend_yield")
        if yield_value is not None:
            result[symbol] = yield_value
    return result


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")

    if len(sys.argv) > 1:
        outcome = import_file(sys.argv[1])
        print(outcome.validation.summary())
        print(f"\n{outcome.message}")
    else:
        results = scan_incoming()
        if not results:
            print("incoming/ 폴더에 처리할 CSV가 없습니다.")
        for r in results:
            print(r.validation.summary())
            print(f"{r.message}\n")
