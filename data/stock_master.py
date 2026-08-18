"""
StockMaster - KOSPI/KOSDAQ 전체 종목코드 마스터 (Phase 5-2)

================================================================================
【변경 이력】
================================================================================
【2026-08-15】최초 생성 (Phase 5 방향 보고서 반영, 사용자가 "KOSPI/KOSDAQ 전체 종목"
범위로 진행 결정함)

- 배경: ValuationAnalyzer의 상대평가(Phase 5-5)가 실제로 의미 있으려면, 진짜 시장
  중앙값(market_valuation.py)이 필요하고, 그러려면 KOSPI/KOSDAQ 전체 종목코드 목록이
  먼저 있어야 한다. KIS Open API는 이 목록을 REST 엔드포인트로 제공하지 않고, 공식
  마스터파일(zip)로 배포한다.

- 파싱 로직 출처: koreainvestment(한국투자증권) 공식 GitHub
  (open-trading-api/stocks_info/kis_kospi_code_mst.py,
   kis_kosdaq_code_mst.py)의 필드 폭을 그대로 따른다:
    * 한 줄 = part1(가변) + part2(고정폭 통계 영역)
    * part2 전체 길이: KOSPI 228자, KOSDAQ 222자 (시장마다 다름)
    * part1[0:9]  = 단축코드(종목코드, 6자리 + 공백 패딩)
    * part1[9:21] = 표준코드 (이 모듈에서는 사용하지 않음)
    * part1[21:]  = 한글 종목명
    * part2[0:2]  = 그룹코드/증권그룹구분코드 (두 시장 모두 첫 필드, 폭 2로 동일)
      "ST"=보통주(주권). SPAC/ETP/리츠/외국주 등은 PER/PBR 상대평가 의미가 약해
      기본적으로 제외한다 (common_stock_only=True가 기본값).

- 이 세션은 실제 네트워크로 마스터파일을 받아 검증할 수 없었다 (클라우드 샌드박스가
  해당 다운로드 도메인에 접근 가능한지 확인 못 함). 파싱 로직은 공식 샘플과 동일하게
  맞췄지만, 실제 파일로 최소 1회 실행 확인이 필요하다 (사용자 컴퓨터에서 __main__ 실행
  또는 pytest로 확인 요망).
- 자기 검증 장치: 파싱 결과가 시장당 최소 300종목 미만이면 형식이 바뀌었다고 보고
  명시적으로 예외를 던진다 (조용히 이상한 데이터를 반환하지 않기 위함).
- 캐시: 같은 날짜에 이미 받은 파일이 있으면 재사용 (전체 종목 리스트는 자주 안 바뀌고,
  다운로드+파싱 자체가 느리기 때문 - Phase 5 방향 보고서의 "재무데이터는 하루 1회 캐싱"
  원칙을 종목마스터에도 동일하게 적용).
================================================================================
"""

import os
import ssl
import json
import zipfile
import tempfile
import urllib.request
from datetime import date
from typing import Any, Dict, List, Optional

KOSPI = "KOSPI"
KOSDAQ = "KOSDAQ"

_KOSPI_MST_URL = "https://new.real.download.dws.co.kr/common/master/kospi_code.mst.zip"
_KOSDAQ_MST_URL = "https://new.real.download.dws.co.kr/common/master/kosdaq_code.mst.zip"

# part2(고정폭 통계 영역) 전체 길이 - KIS 공식 샘플 기준, 시장마다 다르다
_PART2_WIDTH = {KOSPI: 228, KOSDAQ: 222}

# 그룹코드(증권그룹구분코드)의 part2 내 시작 위치와 너비.
# 2026-08-16 실제 KOSPI 마스터파일(005930 삼성전자)로 실측 검증함:
#   part2 앞부분 30자 = ' ST1002700130000 NN5YYY YYNNNN'
# → part2[0]은 그룹코드 앞의 1자리 필드(용도 미상, 보통 공백)이고, 진짜 그룹코드
# "ST"는 part2[1:3]에 있다 (part2[0:2]가 아님). 문서상 오프셋(0)과 실제 파일이
# 1자리 어긋나 있어, 이전 버전은 그룹코드의 두 번째 글자를 잘라먹고 있었다
# (예: "ST" → "S", "EF" → "E") - 그 결과 common_stock_only 필터가 전부 걸러졌었다.
_GROUP_CODE_OFFSET = 1
_GROUP_CODE_WIDTH = 2

# 그룹코드 "ST" = 보통주(주권)
_COMMON_STOCK_GROUP_CODE = "ST"

# 시장당 최소 예상 종목 수 (이보다 적으면 파싱 실패로 간주 - 자기 검증용)
_MIN_EXPECTED_RECORDS = 300


