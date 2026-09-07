"""
price_series - 종목별 일봉(OHLCV) 로우데이터 → 수익률/거래대금/이평선 계산 (Phase 5-14)

================================================================================
【변경 이력】
================================================================================
【2026-08-23】최초 생성
- 배경: docs/hierarchical_scoring_plan.md Phase 2. sector_analy_method.txt의
  Sector/Theme 점수 공식(모멘텀/상대강도/상승확산도/거래대금/추세안정성)이
  SectorAnalyzer/ThemeAnalyzer 양쪽에서 거의 동일하게 필요하다 - "종목 바스켓의
  가격 시계열을 받아서 바스켓 단위 점수로 집계"하는 로직을 여기 한 곳에 모으고,
  두 analyzer는 "바스켓을 어떻게 나누는지"(Sector=1:1, Theme=다대다+Primary/
  Secondary)만 각자 다르게 한다.
- 순수 계산 모듈이다(API/DB 호출 없음) - BaseAnalyzer 하위 analyzer들과 동일한
  "역할 분리" 원칙(ValuationAnalyzer 등). 입력은 항상 price_history_pipeline.py가
  DB(stock_price_history)에서 읽어 만든 평범한 dict 리스트다.
- 방법론 문서는 각 지표를 몇 점 배점하는지만 정하고, "원시 수익률/비율을 그
  배점으로 어떻게 스케일링하는지"는 구체적으로 명시하지 않았다. 아래
  scale_symmetric()/scale_ratio() 등은 이 세션이 합리적이라고 판단해 고른
  스케일링 함수이며(예: 모멘텀 ±20%를 0~30점의 양끝에 매핑), 실거래 데이터로
  분포를 확인한 뒤 조정이 필요할 수 있다 - 이 사실을 코드에 명시해 둔다.
================================================================================
"""

from typing import Any, Dict, List, Optional

# 각 구성요소가 원시값 0(중립)일 때 몇 점을 주는지, 그리고 원시값 1단위가 몇 점을
# 움직이는지를 정의한다. 방법론 문서의 배점(모멘텀30/상대강도25/확산도20/거래대금15/
# 추세안정성10)을 그대로 "만점 배점"으로 쓰고, 중립값은 항상 만점의 절반이다.
_MOMENTUM_MAX = 30.0
_MOMENTUM_NEUTRAL_SPAN_PCT = 20.0  # 모멘텀 ±20%p에서 0점/만점에 도달

_RELATIVE_MAX = 25.0
_RELATIVE_NEUTRAL_SPAN_PCT = 10.0  # 시장 대비 ±10%p 초과수익률에서 0점/만점

_BREADTH_MAX = 20.0  # 상승비율 0~100%를 그대로 0~20점에 선형 매핑

_VOLUME_MAX = 15.0
_VOLUME_NEUTRAL_RATIO_SPAN = 1.0  # 거래대금 비율 1.0(변화없음)이 중립, ±1.0에서 0점/만점 (0배~2배)

_TREND_MAX = 10.0  # MA20>MA60인 종목 비율 0~100%를 그대로 0~10점에 선형 매핑


def scale_symmetric(value: Optional[float], max_points: float, neutral_span: float) -> Optional[float]:
    """0을 중립(만점의 절반)으로 두고 좌우 대칭으로 스케일링. value가 None이면 None.

    Sector/Theme(score_basket)뿐 아니라 StockAnalyzer(Phase 3)의 종목 개별 점수
    스케일링에도 그대로 재사용한다 - 공개(public) 함수로 둔 이유.
    """
    if value is None:
        return None
    ratio = value / neutral_span if neutral_span else 0.0
    points = (max_points / 2) * (1 + ratio)
    return max(0.0, min(max_points, points))


def scale_ratio(ratio: Optional[float], max_points: float, neutral_span: float) -> Optional[float]:
    """ratio=1.0(변화 없음)을 중립으로 두고 스케일링 (거래대금 비율 전용)."""
    if ratio is None:
        return None
    return scale_symmetric(ratio - 1.0, max_points, neutral_span)


def scale_fraction(fraction: Optional[float], max_points: float) -> Optional[float]:
    """0~1 비율을 0~max_points에 선형 매핑 (확산도/추세안정성 전용)."""
    if fraction is None:
        return None
    return max(0.0, min(max_points, fraction * max_points))


