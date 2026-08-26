"""
포트폴리오 전체 위험 한도 관리 (Phase 6-1)

================================================================================
【변경 이력】
================================================================================
【2026-08-25】최초 생성 (Phase 6-1) - 업로드 문서(miev2trading.txt) §7, §13,
§14 그대로 구현.

핵심 원칙(문서 그대로): 종목별 위험(0.5%)을 다 더해도 계좌 전체 위험이
목표치(5%)를 넘으면 안 된다. 개별 종목 계산(position_sizer.py)이 "이
종목만 보면 얼마까지 살 수 있는가"를 답한다면, 이 모듈은 "다른 종목들과
합쳐서 봐도 괜찮은가"를 답한다 - 신규 진입/추가매수 모두에 적용해야 한다
(문서 §13 "추가 매수 시에도 새 위험을 다시 계산해야 한다").
================================================================================
"""

from math import floor
from typing import List, Dict, Any

from market_intelligence.trade_execution.config import TradingConfig, DEFAULT_CONFIG


def position_risk(position: Dict[str, Any]) -> float:
    """보유 포지션 1개의 현재 손절 위험액(원). quantity * (average_price -
    stop_price) - 이미 평균단가보다 stop_price가 높아진(트레일링 등으로
    이익 구간에 들어간) 경우는 0으로 처리한다(그 이상 위험이 없으므로)."""
    quantity = position.get("quantity", 0) or 0
    average_price = position.get("average_price")
    stop_price = position.get("stop_price")
    if average_price is None or stop_price is None:
        return 0.0
    risk_per_share = max(average_price - stop_price, 0.0)
    return quantity * risk_per_share


def total_portfolio_risk(positions: List[Dict[str, Any]]) -> float:
    """현재 보유 중인 모든 포지션의 위험액 합계(원)."""
    return sum(position_risk(p) for p in positions)


def remaining_risk_budget(positions: List[Dict[str, Any]], config: TradingConfig = DEFAULT_CONFIG) -> float:
    """신규 진입/추가매수에 아직 쓸 수 있는 위험 한도(원). 이미 한도를
    넘었으면 0을 돌려준다(음수를 돌려주지 않음 - 호출부가 "더 이상 못 산다"만
    알면 되므로)."""
    max_budget = config.total_capital * config.max_portfolio_risk_ratio
    used = total_portfolio_risk(positions)
    return max(max_budget - used, 0.0)


def clip_shares_to_portfolio_risk(
    proposed_shares: int,
    risk_per_share: float,
    positions: List[Dict[str, Any]],
    config: TradingConfig = DEFAULT_CONFIG,
) -> int:
    """개별 종목 기준으로 계산된 매수 수량(proposed_shares)을, 포트폴리오
    전체 위험 한도 안으로 다시 한번 깎는다. position_sizer.calculate_position()
    의 target_shares(또는 split_entry_shares()의 회차별 수량)를 이 함수에
    통과시킨 뒤에 실제 주문에 써야 한다.

    Returns:
        min(proposed_shares, 포트폴리오 위험 한도로 살 수 있는 최대 수량).
        risk_per_share<=0이면 proposed_shares를 그대로 돌려준다(위험 계산이
        무의미한 경우 - position_sizer 쪽에서 이미 걸러졌어야 하는 상황).
    """
    if risk_per_share <= 0:
        return proposed_shares

    budget = remaining_risk_budget(positions, config)
    shares_by_portfolio_budget = floor(budget / risk_per_share)
    return max(min(proposed_shares, shares_by_portfolio_budget), 0)
