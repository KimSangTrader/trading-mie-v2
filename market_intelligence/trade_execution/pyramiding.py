"""
추가매수(피라미딩) 및 손절 판정 (Phase 6-1)

================================================================================
【변경 이력】
================================================================================
【2026-08-25】최초 생성 (Phase 6-1) - 업로드 문서(miev2trading.txt) §9~§11,
§18의 should_add_position()/PositionManager를 그대로 옮김.

핵심 원칙(문서 그대로, 임의로 바꾸지 않음):
  - 손실 중인 종목에는 절대 추가매수하지 않는다("물타기 금지" - 처음 분석이
    틀렸다는 신호가 나오는데 돈을 더 넣지 않는다는 게 문서의 명시적 철학).
  - 추가매수는 "가격이 마지막 매수가 + 1 ATR 이상 올랐을 때"만, 그리고
    동시에 "계층형 랭킹이 여전히 30위 이내"이고 "Sector/Theme 점수가 여전히
    강할 때"만 허용한다 - 세 조건 다 만족해야 함(AND).
  - 최대 3회(1차+추가 2회)까지만 진입.

【미확정 - 다음 단계에서 사용자 확인 필요, config.py 상단 changelog에도
동일하게 적어둠】check_stop()은 문서에 명시된 "손절가 도달" 조건만 구현했다.
문서가 언급만 하고 정확한 수치를 안 준 "추세 이탈 시 전량/단계적 청산"
(랭킹이 크게 나빠졌을 때 손절가 도달 전이라도 전량 매도하는 규칙)은
아직 없다 - 지금은 손절가에 닿기 전까지는 계속 보유한다.
================================================================================
"""

from typing import Dict, Any, Tuple

from market_intelligence.trade_execution.config import TradingConfig, DEFAULT_CONFIG


def should_add(
    position: Dict[str, Any],
    candidate: Dict[str, Any],
    config: TradingConfig = DEFAULT_CONFIG,
) -> Tuple[str, str]:
    """이미 보유 중인 포지션에 추가매수(피라미딩)할지 판정한다.

    Args:
        position: {"average_price", "last_entry_price", "entry_count"} 필요.
        candidate: {"current_price", "atr20", "current_rank", "sector_score",
            "theme_score"} 필요.
        config: TradingConfig.

    Returns:
        (action, reason). action: "ADD" | "HOLD"
    """
    if position.get("entry_count", 0) >= config.max_entries:
        return "HOLD", "MAX_ENTRIES_REACHED"

    current_price = candidate.get("current_price")
    average_price = position.get("average_price")
    if current_price is None or average_price is None:
        return "HOLD", "MISSING_PRICE_DATA"

    # 물타기 금지 - 평균단가 이하에서는 절대 추가매수하지 않는다
    if current_price <= average_price:
        return "HOLD", "LOSING_POSITION"

    atr20 = candidate.get("atr20")
    last_entry_price = position.get("last_entry_price")
    if atr20 is None or atr20 <= 0 or last_entry_price is None:
        return "HOLD", "MISSING_ATR_OR_ENTRY_PRICE"

    add_trigger = last_entry_price + atr20 * config.pyramid_atr_multiple
    if current_price < add_trigger:
        return "HOLD", "ATR_TARGET_NOT_REACHED"

    current_rank = candidate.get("current_rank")
    if current_rank is None or current_rank > config.max_rank_for_add:
        return "HOLD", "RANK_WEAKENED"

    sector_score = candidate.get("sector_score")
    if sector_score is None or sector_score < config.min_sector_score:
        return "HOLD", "SECTOR_WEAKENED"

    theme_score = candidate.get("theme_score")
    if theme_score is None or theme_score < config.min_theme_score:
        return "HOLD", "THEME_WEAKENED"

    return "ADD", "PYRAMID_APPROVED"


def check_stop(position: Dict[str, Any], current_price: float) -> Tuple[str, str]:
    """손절가 도달 여부만 확인한다(그 외 청산 규칙은 아직 없음 - 위 모듈
    docstring 참고).

    Returns:
        (action, reason). action: "STOP_LOSS" | "HOLD"
    """
    stop_price = position.get("stop_price")
    if stop_price is None or current_price is None:
        return "HOLD", "MISSING_STOP_OR_PRICE"

    if current_price <= stop_price:
        return "STOP_LOSS", "STOP_PRICE_HIT"

    return "HOLD", "ABOVE_STOP"
