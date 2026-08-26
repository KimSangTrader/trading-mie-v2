"""pyramiding.py 테스트 (Phase 6-1) - should_add()/check_stop()의 각 차단 조건."""
import pytest
from market_intelligence.trade_execution.config import TradingConfig
from market_intelligence.trade_execution.pyramiding import should_add, check_stop

CONFIG = TradingConfig(total_capital=7_000_000.0)


def _position(**overrides):
    base = {
        "average_price": 10_000.0,
        "last_entry_price": 10_000.0,
        "entry_count": 1,
        "stop_price": 9_000.0,
        "quantity": 35,
    }
    base.update(overrides)
    return base


def _candidate(**overrides):
    base = {
        "current_price": 10_600.0,  # 마지막 매수가 + 1 ATR(500) 이상
        "atr20": 500.0,
        "current_rank": 10,
        "sector_score": 70.0,
        "theme_score": 65.0,
    }
    base.update(overrides)
    return base


class TestShouldAdd:
    def test_all_conditions_pass(self):
        action, reason = should_add(_position(), _candidate(), CONFIG)
        assert action == "ADD"
        assert reason == "PYRAMID_APPROVED"

    def test_max_entries_reached(self):
        action, reason = should_add(_position(entry_count=3), _candidate(), CONFIG)
        assert action == "HOLD"
        assert reason == "MAX_ENTRIES_REACHED"

    def test_losing_position_never_adds(self):
        """문서의 핵심 원칙: 평균단가 이하에서는 절대 물타기하지 않는다."""
        action, reason = should_add(_position(), _candidate(current_price=9_500.0), CONFIG)
        assert action == "HOLD"
        assert reason == "LOSING_POSITION"

    def test_price_at_average_is_still_blocked(self):
        """평균단가와 정확히 같아도(수익 0) 추가매수 금지 - 문서는 "수익
        방향으로 움직였을 때"라고 했으므로 동일가는 통과시키지 않는다."""
        action, reason = should_add(_position(), _candidate(current_price=10_000.0), CONFIG)
        assert action == "HOLD"
        assert reason == "LOSING_POSITION"

    def test_atr_target_not_reached(self):
        action, reason = should_add(_position(), _candidate(current_price=10_300.0), CONFIG)  # +1ATR 미달
        assert action == "HOLD"
        assert reason == "ATR_TARGET_NOT_REACHED"

    def test_rank_dropped_blocks_add(self):
        """문서 예시: 전일 1위 -> 오늘 85위면 추가매수 금지(30위 초과)."""
        action, reason = should_add(_position(), _candidate(current_rank=85), CONFIG)
        assert action == "HOLD"
        assert reason == "RANK_WEAKENED"

    def test_rank_still_ok_within_30(self):
        """문서 예시: 전일 1위 -> 오늘 3위는 괜찮다."""
        action, reason = should_add(_position(), _candidate(current_rank=3), CONFIG)
        assert action == "ADD"

    def test_sector_weakened_blocks_add(self):
        action, reason = should_add(_position(), _candidate(sector_score=50.0), CONFIG)
        assert action == "HOLD"
        assert reason == "SECTOR_WEAKENED"

    def test_theme_weakened_blocks_add(self):
        action, reason = should_add(_position(), _candidate(theme_score=40.0), CONFIG)
        assert action == "HOLD"
        assert reason == "THEME_WEAKENED"


class TestCheckStop:
    def test_stop_hit(self):
        action, reason = check_stop(_position(stop_price=9_000.0), current_price=8_900.0)
        assert action == "STOP_LOSS"

    def test_exactly_at_stop_triggers(self):
        action, reason = check_stop(_position(stop_price=9_000.0), current_price=9_000.0)
        assert action == "STOP_LOSS"

    def test_above_stop_holds(self):
        action, reason = check_stop(_position(stop_price=9_000.0), current_price=9_500.0)
        assert action == "HOLD"

    def test_missing_data_holds_safely(self):
        action, reason = check_stop(_position(stop_price=None), current_price=9_500.0)
        assert action == "HOLD"
        assert reason == "MISSING_STOP_OR_PRICE"
