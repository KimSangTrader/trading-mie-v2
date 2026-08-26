"""
1차 진입 필터 (Phase 6-1)

================================================================================
【변경 이력】
================================================================================
【2026-08-25】최초 생성 (Phase 6-1) - 업로드 문서(miev2trading.txt) §18의
TradeExecutionAnalyzer.check_entry()를 그대로 옮기되, 갭 판정은 문서의
5단계 표(gap_filter.classify_gap)를 그대로 쓰도록 연결했다(문서 코드
예시 자체는 7% 단일 컷오프였지만, 문서 본문 §4의 5단계 표가 더 상세하고
§19 "최종 규칙"도 5단계와 일관되므로 5단계 쪽을 채택 - 코드 예시의 단순
버전은 앞부분 설명용 축약이었던 것으로 판단).

check_entry()가 돌려주는 gap 판정별 의미:
  - "NORMAL_ENTRY": 정상 진입
  - "REDUCE_POSITION": 진입은 하되 이후 포지션 사이징 단계에서 비중을
    줄여야 함(이 함수는 판정만 하고 실제 축소는 호출부/포지션사이저 몫)
  - "WAIT" / "WAIT_CONFIRMATION": 오늘은 진입하지 않고 다음 기회(또는
    시간 경과 후 재평가)로 미룸
  - "NO_ENTRY": 이 종목은 오늘 후보에서 완전히 제외
================================================================================
"""

from typing import Dict, Any, Tuple

from market_intelligence.trade_execution.config import TradingConfig, DEFAULT_CONFIG
from market_intelligence.trade_execution.gap_filter import classify_gap, compute_gap_pct


def check_entry(candidate: Dict[str, Any], config: TradingConfig = DEFAULT_CONFIG) -> Tuple[str, str]:
    """다음날 실제 매수 전, 전일 계층형 랭킹 후보를 실시간 조건으로 재검증한다.

    Args:
        candidate: 최소 다음 키를 가져야 한다.
            "previous_close", "current_price"(또는 당일 시가),
            "final_score", "sector_score", "theme_score", "atr20"
        config: TradingConfig.

    Returns:
        (action, reason) 튜플.
        action: "BUY" | "REDUCE" | "WAIT" | "NO_ENTRY"
        reason: 사유 코드(로그/기록용).
    """
    previous_close = candidate.get("previous_close")
    current_price = candidate.get("current_price")
    if not previous_close or not current_price:
        return "WAIT", "MISSING_PRICE_DATA"

    gap_pct = compute_gap_pct(current_price, previous_close)
    gap_action = classify_gap(gap_pct)

    if gap_action == "NO_ENTRY":
        return "NO_ENTRY", "GAP_TOO_HIGH"
    if gap_action in ("WAIT", "WAIT_CONFIRMATION"):
        return "WAIT", f"GAP_{gap_action}"

    final_score = candidate.get("final_score")
    if final_score is None or final_score < config.min_final_score:
        return "WAIT", "LOW_FINAL_SCORE"

    sector_score = candidate.get("sector_score")
    if sector_score is None or sector_score < config.min_sector_score:
        return "WAIT", "WEAK_SECTOR"

    theme_score = candidate.get("theme_score")
    if theme_score is None or theme_score < config.min_theme_score:
        return "WAIT", "WEAK_THEME"

    atr20 = candidate.get("atr20")
    if atr20 is None or atr20 <= 0:
        return "WAIT", "INVALID_ATR"

    if gap_action == "REDUCE_POSITION":
        return "REDUCE", "GAP_REDUCE_POSITION"

    return "BUY", "ENTRY_APPROVED"
