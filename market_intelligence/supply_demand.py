"""
supply_demand - 종목별 외국인/기관 순매수 동향 -> StockAnalyzer 수급 25점용 0~100 점수 (Phase 5-18)

================================================================================
【변경 이력】
================================================================================
【2026-08-24】최초 생성
- 배경: main.py Phase 5-17(계층형 파이프라인 실배선) 라이브 검증이 끝난 뒤 사용자가
  "순서대로" 지시한 백로그의 첫 항목 - 종목별 외국인/기관 순매수 데이터 연동.
  StockAnalyzer(market_intelligence/analyzers/stock_analyzer.py)는 이미
  data["supply_demand_score"](0~100, 정규화됨)를 받는 자리를 마련해 뒀지만
  (클래스 docstring "알려진 한계 1"), 지금까지 아무도 채워주지 않아 항상 결측
  처리(나머지 3개 컴포넌트로 재정규화)되고 있었다. 이 모듈이 그 자리를 채운다 -
  data/kis_client.py.get_investor_trend()가 조회한 원시 데이터를 0~100 점수로
  바꾸는 순수 계산기(API/DB 호출 없음, price_series.py/hierarchical_ranker.py와
  동일한 역할 분리 원칙).
- 【핵심 설계 결정 - 수량 기준, 거래대금 기준 아님】StockAnalyzer 클래스 docstring이
  이미 경고한 원칙을 그대로 따른다: "원시 순매수 금액(원)은 종목 시가총액에 따라
  스케일이 완전히 달라서, 임의의 스케일링 함수를 지어내는 것은 조용히 틀린 값을
  주는 것과 같다." 그래서 이 모듈은 "거래대금"(_tr_pbmn, 단위 불명 - kis_client.py
  변경이력 참고) 대신 "수량"(_ntby_qty, 주식 수 - 단위가 명확함)을 같은 기간의
  실제 거래량(price_rows의 volume, 역시 주식 수)에 대한 비율로 정규화한다.
  시가총액/주가 수준과 무관하게 종목 간 비교 가능한 상대 지표가 된다.
- 스케일링 폭(_SUPPLY_DEMAND_SPAN_RATIO=0.10, 즉 ±10%p)은 이 세션이 실거래
  분포를 확인하지 못한 채 고른 잠정값이다(market_intelligence/hierarchical_ranker.py의
  _MARKET_REGIME_SPAN_PCT가 처음엔 3.0으로 시작해 사용자의 실측 데이터로 6.0까지
  재조정됐던 것과 동일한 상황 - 라이브 검증 후 실제 분포를 보고 조정이 필요할 수
  있다는 걸 미리 남겨둔다).
================================================================================
"""

from typing import Any, Dict, List, Optional

from market_intelligence.price_series import scale_symmetric

_SUPPLY_DEMAND_WINDOW_DAYS = 5  # 최근 5영업일 누적으로 단일 일자 노이즈를 줄인다
_SUPPLY_DEMAND_SPAN_RATIO = 0.10  # (외국인+기관 순매수량)/거래량 비율 ±10%p에서 0점/100점 (잠정값 - 위 변경이력 참고)


def compute_supply_demand_score(
    investor_trend: Optional[Dict[str, Any]],
    price_rows: Optional[List[Dict[str, Any]]],
    window_days: int = _SUPPLY_DEMAND_WINDOW_DAYS,
) -> Optional[float]:
    """최근 window_days 영업일의 (외국인+기관) 순매수 수량 합계를, 같은 날짜의 실제
    거래량 합계에 대한 비율로 정규화해 0~100 수급 점수를 낸다.

    Args:
        investor_trend: kis_client.get_investor_trend()의 반환 형식 -
            {"dates": [...], "foreign_net_qty": [...], "institution_net_qty": [...], ...}
            (날짜 오래된 -> 최신 순 정렬).
        price_rows: 이 종목의 일봉 리스트 [{"trade_date": "YYYYMMDD", "volume": ...}, ...]
            (data/price_history_collector.chart_to_price_rows()의 반환 형식 그대로
            써도 되고, DB에서 읽은 stock_price_history 행이어도 된다 - "trade_date"/
            "volume" 키만 있으면 됨).
        window_days: 누적할 최근 영업일 수(기본 5 - 위 변경이력 참고).

    Returns:
        investor_trend/price_rows 양쪽에 공통으로 존재하는(날짜가 일치하는) 최근
        영업일이 하나도 없거나, 그 기간 거래량 합계가 0이면 None(결측 - 호출부가
        StockAnalyzer의 재정규화 로직에 맡긴다 - ValuationAnalyzer와 동일 원칙).
    """
    if not investor_trend or not price_rows:
        return None

    dates = investor_trend.get("dates") or []
    if not dates:
        return None
    foreign_qty = investor_trend.get("foreign_net_qty") or []
    institution_qty = investor_trend.get("institution_net_qty") or []

    volume_by_date: Dict[str, float] = {}
    for row in price_rows:
        trade_date = row.get("trade_date")
        volume = row.get("volume")
        if trade_date and volume is not None:
            volume_by_date[trade_date] = float(volume)

    n = min(window_days, len(dates))
    recent_indices = range(len(dates) - n, len(dates))

    net_qty_sum = 0.0
    volume_sum = 0.0
    matched_days = 0

    for i in recent_indices:
        date_val = dates[i]
        volume = volume_by_date.get(date_val)
        if volume is None or volume <= 0:
            continue  # 그 날짜의 실제 거래량을 모르면(price_rows에 없으면) 비율 계산에서 제외

        f = foreign_qty[i] if i < len(foreign_qty) else None
        o = institution_qty[i] if i < len(institution_qty) else None
        if f is None and o is None:
            continue

        net_qty_sum += (f or 0) + (o or 0)
        volume_sum += volume
        matched_days += 1

    if matched_days == 0 or volume_sum <= 0:
        return None

    ratio = net_qty_sum / volume_sum
    return scale_symmetric(ratio, 100.0, _SUPPLY_DEMAND_SPAN_RATIO)


if __name__ == "__main__":
    # Mock: 5일간 외국인+기관이 거래량의 약 8%를 꾸준히 순매수 -> 중립(50) 위 점수
    investor_trend = {
        "dates": ["20260817", "20260818", "20260819", "20260820", "20260821"],
        "foreign_net_qty": [30000, 32000, 28000, 31000, 29000],
        "institution_net_qty": [10000, 9000, 11000, 10500, 9500],
    }
    price_rows = [
        {"trade_date": d, "volume": 500000}
        for d in investor_trend["dates"]
    ]
    score = compute_supply_demand_score(investor_trend, price_rows)
    print(f"수급 점수: {score:.1f}/100 (예상: 8%/10% 폭 -> 90점 근처)")
