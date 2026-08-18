"""
KRX 정보데이터시스템(data.krx.co.kr) 배당수익률 일괄 조회 (Phase 5-8)

================================================================================
【변경 이력】
================================================================================
【2026-08-17】기준일 자동 보정 추가 (주말/공휴일 HTTP 400 대응)
- 최초 버전(아래 "최초 생성" 항목)을 사용자 컴퓨터에서 실행(python -m data.krx_data
  KOSPI)한 결과 HTTP 400으로 실패함. 원인 조사: 로그에 찍힌 기준일 20260816은
  2026-08-16(일요일)이었음 - KRX 정보데이터시스템은 비영업일(주말/공휴일)에는 해당
  bld의 통계를 아예 생성하지 않아 400을 돌려주는 것으로 보임(서버가 명시적으로
  "휴장일" 같은 메시지를 주는 게 아니라 그냥 400).
- pykrx(sharebook-kr/pykrx)의 get_nearest_business_day_in_a_week를 참고했는데,
  이 함수도 로컬 공휴일 캘린더를 갖고 있지 않고 "서버에 물어봐서 데이터가 있으면
  영업일"이라는 방식으로 판정한다(지수 시세를 넓은 기간으로 조회해서 실제로 돌아온
  마지막 날짜를 씀). 즉 정적인 공휴일 목록을 유지하는 게 아니라 서버 응답 자체를
  신뢰의 기준으로 삼는 게 이 생태계의 검증된 방식이라 그대로 따름.
- 수정: trade_date를 명시하지 않으면 어제부터 시작해 주말은 건너뛰고, 하루씩
  뒤로 가며 최대 _MAX_LOOKBACK_DAYS(10)일까지 순차 요청 - 응답이 200이 아니거나
  output이 비어있으면 실패로 보고 하루 더 뒤로 감. 추석/설 연휴(최대 5일 연휴)도
  커버하도록 10일로 넉넉히 잡음. trade_date를 명시적으로 넘긴 경우는 사용자 의도를
  존중해 그 날짜 1회만 시도(자동 보정 안 함).
- (참고) 사용자가 "최근 KRX가 세션 쿠키/OTP 인증을 요구하도록 보안을 강화했을 수
  있다"는 가설도 제시했으나, pykrx의 Post 클래스(활발히 유지보수 중이고 지금도
  동작하는 라이브러리) 소스를 직접 확인한 결과 세션 예열이나 OTP 없이 단순 POST 1회로
  동작하고 있어 이 가설의 근거는 약하다고 판단, 우선 날짜 문제부터 고침. 날짜를
  고쳐도 여전히 400이면 그때 세션/쿠키 쪽을 재조사할 것.

【2026-08-17】최초 생성
- 배경: 종목별 배당수익률을 KIS Open API로 확보하려고 두 가지를 시도했으나 모두
  부적합했다.
    1) get_stock_fundamental (inquire-price): 애초에 배당수익률 필드가 없음.
    2) get_dividend_rates (배당률 상위 랭킹 API, tr_id HHKDB13470100): 실제로
       불러보니 (a) 시장당 20종목까지만 반환(랭킹/순위 API라 상위권만 줌 - 전체
       종목 커버 불가), (b) divi_rate 필드가 "배당수익률(%)"이 아니라 "액면배당률"
       (액면가 대비 배당금 비율, 종목마다 액면가가 달라 상대비교 불가)이었음
       - 삼성화재해상보험1우 사례로 실측 확인: per_sto_divi_amt(배당금)=19505원,
         divi_rate=3901.00 → 19505/500(액면가)*100=3901.0로 정확히 일치.
       → 이 방식은 폐기 (kis_client.py의 get_dividend_rates 제거).
  사용자가 첨부한 "한국거래소를 이용한 배당율조회와 실시간 조회 연동방법.docx"가
  대안을 제시함: 종목 수천 개를 API로 순회하지 말고, KRX 정보데이터시스템에서
  전종목 배당 지표를 한 번에 벌크로 받아온 뒤(정적/일 단위 데이터), 실시간이
  필요한 부분만 KIS Open API로 보완하라는 것.
- 이 모듈은 KIS Open API와 완전히 무관한 별도의 공개 데이터 소스다(인증/앱키 불필요).
  data.krx.co.kr가 자체 웹페이지(PER/PBR/배당수익률 화면)에서 쓰는 내부 JSON API를
  그대로 호출한다. 이 엔드포인트/파라미터는 국내에서 널리 쓰이는 오픈소스 라이브러리
  pykrx(sharebook-kr/pykrx)의 PER_PBR_배당수익률_전종목 클래스를 참고해서 그대로
  이식했다(공식 문서가 아니라 리버스엔지니어링된 내부 API라, pykrx처럼 이미 널리
  검증된 구현을 따르는 게 임의로 KRX API를 추측하는 것보다 안전하다고 판단함).
- 이 세션은 실제로 호출해서 검증할 수 없었다(클라우드 샌드박스 네트워크 제약).
  사용자 컴퓨터에서 라이브 검증 필요 - 특히 응답 필드명(ISU_SRT_CD, DVD_YLD)과
  날짜/휴장일 처리가 실제로 맞는지 확인해야 한다.
================================================================================
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Optional

import requests

logger = logging.getLogger(__name__)

_KRX_URL = "https://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd"
_BLD_PER_PBR_DIV = "dbms/MDC/STAT/standard/MDCSTAT03501"  # PER/PBR/배당수익률 전종목 (pykrx 기준)

_MARKET_ID = {"KOSPI": "STK", "KOSDAQ": "KSQ"}

_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer": "https://data.krx.co.kr/contents/MDC/MDI/outerLoader/index.cmd",
    "X-Requested-With": "XMLHttpRequest",
}

# 추석/설 연휴 등 최대 5일 연속 휴장에도 여유 있게 대응하기 위해 10일까지 뒤로 감
_MAX_LOOKBACK_DAYS = 10


def _candidate_trade_dates(max_lookback_days: int = _MAX_LOOKBACK_DAYS):
    """어제부터 하루씩 거슬러 올라가며 영업일 후보 날짜를 순서대로 내놓는 제너레이터.
    주말(토/일)은 애초에 API를 부르지 않고 건너뛴다 - 공휴일까지는 로컬에서 판별할
    방법이 없으므로(하드코딩된 공휴일 캘린더 없음), 그건 호출부가 실제 응답으로
    판정한다(pykrx의 get_nearest_business_day_in_a_week와 동일한 사상: 서버가
    데이터를 주면 영업일, 안 주면 다음 후보로)."""
    d = datetime.now() - timedelta(days=1)
    yielded = 0
    while yielded < max_lookback_days:
        if d.weekday() < 5:  # 0=월 ... 4=금, 5=토 6=일
            yield d.strftime("%Y%m%d")
            yielded += 1
        d -= timedelta(days=1)


def _fetch_one(market: str, trade_date: str) -> Optional[Dict[str, float]]:
    """지정한 하루치를 조회한다. 성공(응답 200 + 종목 1개 이상)하면 딕셔너리를,
    비영업일 등으로 실패(HTTP 400 등)하거나 결과가 비어 있으면 None을 돌려준다."""
    params = {
        "bld": _BLD_PER_PBR_DIV,
        "trdDd": trade_date,
        "mktId": _MARKET_ID[market],
    }
    response = requests.post(_KRX_URL, data=params, headers=_HEADERS, timeout=30)

    if response.status_code != 200:
        logger.info(f"   ({trade_date}은 조회 실패/비영업일로 보임: HTTP {response.status_code})")
        return None

    data = response.json()
    rows = data.get("output", [])
    if not rows:
        logger.info(f"   ({trade_date}은 결과 없음 - 비영업일로 보임)")
        return None

    result: Dict[str, float] = {}
    for row in rows:
        symbol = str(row.get("ISU_SRT_CD", "")).strip()
        rate = row.get("DVD_YLD")
        if not symbol or rate in (None, "", "-"):
            continue
        try:
            # KRX 응답 숫자 필드는 천단위 콤마가 섞인 문자열일 수 있음
            result[symbol] = float(str(rate).replace(",", ""))
        except (TypeError, ValueError):
            continue
    return result


def get_dividend_yields(market: str, trade_date: Optional[str] = None) -> Dict[str, float]:
    """
    KRX 정보데이터시스템에서 시장 전체 배당수익률을 한 번에(시장당 1회) 조회한다.

    Args:
        market: "KOSPI" 또는 "KOSDAQ"
        trade_date: "YYYYMMDD" 형식 기준일. None이면 어제부터 거슬러 올라가며
            (주말 제외, 최대 _MAX_LOOKBACK_DAYS일) 실제로 데이터가 있는 가장 최근
            영업일을 자동으로 찾는다. 명시적으로 넘기면 그 날짜 1회만 시도한다
            (호출자가 특정 날짜를 원한 것으로 보고 임의로 다른 날짜로 대체하지 않음).

    Returns:
        {"005930": 2.15, "000660": 1.10, ...} 형태의 {종목코드: 배당수익률(%)} 딕셔너리.
        조회 실패/데이터 없음(휴장일 연속 등으로 lookback 범위 내에 못 찾음) 시
        빈 딕셔너리 - 호출부는 병합할 데이터가 없다고 보고 그대로 진행한다(기존
        KIS PER/PBR 수집 결과에는 영향 없음).
    """
    if market not in _MARKET_ID:
        raise ValueError(f"알 수 없는 시장 구분: {market}")

    candidates = [trade_date] if trade_date else list(_candidate_trade_dates())

    # 후보 날짜 하나하나를 개별적으로 시도한다 - 특정 날짜에서 네트워크 오류가 나도
    # (비영업일이라 400이 나는 것과 구분 없이) 다음 후보로 계속 진행해야 하므로,
    # try/except를 루프 밖이 아니라 안쪽에 둔다(밖에 두면 첫 후보에서 예외가 나는
    # 순간 나머지 후보를 아예 시도조차 못 하고 끝나버림).
    for candidate in candidates:
        logger.info(f"💰 {market} KRX 배당수익률 일괄 조회 중 (기준일 {candidate})...")
        try:
            result = _fetch_one(market, candidate)
        except Exception as e:
            logger.info(f"   ({candidate} 조회 중 오류 - {e}, 다음 후보로 진행)")
            continue
        if result:
            logger.info(f"   ✅ {market} 배당수익률 {len(result)}종목 확보 (기준일 {candidate})")
            return result

    logger.warning(
        f"⚠️  {market} KRX 배당수익률 조회 실패 - 후보 날짜 {len(candidates)}개 모두 데이터 없음"
    )
    return {}


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")

    market_arg = sys.argv[1] if len(sys.argv) > 1 else "KOSPI"
    date_arg = sys.argv[2] if len(sys.argv) > 2 else None

    rates = get_dividend_yields(market_arg, date_arg)
    print(f"\n총 {len(rates)}종목")
    for symbol, rate in list(rates.items())[:10]:
        print(f"  {symbol}: {rate}%")
