"""gap_filter.py 테스트 (Phase 6-1) - 업로드 문서 §4의 5단계 판정표 경계값 검증."""
import pytest
from market_intelligence.trade_execution.gap_filter import compute_gap_pct, classify_gap, check_gap


class TestComputeGapPct:
    def test_document_example(self):
        """문서 §3 예시: 전일 종가 10,000원, 다음날 시가 11,500원 -> 갭 +15%."""
        assert compute_gap_pct(11_500, 10_000) == pytest.approx(15.0)

    def test_zero_previous_close_raises(self):
        with pytest.raises(ValueError):
            compute_gap_pct(1000, 0)


class TestClassifyGap:
    @pytest.mark.parametrize("gap_pct,expected", [
        (-10.0, "WAIT"),
        (-5.0, "WAIT"),          # 경계 포함(<=-5 -> WAIT, 문서 원문 그대로)
        (-4.999, "NORMAL_ENTRY"),
        (0.0, "NORMAL_ENTRY"),
        (3.0, "NORMAL_ENTRY"),   # 경계 포함
        (3.001, "WAIT_CONFIRMATION"),
        (7.0, "WAIT_CONFIRMATION"),   # 경계 포함
        (7.001, "REDUCE_POSITION"),
        (12.0, "REDUCE_POSITION"),    # 경계 포함
        (12.001, "NO_ENTRY"),
        (15.0, "NO_ENTRY"),      # 문서 §3의 +15% 예시
        (50.0, "NO_ENTRY"),
    ])
    def test_boundaries_match_document(self, gap_pct, expected):
        assert classify_gap(gap_pct) == expected


class TestCheckGap:
    def test_returns_gap_and_action(self):
        result = check_gap(today_open=10_300, previous_close=10_000)
        assert result["gap_pct"] == pytest.approx(3.0)
        assert result["action"] == "NORMAL_ENTRY"