def parse_mst_line(line: str, market: str) -> Optional[Dict[str, Any]]:
    """
    마스터파일 한 줄을 파싱. 형식이 안 맞거나 비정상 줄이면 None.

    이 함수는 네트워크 없이 순수 문자열 처리만 하므로 단위테스트로 독립 검증 가능.
    """
    part2_width = _PART2_WIDTH.get(market)
    if part2_width is None:
        raise ValueError(f"알 수 없는 시장 구분: {market}")

    line = line.rstrip("\n").rstrip("\r")
    if len(line) <= part2_width:
        return None  # 손상되었거나 빈 줄

    part1 = line[: len(line) - part2_width]
    part2 = line[-part2_width:]

    symbol = part1[0:9].strip()
    name = part1[21:].strip()
    group_code = part2[_GROUP_CODE_OFFSET:_GROUP_CODE_OFFSET + _GROUP_CODE_WIDTH].strip()

    if not symbol or not name:
        return None

    return {
        "symbol": symbol,
        "name": name,
        "market": market,
        "group_code": group_code,
    }


class StockMaster:
    """KOSPI/KOSDAQ 전체 종목코드 마스터 다운로더 + 파서 (KIS 공식 마스터파일 기반)"""

    def __init__(self, cache_dir: Optional[str] = None):
        self.cache_dir = cache_dir or os.path.join(os.getcwd(), "data", "master_cache")
        os.makedirs(self.cache_dir, exist_ok=True)

    # ---------- 공개 API ----------

    def get_stock_list(self, market: str = "ALL", common_stock_only: bool = True,
                        force_refresh: bool = False) -> List[Dict[str, Any]]:
        """
        Returns: [{"symbol": "005930", "name": "삼성전자", "market": "KOSPI",
                    "group_code": "ST"}, ...]
        """
        records: List[Dict[str, Any]] = []
        if market in ("ALL", KOSPI):
            records.extend(self._get_market_list(KOSPI, force_refresh))
        if market in ("ALL", KOSDAQ):
            records.extend(self._get_market_list(KOSDAQ, force_refresh))

        if common_stock_only:
            records = [r for r in records if r.get("group_code") == _COMMON_STOCK_GROUP_CODE]

        return records

    # ---------- 캐시 ----------

    def _cache_path(self, market: str) -> str:
        today = date.today().isoformat()
        return os.path.join(self.cache_dir, f"{market.lower()}_{today}.json")

    def _get_market_list(self, market: str, force_refresh: bool) -> List[Dict[str, Any]]:
        cache_path = self._cache_path(market)

        if not force_refresh and os.path.exists(cache_path):
            with open(cache_path, "r", encoding="utf-8") as f:
                return json.load(f)

        records = self._download_and_parse(market)

        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False)

        return records

    # ---------- 다운로드 + 파싱 ----------

    def _download_and_parse(self, market: str) -> List[Dict[str, Any]]:
        url = _KOSPI_MST_URL if market == KOSPI else _KOSDAQ_MST_URL

        with tempfile.TemporaryDirectory() as tmp_dir:
            zip_path = os.path.join(tmp_dir, "master.zip")
            self._download(url, zip_path)

            with zipfile.ZipFile(zip_path) as zf:
                zf.extractall(tmp_dir)
                mst_names = [n for n in zf.namelist() if n.lower().endswith(".mst")]

            if not mst_names:
                raise RuntimeError(f"{market} 마스터파일 압축 안에 .mst 파일이 없습니다")

            mst_path = os.path.join(tmp_dir, mst_names[0])
            return self._parse_mst_file(mst_path, market)

    @staticmethod
    def _download(url: str, dest_path: str) -> None:
        # 이 요청에 한해서만 SSL 미검증 컨텍스트 사용 (KIS 공식 샘플은
        # ssl._create_default_https_context를 전역으로 바꾸는데, 실거래 시스템 전체의
        # SSL 검증을 약화시키고 싶지 않아 요청 단위로만 적용)
        context = ssl._create_unverified_context()
        with urllib.request.urlopen(url, context=context, timeout=30) as response:
            data = response.read()
        with open(dest_path, "wb") as f:
            f.write(data)

    @staticmethod
    def _parse_mst_file(mst_path: str, market: str) -> List[Dict[str, Any]]:
        records = []
        with open(mst_path, mode="r", encoding="cp949", errors="replace") as f:
            for line in f:
                record = parse_mst_line(line, market)
                if record is not None:
                    records.append(record)

        if len(records) < _MIN_EXPECTED_RECORDS:
            raise RuntimeError(
                f"{market} 마스터파일 파싱 결과가 비정상적으로 적습니다 "
                f"({len(records)}건, 최소 {_MIN_EXPECTED_RECORDS}건 예상) - "
                f"파일 형식이 바뀌었을 수 있습니다. KIS 공식 샘플코드와 필드 폭을 다시 확인하세요."
            )

        return records


if __name__ == "__main__":
    import sys

    market_arg = sys.argv[1] if len(sys.argv) > 1 else "ALL"

    master = StockMaster()
    stocks = master.get_stock_list(market=market_arg, common_stock_only=True)

    print(f"수집된 보통주: {len(stocks)}종목")
    for market_name in (KOSPI, KOSDAQ):
        count = sum(1 for s in stocks if s["market"] == market_name)
        print(f"  {market_name}: {count}종목")

    print("\n샘플 5종목:")
    for s in stocks[:5]:
        print(f"  {s['symbol']} {s['name']} ({s['market']})")
