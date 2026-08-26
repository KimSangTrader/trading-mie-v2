"""
시초가 갭 필터 (Phase 6-1)

================================================================================
【변경 이력】
================================================================================
【2026-08-25】최초 생성 (Phase 6-1) - 업로드 문서(miev2trading.txt) §4 그대로 구현.
- 전일 종가 대비 당일 시가 갭을 5단계로 판정한다. config.GAP_BANDS에 판정
  경계값을 두고, 이 모듈은 그 경계값을 그대로 적용하는 순수 함수만 제공한다
  (경계값을 바꾸고 싶으면 config.py만 고치면 됨).
================================================================================
"""

from typing import Optional
from market_intelligence.trade_execution.config import GAP_BANDS


def compute_gap_pct(today_open: float, previous_close: float) -> float:
    """갭(%) = (당일 시가 - 전일 종가) / 전일 종가 * 100."""
    if previous_close == 0:
        raise ValueError("previous_close가 0입니다 - 갭을 계산할 수 없습니다.")
    return (today_open - previous_close) / previous_close * 100.0


def classify_gap(gap_pct: float) -> str:
    """갭(%)을 5단계 중 하나로 판정한다.

    Returns:
        "WAIT" | "NORMAL_ENTRY" | "WAIT_CONFIRMATION" | "REDUCE_POSITION" | "NO_ENTRY"
    """
    for lower, upper, label in GAP_BANDS:
        if lower is not None and gap_pct <= lower:
            continue
        if upper is not None and gap_pct > upper:
            continue
        return label
    # 이론상 GAP_BANDS가 -inf~+inf를 전부 커버하므로 여기 도달하면 안 되지만,
    # 방어적으로 가장 보수적인 판정(WAIT)을 돌려준다.
    return "WAIT"


def check_gap(today_open: float, previous_close: float) -> dict:
    """편의 함수 - 갭 계산과 판정을 한 번에.

    Returns:
        {"gap_pct": float, "action": str}
    """
    gap_pct = compute_gap_pct(today_open, previous_close)
    return {"gap_pct": gap_pct, "action": classify_gap(gap_pct)}
