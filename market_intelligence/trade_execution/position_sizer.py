"""
ATR 기반 포지션 사이징 (Phase 6-1)

================================================================================
【변경 이력】
================================================================================
【2026-08-25】최초 생성 (Phase 6-1) - 업로드 문서(miev2trading.txt) §15/§9(두 번째
글) 그대로 구현.
- 핵심 원칙(문서 그대로): "종목마다 같은 금액을 사지 않는다. 손절될 때 잃는
  금액(위험)을 종목마다 동일하게 맞추고, 그 위험 한도 안에서 변동성(ATR)에
  따라 수량이 자동으로 달라지게 한다."
- calculate()는 "이 종목에 최종적으로 다 채웠을 때의 목표 수량"(target_shares)
  까지만 계산한다. 문서의 1차 50%/2차 25%/3차 25% 분할은 이 목표 수량에
  entry_weights를 곱해서 각 회차의 실제 매수 수량을 구하는 방식으로
  split_entry_shares()에 분리했다 - PositionSizer 자체는 "얼마까지 살
  것인가"만 책임지고, "몇 번에 나눠 살 것인가"는 별도 함수로 둔 것(단일
  책임 분리).
- available_cash 인자를 문서 원본 계산식(risk 기준, 투자한도 기준 min)에
  하나 더 추가했다 - 문서 §9 마지막 "제가 가장 추천하는 핵심 공식"에도
  available_cash // entry_price가 min()에 포함되어 있어서 문서 의도와
  일치한다(실제로 없는 현금을 매수 수량 계산에 넣지 않기 위함).
================================================================================
"""

from math import floor
from typing import Optional, Dict

from market_intelligence.trade_execution.config import TradingConfig, DEFAULT_CONFIG


def calculate_position(
    entry_price: float,
    atr20: float,
    available_cash: float,
    config: TradingConfig = DEFAULT_CONFIG,
) -> Optional[Dict[str, float]]:
    """진입가/ATR20/가용현금으로 이 종목의 "목표 최종 수량"을 계산한다.

    Args:
        entry_price: 진입(예정) 가격.
        atr20: 20일 ATR(원). 0 이하면 계산 불가(atr.compute_atr가 결측 시
            None을 돌려주므로, 호출부는 atr20이 None이 아님을 먼저 확인해야
            한다 - 이 함수는 숫자만 받는다).
        available_cash: 이 종목에 실제로 쓸 수 있는 현금(계좌 가용 현금,
            포트폴리오 위험 한도로 이미 줄여진 값이어도 됨 - 이 함수는 그냥
            상한선 중 하나로만 씀).
        config: TradingConfig. 기본값은 문서의 700만원 계좌 보수형 설정.

    Returns:
        None: entry_price<=0, atr20<=0, 또는 stop_price>=entry_price(손절폭이
            0 이하 - 데이터 이상)인 경우. 이 경우 이 종목은 매수하지 않는다.
        dict: {
            "entry_price", "atr20", "stop_price", "risk_per_share",
            "shares_by_risk", "shares_by_position_limit", "shares_by_cash",
            "target_shares"(세 상한의 최솟값 - 최종 목표 수량),
            "investment_amount"(target_shares 기준 투자금액),
            "expected_loss"(target_shares 기준 최대 예상 손실액),
            "expected_loss_pct"(계좌 대비 %),
        }
    """
    if entry_price is None or entry_price <= 0:
        return None
    if atr20 is None or atr20 <= 0:
        return None

    stop_price = entry_price - atr20 * config.stop_atr_multiple
    risk_per_share = entry_price - stop_price
    if risk_per_share <= 0:
        return None

    risk_budget = config.total_capital * config.risk_per_stock_ratio
    shares_by_risk = floor(risk_budget / risk_per_share)

    max_position_amount = config.total_capital * config.max_position_ratio
    shares_by_position_limit = floor(max_position_amount / entry_price)

    shares_by_cash = floor(max(available_cash, 0) / entry_price)

    target_shares = max(min(shares_by_risk, shares_by_position_limit, shares_by_cash), 0)

    investment_amount = target_shares * entry_price
    expected_loss = target_shares * risk_per_share
    expected_loss_pct = (expected_loss / config.total_capital * 100.0) if config.total_capital else 0.0

    return {
        "entry_price": entry_price,
        "atr20": atr20,
        "stop_price": stop_price,
        "risk_per_share": risk_per_share,
        "shares_by_risk": shares_by_risk,
        "shares_by_position_limit": shares_by_position_limit,
        "shares_by_cash": shares_by_cash,
        "target_shares": target_shares,
        "investment_amount": investment_amount,
        "expected_loss": expected_loss,
        "expected_loss_pct": expected_loss_pct,
    }


def split_entry_shares(
    target_shares: int,
    entry_sequence: int,
    config: TradingConfig = DEFAULT_CONFIG,
) -> int:
    """목표 수량(target_shares)을 회차별 비중(entry_weights)에 따라 나눈다.

    Args:
        target_shares: calculate_position()의 target_shares.
        entry_sequence: 몇 번째 매수인지(1, 2, 3, ...). config.entry_weights에
            없는 회차(예: max_entries를 넘는 4차)는 0을 돌려준다.

    Returns:
        이번 회차에 매수할 수량(정수, 내림). 문서 예시(50/25/25)에서 단순히
        target_shares에 비중을 곱해 매 회차 독립적으로 내림하므로, 세 번
        다 사도 합이 target_shares보다 1~2주 적게 나올 수 있다 - 이건
        "목표보다 적게 사는 것"이라 위험 한도를 넘지 않는 안전한 방향의
        오차이므로 의도적으로 그대로 둔다(반대로 넘치면 위험 한도 위반).
    """
    weight = config.entry_weights.get(entry_sequence, 0.0)
    return floor(target_shares * weight)
