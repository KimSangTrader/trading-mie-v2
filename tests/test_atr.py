"""atr.py 테스트 (Phase 6-1)."""
import pytest
from market_intelligence.trade_execution.atr import compute_true_range, compute_atr


def _make_rows(n, period=20):
    """close가 매일 1씩 오르고 high=close+5/low=close-5인 합성 데이터.
    이 조건에서는 항상 (고가-저가=10)이 True Range의 최댓값이 되므로,
    ATR20이 정확히 10이 되는 걸 손으로 검증할 수 있다."""
    rows = []
    close = 100
    for i in range(n):
        rows.append({"high": close + 5, "low": close - 5, "close": close})
        close += 1
    return rows


class TestComputeTrueRange:
    def test_no_prev_close_uses_high_low_only(self):
        assert compute_true_range(high=105, low=95, prev_close=None) == 10

    def test_gap_up_dominates(self):
        # 전일 종가 90, 오늘 고가 105/저가 100 -> |105-90|=15가 최댓값
        assert compute_true_range(high=105, low=100, prev_close=90) == 15

    def test_gap_down_dominates(self):
        # 전일 종가 120, 오늘 고가 105/저가 100 -> |100-120|=20이 최댓값
        assert compute_true_range(high=105, low=100, prev_close=120) == 20


class TestComputeAtr:
    def test_deterministic_fixture(self):
        rows = _make_rows(21)  # period(20)+1
        assert compute_atr(rows, period=20) == pytest.approx(10.0)

    def test_insufficient_rows_returns_none(self):
        rows = _make_rows(20)  # period+1보다 1개 부족
        assert compute_atr(rows, period=20) is None

    def test_empty_rows_returns_none(self):
        assert compute_atr([], period=20) is None

    def test_missing_high_low_reduces_valid_count(self):
        rows = _make_rows(21)
        rows[5]["high"] = None  # 유효 True Range가 20개 미만이 되어야 함
        assert compute_atr(rows, period=20) is None

    def test_exactly_enough_rows_after_trim(self):
        """더 많은 행이 있어도 최근 period+1개만 쓴다."""
        rows = _make_rows(100)
        result = compute_atr(rows, period=20)
        assert result == pytest.approx(10.0)
