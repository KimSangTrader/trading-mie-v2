"""
ATR(Average True Range) 계산 (Phase 6-1)

================================================================================
【변경 이력】
================================================================================
【2026-08-25】최초 생성 (Phase 6-1)
- 업로드 문서(miev2trading.txt)가 요구하는 "20일 ATR"을 계산하는 순수 함수.
  StockPriceHistory(일봉 OHLCV)만 있으면 계산 가능 - DB/API 접근 없음(다른
  analyzers와 동일한 "순수 계산기" 원칙).
- 【설계 선택 - 문서에 명시 안 됨】ATR 평활화 방식은 두 가지가 있다: (1) 단순
  이동평균(SMA of True Range), (2) Wilder의 지수평활(전통적 터틀 트레이딩이
  실제로 쓰는 방식). 업로드 문서는 "N ≈ 20일 ATR"이라고만 하고 평활 방식을
  명시하지 않았다. 이 구현은 더 단순하고 투명한 (1) 단순 이동평균을 채택했다
  - 필요하면 나중에 Wilder 방식으로 바꿀 수 있도록 함수를 분리해뒀다.
================================================================================
"""

from typing import List, Dict, Any, Optional


def compute_true_range(high: float, low: float, prev_close: Optional[float]) -> float:
    """True Range = max(고가-저가, |고가-전일종가|, |저가-전일종가|).
    prev_close가 없으면(첫 거래일) 고가-저가만 쓴다."""
    tr = high - low
    if prev_close is not None:
        tr = max(tr, abs(high - prev_close), abs(low - prev_close))
    return tr


def compute_atr(price_rows: List[Dict[str, Any]], period: int = 20) -> Optional[float]:
    """일봉 OHLC 리스트로 ATR(단순 이동평균 방식)을 계산한다.

    Args:
        price_rows: 거래일 오름차순(과거->최근)으로 정렬된 dict 리스트, 각
            원소는 최소 "high"/"low"/"close" 키를 가져야 한다(StockPriceHistory
            레코드를 그대로 넘겨도 됨). trade_date는 정렬 기준으로만 쓰이고
            이 함수는 순서를 신뢰한다 - 호출부가 정렬해서 넘겨야 한다.
        period: ATR 기간(기본 20일, TradingConfig.atr_period와 맞출 것).

    Returns:
        ATR 값(원). 계산에 필요한 최소 데이터(period+1개, True Range 계산에
        전일 종가가 필요하므로)가 없으면 None을 돌려준다 - 다른 analyzer들과
        동일하게 "결측이면 조용히 None, 무리해서 0이나 추정값을 만들지 않는다"
        원칙을 따른다.
    """
    if not price_rows or period <= 0:
        return None

    if len(price_rows) < period + 1:
        return None

    recent = price_rows[-(period + 1):]
    true_ranges = []
    for i in range(1, len(recent)):
        high = recent[i].get("high")
        low = recent[i].get("low")
        prev_close = recent[i - 1].get("close")
        if high is None or low is None:
            continue
        true_ranges.append(compute_true_range(float(high), float(low), float(prev_close) if prev_close is not None else None))

    if len(true_ranges) < period:
        # 결측 캔들이 섞여 있어서 유효 True Range가 기간보다 적으면 계산하지 않는다
        return None

    return sum(true_ranges) / len(true_ranges)
