"""portfolio_risk.py 테스트 (Phase 6-1) - 업로드 문서 §14의 7종목 합계 예시 그대로."""
import pytest
from market_intelligence.trade_execution.config import TradingConfig
from market_intelligence.trade_execution.portfolio_risk import (
    position_risk,
    total_portfolio_risk,
    remaining_risk_budget,
    clip_shares_to_portfolio_risk,
)

CONFIG = TradingConfig(total_capital=7_000_000.0)


def _pos(loss):
    """quantity=1이고 (average_price - stop_price) = loss가 되도록 만든
    포지션 - position_risk() 계산 검증용 헬퍼."""
    return {"quantity": 1, "average_price": loss, "stop_price": 0}


class TestPositionRisk:
    def test_basic(self):
        pos = {"quantity": 35, "average_price": 10_000, "stop_price": 9_000}
        assert position_risk(pos) == 35_000

    def test_stop_above_average_is_zero_risk(self):
        """트레일링 등으로 손절가가 평균단가보다 높아졌으면 위험 0(이익
        구간 진입) - 음수 위험으로 포트폴리오 위험을 부풀리지 않는다."""
        pos = {"quantity": 10, "average_price": 10_000, "stop_price": 10_500}
        assert position_risk(pos) == 0.0


class TestTotalPortfolioRisk:
    def test_document_seven_stock_example(self):
        """문서 §14: A~G 최대 손실 합계 242,000원."""
        losses = [35_000, 34_000, 35_000, 35_000, 34_000, 35_000, 34_000]
        positions = [_pos(loss) for loss in losses]
        assert total_portfolio_risk(positions) == 242_000

    def test_remaining_budget_document_example(self):
        """문서 §14: 5% 한도(350,000원) - 242,000원 = 108,000원."""
        losses = [35_000, 34_000, 35_000, 35_000, 34_000, 35_000, 34_000]
        positions = [_pos(loss) for loss in losses]
        assert remaining_risk_budget(positions, CONFIG) == pytest.approx(108_000)

    def test_over_budget_clamps_to_zero(self):
        positions = [_pos(400_000)]  # 이미 한도(350,000) 초과
        assert remaining_risk_budget(positions, CONFIG) == 0.0

    def test_empty_positions_full_budget(self):
        assert remaining_risk_budget([], CONFIG) == pytest.approx(350_000)


class TestClipSharesToPortfolioRisk:
    def test_clips_when_budget_insufficient(self):
        positions = [_pos(35_000) for _ in range(6)]  # 이미 210,000원 사용, 남은 140,000원
        # 신규 종목 risk_per_share=1,000원 -> 남은 예산 기준 140주까지만 가능
        clipped = clip_shares_to_portfolio_risk(proposed_shares=200, risk_per_share=1_000, positions=positions, config=CONFIG)
        assert clipped == 140

    def test_no_clip_when_budget_sufficient(self):
        clipped = clip_shares_to_portfolio_risk(proposed_shares=10, risk_per_share=1_000, positions=[], config=CONFIG)
        assert clipped == 10

    def test_zero_risk_per_share_returns_proposed_unchanged(self):
        clipped = clip_shares_to_portfolio_risk(proposed_shares=10, risk_per_share=0, positions=[], config=CONFIG)
        assert clipped == 10
