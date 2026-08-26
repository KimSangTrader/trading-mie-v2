"""entry_filter.py 테스트 (Phase 6-1) - check_entry()의 각 차단 조건."""
import pytest
from market_intelligence.trade_execution.config import TradingConfig
from market_intelligence.trade_execution.entry_filter import check_entry

CONFIG = TradingConfig(total_capital=7_000_000.0)


def _candidate(**overrides):
    base = {
        "previous_close": 10_000,
        "current_price": 10_200,   # +2% 갭 (NORMAL_ENTRY 구간)
        "final_score": 80.0,
        "sector_score": 70.0,
        "theme_score": 65.0,
        "atr20": 500.0,
    }
    base.update(overrides)
    return base


class TestCheckEntry:
    def test_all_conditions_pass(self):
        action, reason = check_entry(_candidate(), CONFIG)
        assert action == "BUY"
        assert reason == "ENTRY_APPROVED"

    def test_gap_too_high_blocks_entirely(self):
        action, reason = check_entry(_candidate(current_price=11_500), CONFIG)  # +15%
        assert action == "NO_ENTRY"
        assert "GAP" in reason

    def test_gap_wait_confirmation_defers(self):
        action, reason = check_entry(_candidate(current_price=10_500), CONFIG)  # +5%
        assert action == "WAIT"

    def test_gap_reduce_position(self):
        action, reason = check_entry(_candidate(current_price=10_900), CONFIG)  # +9%
        assert action == "REDUCE"
        assert reason == "GAP_REDUCE_POSITION"

    def test_low_final_score_waits(self):
        action, reason = check_entry(_candidate(final_score=70.0), CONFIG)
        assert action == "WAIT"
        assert reason == "LOW_FINAL_SCORE"

    def test_weak_sector_waits(self):
        action, reason = check_entry(_candidate(sector_score=60.0), CONFIG)
        assert action == "WAIT"
        assert reason == "WEAK_SECTOR"

    def test_weak_theme_waits(self):
        action, reason = check_entry(_candidate(theme_score=50.0), CONFIG)
        assert action == "WAIT"
        assert reason == "WEAK_THEME"

    def test_invalid_atr_waits(self):
        action, reason = check_entry(_candidate(atr20=0), CONFIG)
        assert action == "WAIT"
        assert reason == "INVALID_ATR"

    def test_missing_price_data_waits(self):
        action, reason = check_entry(_candidate(previous_close=None), CONFIG)
        assert action == "WAIT"
        assert reason == "MISSING_PRICE_DATA"

    def test_gap_checked_before_scores(self):
        """갭이 이미 NO_ENTRY 수준이면 점수가 만점이어도 절대 통과 못 한다
        (문서의 "갭 상승한 종목은 추격하지 않는다" 원칙이 최우선)."""
        action, reason = check_entry(_candidate(current_price=13_000, final_score=100, sector_score=100, theme_score=100), CONFIG)
        assert action == "NO_ENTRY"
