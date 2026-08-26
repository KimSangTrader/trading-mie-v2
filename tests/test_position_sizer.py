"""position_sizer.py 테스트 (Phase 6-1)

업로드 문서(miev2trading.txt)에 나온 계산 예시를 그대로 픽스처로 써서,
구현이 문서의 수치와 정확히 일치하는지 확인한다.
"""
import pytest
from market_intelligence.trade_execution.config import TradingConfig
from market_intelligence.trade_execution.position_sizer import calculate_position, split_entry_shares

# 문서 §8의 700만원 계좌 보수형 설정과 동일
CONFIG_700 = TradingConfig(total_capital=7_000_000.0)


class TestCalculatePosition:
    def test_document_example_B_stock(self):
        """문서 §9(두 번째 글) Step 1~6 예시: 진입가 20,000원, ATR20 1,000원
        -> 손절 18,000원, 1주당 위험 2,000원, 위험기준 17주, 투자한도기준 52주,
        최종 17주."""
        result = calculate_position(entry_price=20_000, atr20=1_000, available_cash=10_000_000, config=CONFIG_700)
        assert result is not None
        assert result["stop_price"] == 18_000
        assert result["risk_per_share"] == 2_000
        assert result["shares_by_risk"] == 17
        assert result["shares_by_position_limit"] == 52
        assert result["target_shares"] == 17

    def test_document_example_A_stock(self):
        """문서 §3/§11 A종목: 진입가 10,000원, ATR20 500원 -> 손절 9,000원,
        1주당 위험 1,000원, 35주, 투자금 350,000원, 최대손실 35,000원."""
        result = calculate_position(entry_price=10_000, atr20=500, available_cash=10_000_000, config=CONFIG_700)
        assert result["shares_by_risk"] == 35
        assert result["target_shares"] == 35
        assert result["investment_amount"] == 350_000
        assert result["expected_loss"] == 35_000

    def test_document_example_B_stock_section4(self):
        """문서 §4 B종목: 진입가 20,000원, ATR20 2,000원 -> 손절 16,000원,
        1주당 위험 4,000원, 8주, 투자금 160,000원, 최대손실 32,000원."""
        result = calculate_position(entry_price=20_000, atr20=2_000, available_cash=10_000_000, config=CONFIG_700)
        assert result["shares_by_risk"] == 8
        assert result["target_shares"] == 8
        assert result["investment_amount"] == 160_000
        assert result["expected_loss"] == 32_000

    def test_max_position_ratio_caps_low_volatility_stock(self):
        """문서 §5의 핵심 경고 사례: ATR이 너무 작으면 위험기준만으로는
        350주(계좌의 25%)까지 살 수 있게 계산되지만, 종목당 최대 투자금액
        한도(15%=1,050,000원)가 이를 210주로 깎아야 한다."""
        result = calculate_position(entry_price=5_000, atr20=50, available_cash=10_000_000, config=CONFIG_700)
        assert result["shares_by_risk"] == 350
        assert result["shares_by_position_limit"] == 210
        assert result["target_shares"] == 210  # 더 작은 쪽(투자한도)이 최종 적용돼야 함

    def test_cash_constraint_applies(self):
        """가용 현금이 부족하면 그게 최종 병목이 된다."""
        result = calculate_position(entry_price=10_000, atr20=500, available_cash=100_000, config=CONFIG_700)
        assert result["shares_by_cash"] == 10
        assert result["target_shares"] == 10

    @pytest.mark.parametrize("entry_price,atr20", [(0, 500), (-100, 500), (10_000, 0), (10_000, -50)])
    def test_invalid_inputs_return_none(self, entry_price, atr20):
        assert calculate_position(entry_price=entry_price, atr20=atr20, available_cash=1_000_000, config=CONFIG_700) is None

    def test_seven_stock_table_total(self):
        """문서 §11의 7종목 예시표 - A/B/C/D/F/G 6종목은 표의 매수 주수와
        정확히 일치한다(전부 shares=floor(35,000/(2*ATR)) 공식대로).

        E종목(30,000원/ATR 800)만 표에 14주로 적혀 있는데, 이는 문서 자체의
        공식(2*ATR 손절)과 안 맞는 계산 오류다 - floor(35,000/(2*800))=21이
        맞고, 표의 14주가 되려면 risk_per_share=2,400(=3*ATR)이어야 해서
        다른 6종목의 배수(2*ATR)와도 어긋난다. 이 구현은 문서가 명시한 공식
        (2*ATR)을 그대로 따르므로 E종목은 21주가 맞다 - 표의 오탈자를
        따라가지 않는다."""
        rows = [
            (10_000, 500, 35),
            (20_000, 1_000, 17),
            (50_000, 2_500, 7),
            (5_000, 150, 116),
            (30_000, 800, 21),   # 문서 표는 14주로 오기(誤記) - 공식대로면 21주
            (15_000, 600, 29),
            (8_000, 400, 43),
        ]
        for entry_price, atr20, expected_shares in rows:
            result = calculate_position(entry_price=entry_price, atr20=atr20, available_cash=10_000_000, config=CONFIG_700)
            assert result["shares_by_risk"] == expected_shares, f"entry={entry_price} atr={atr20}"


class TestSplitEntryShares:
    def test_conservative_split(self):
        """1차 50%/2차 25%/3차 25% (보수형, 문서 §13 기본값)."""
        config = TradingConfig(total_capital=7_000_000.0)
        assert split_entry_shares(100, 1, config) == 50
        assert split_entry_shares(100, 2, config) == 25
        assert split_entry_shares(100, 3, config) == 25

    def test_unknown_sequence_returns_zero(self):
        config = TradingConfig(total_capital=7_000_000.0)
        assert split_entry_shares(100, 4, config) == 0

    def test_rounding_never_exceeds_target(self):
        config = TradingConfig(total_capital=7_000_000.0)
        target = 17
        total = sum(split_entry_shares(target, seq, config) for seq in (1, 2, 3))
        assert total <= target