def renormalize_to_100(components: Dict[str, "tuple[Optional[float], float]"]) -> float:
    """{이름: (배점만큼 스케일링된 점수 또는 None, 그 구성요소의 만점)} 딕셔너리를 받아,
    결측(None) 구성요소는 제외하고 나머지 구성요소의 만점 합계 기준으로 0~100점을
    재정규화한다 (ValuationAnalyzer의 "계산 가능한 지표만으로 재정규화" 원칙과 동일).

    구성요소의 만점 합이 정확히 100일 필요는 없다 - 어떤 가중치 배분이든 0~100으로
    환산해서 돌려준다. 전부 결측이면 중립값 50.0을 반환한다.
    """
    known = [(pts, max_pts) for pts, max_pts in components.values() if pts is not None]
    if not known:
        return 50.0
    known_max_total = sum(max_pts for _, max_pts in known)
    if known_max_total <= 0:
        return 50.0
    score = sum(pts for pts, _ in known) * (100.0 / known_max_total)
    return max(0.0, min(100.0, score))


def group_price_rows_by_ticker(rows: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """price_history 행 리스트를 ticker별로 묶고, trade_date 오름차순(과거→최신)으로 정렬한다.

    trade_date는 'YYYYMMDD' 문자열이라 문자열 정렬이 곧 날짜순 정렬이다.
    """
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        ticker = row.get("ticker")
        if not ticker:
            continue
        grouped.setdefault(ticker, []).append(row)
    for ticker_rows in grouped.values():
        ticker_rows.sort(key=lambda r: r.get("trade_date") or "")
    return grouped


def compute_ticker_metrics(sorted_rows: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """한 종목의 (오래된→최신 정렬된) 일봉 리스트에서 수익률/거래대금비율/이평선을 계산한다.

    데이터가 전혀 없으면 None. 각 지표는 계산에 필요한 일수가 부족하면 개별적으로
    None이 된다(예: 20일치밖에 없으면 return_60d/ma60은 None, 나머지는 정상 계산) -
    ValuationAnalyzer의 "결측 지표만 제외" 원칙과 동일.
    """
    closes: List[float] = []
    volumes: List[float] = []
    for r in sorted_rows:
        c = r.get("close")
        v = r.get("volume")
        if c is None:
            continue
        closes.append(float(c))
        volumes.append(float(v) if v is not None else 0.0)

    if not closes:
        return None

    def pct_return(n: int) -> Optional[float]:
        if len(closes) < n + 1:
            return None
        old = closes[-1 - n]
        if not old:
            return None
        return (closes[-1] / old - 1) * 100

    def moving_average(n: int) -> Optional[float]:
        if len(closes) < n:
            return None
        return sum(closes[-n:]) / n

    trading_values = [c * v for c, v in zip(closes, volumes)]

    def avg_trading_value(n: int) -> Optional[float]:
        if len(trading_values) < n:
            return None
        return sum(trading_values[-n:]) / n

    tv5 = avg_trading_value(5)
    tv20 = avg_trading_value(20)
    trading_value_ratio = (tv5 / tv20) if (tv5 is not None and tv20) else None

    ma20 = moving_average(20)
    ma60 = moving_average(60)

    return {
        "return_1d": pct_return(1),
        "return_5d": pct_return(5),
        "return_20d": pct_return(20),
        "return_60d": pct_return(60),
        "trading_value_ratio": trading_value_ratio,
        "ma20": ma20,
        "ma60": ma60,
        "ma20_above_ma60": (ma20 > ma60) if (ma20 is not None and ma60 is not None) else None,
        "latest_close": closes[-1],
        "data_days": len(closes),
    }


def _median(values: List[float]) -> Optional[float]:
    values = sorted(values)
    n = len(values)
    if n == 0:
        return None
    mid = n // 2
    if n % 2:
        return values[mid]
    return (values[mid - 1] + values[mid]) / 2


def compute_market_returns(
    ticker_metrics: Dict[str, Dict[str, Any]], ticker_market: Dict[str, str]
) -> Dict[str, Dict[str, Optional[float]]]:
    """시장(KOSPI/KOSDAQ)별 대표 수익률을 종목 수익률의 중앙값으로 근사한다.

    실제 KOSPI/KOSDAQ 지수 시계열이 없어도(이 analyzer는 순수 계산기라 API를
    호출하지 않는다) 같은 price_history 입력만으로 상대강도를 계산할 수 있게
    하기 위한 자체 완결적(self-sufficient) 기본값이다. 더 정확한 지수 기준
    수익률이 있으면 analyze()의 market_returns 인자로 덮어쓸 수 있다.
    """
    by_market: Dict[str, Dict[str, List[float]]] = {}
    for ticker, metrics in ticker_metrics.items():
        market = ticker_market.get(ticker)
        if not market:
            continue
        bucket = by_market.setdefault(market, {"return_5d": [], "return_20d": [], "return_60d": []})
        for key in ("return_5d", "return_20d", "return_60d"):
            value = metrics.get(key)
            if value is not None:
                bucket[key].append(value)

    return {
        market: {key: _median(values) for key, values in buckets.items()}
        for market, buckets in by_market.items()
    }


def score_basket(
    member_tickers: List[str],
    ticker_metrics: Dict[str, Dict[str, Any]],
    ticker_market: Dict[str, str],
    market_returns: Dict[str, Dict[str, Optional[float]]],
) -> Dict[str, Any]:
    """Sector 또는 Theme 하나(=종목 바스켓)의 점수를 계산한다.

    방법론 문서 구조 그대로: 모멘텀30 + 상대강도25 + 상승확산도20 + 거래대금15 +
    추세안정성10 = 100점. 각 구성요소는 계산 가능한 종목만으로 집계하고
    (결측 종목은 그 구성요소에서만 제외), data_quality로 바스켓 내 데이터 확보
    비율을 노출한다.
    """
    available = [t for t in member_tickers if t in ticker_metrics]
    member_count = len(member_tickers)
    data_quality = round(100 * len(available) / member_count, 1) if member_count else 0.0

    if not available:
        return {
            "member_count": member_count,
            "data_quality": 0.0,
            "momentum_pct": None,
            "relative_strength_pct": None,
            "breadth_ratio": None,
            "trading_value_ratio": None,
            "trend_ratio": None,
            "return_20d_pct": None,
            "score": 50.0,  # 데이터가 전혀 없으면 중립 처리 (ValuationAnalyzer 원칙과 동일)
        }

    momentum_values = []
    relative_values = []
    breadth_flags = []
    volume_ratios = []
    trend_flags = []
    return_20d_values = []

    for ticker in available:
        m = ticker_metrics[ticker]

        r5, r20, r60 = m.get("return_5d"), m.get("return_20d"), m.get("return_60d")
        if r5 is not None and r20 is not None and r60 is not None:
            momentum_values.append(r5 * 0.2 + r20 * 0.5 + r60 * 0.3)
        if r20 is not None:
            return_20d_values.append(r20)

        market = ticker_market.get(ticker)
        market_r20 = market_returns.get(market, {}).get("return_20d") if market else None
        if r20 is not None and market_r20 is not None:
            relative_values.append(r20 - market_r20)

        if m.get("return_1d") is not None:
            breadth_flags.append(m["return_1d"] > 0)

        if m.get("trading_value_ratio") is not None:
            volume_ratios.append(m["trading_value_ratio"])

        if m.get("ma20_above_ma60") is not None:
            trend_flags.append(m["ma20_above_ma60"])

    momentum_pct = _median(momentum_values) if momentum_values else None
    relative_strength_pct = _median(relative_values) if relative_values else None
    breadth_ratio = (sum(breadth_flags) / len(breadth_flags)) if breadth_flags else None
    trading_value_ratio = _median(volume_ratios) if volume_ratios else None
    trend_ratio = (sum(trend_flags) / len(trend_flags)) if trend_flags else None
    return_20d_pct = _median(return_20d_values) if return_20d_values else None

    components = {
        "momentum": (scale_symmetric(momentum_pct, _MOMENTUM_MAX, _MOMENTUM_NEUTRAL_SPAN_PCT), _MOMENTUM_MAX),
        "relative_strength": (scale_symmetric(relative_strength_pct, _RELATIVE_MAX, _RELATIVE_NEUTRAL_SPAN_PCT), _RELATIVE_MAX),
        "breadth": (scale_fraction(breadth_ratio, _BREADTH_MAX), _BREADTH_MAX),
        "volume": (scale_ratio(trading_value_ratio, _VOLUME_MAX, _VOLUME_NEUTRAL_RATIO_SPAN), _VOLUME_MAX),
        "trend": (scale_fraction(trend_ratio, _TREND_MAX), _TREND_MAX),
    }

    # 계산 가능했던 구성요소만으로 100점 만점 재정규화 (ValuationAnalyzer와 동일 원칙 -
    # 결측 구성요소를 조용히 중립으로 채우지 않고, 나머지 구성요소의 배점 비중을 키운다)
    score = renormalize_to_100(components)

    return {
        "member_count": member_count,
        "data_quality": data_quality,
        "momentum_pct": momentum_pct,
        "relative_strength_pct": relative_strength_pct,
        "breadth_ratio": breadth_ratio,
        "trading_value_ratio": trading_value_ratio,
        "trend_ratio": trend_ratio,
        # Sector/Theme 바스켓의 20일 수익률 중앙값 - StockAnalyzer(Phase 3)의
        # "Sector 내 상대강도"(종목 20일수익률 - Sector 평균 20일수익률) 계산에 쓰인다.
        "return_20d_pct": return_20d_pct,
        "component_points": {k: pts for k, (pts, _) in components.items()},
        "score": score,
    }
