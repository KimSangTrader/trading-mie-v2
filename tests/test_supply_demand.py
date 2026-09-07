"""
supply_demand 테스트 (Phase 5-18: 종목별 외국인/기관 순매수 데이터 연동)

================================================================================
【변경 이력】
================================================================================
【2026-08-24】최초 생성
================================================================================
"""

import pytest

from market_intelligence.supply_demand import compute_supply_demand_score


def _investor_trend(dates, foreign_qty, institution_qty):
    return {
        "dates": dates,
        "foreign_net_qty": foreign_qty,
        "institution_net_qty": institution_qty,
    }


def _price_rows(dates, volume=500000):
    return [{"trade_date": d, "volume": volume} for d in dates]


class TestComputeSupplyDemandScore:
    def test_none_investor_trend_returns_none(self):
        assert compute_supply_demand_score(None, _price_rows(["20260821"])) is None

    def test_none_price_rows_returns_none(self):
        trend = _investor_trend(["20260821"], [1000], [1000])
        assert compute_supply_demand_score(trend, None) is None

    def test_empty_dates_returns_none(self):
        trend = _investor_trend([], [], [])
        assert compute_supply_demand_score(trend, _price_rows(["20260821"])) is None

    def test_strong_net_buying_scores_above_neutral(self):
        dates = ["20260817", "20260818", "20260819", "20260820", "20260821"]
        # 외국인+기관이 매일 거래량의 8%를 순매수 (30000+10000)/500000 = 0.08
        trend = _investor_trend(dates, [30000] * 5, [10000] * 5)
        score = compute_supply_demand_score(trend, _price_rows(dates))
        assert score == pytest.approx(90.0)  # scale_symmetric(0.08, 100, 0.10)

    def test_strong_net_selling_scores_below_neutral(self):
        dates = ["20260817", "20260818", "20260819", "20260820", "20260821"]
        trend = _investor_trend(dates, [-30000] * 5, [-10000] * 5)
        score = compute_supply_demand_score(trend, _price_rows(dates))
        assert score == pytest.approx(10.0)

    def test_zero_net_buying_is_neutral(self):
        dates = ["20260817", "20260818", "20260819", "20260820", "20260821"]
        trend = _investor_trend(dates, [0] * 5, [0] * 5)
        score = compute_supply_demand_score(trend, _price_rows(dates))
        assert score == pytest.approx(50.0)

    def test_extreme_ratio_clamps_to_100(self):
        dates = ["20260821"]
        # 순매수량이 거래량 자체를 넘어서는 극단값 -> 100점 상한에서 클램프
        trend = _investor_trend(dates, [400000], [200000])
        score = compute_supply_demand_score(trend, _price_rows(dates, volume=500000))
        assert score == pytest.approx(100.0)

    def test_only_uses_matching_dates_between_trend_and_price_rows(self):
        # investor_trend에 5일치가 있어도 price_rows(거래량)가 겹치는 날짜만 쓴다
        dates = ["20260817", "20260818", "20260819", "20260820", "20260821"]
        trend = _investor_trend(dates, [30000] * 5, [10000] * 5)
        # 마지막 하루치 거래량만 제공 - 그 하루만으로 계산돼야 함
        score = compute_supply_demand_score(trend, _price_rows(["20260821"]))
        assert score == pytest.approx(90.0)  # (30000+10000)/500000 = 0.08과 동일 비율

    def test_no_overlapping_dates_returns_none(self):
        trend = _investor_trend(["20260821"], [30000], [10000])
        score = compute_supply_demand_score(trend, _price_rows(["20260101"]))
        assert score is None

    def test_missing_one_investor_type_still_computes_from_the_other(self):
        dates = ["20260821"]
        trend = {
            "dates": dates,
            "foreign_net_qty": [40000],
            "institution_net_qty": [None],
        }
        score = compute_supply_demand_score(trend, _price_rows(dates, volume=500000))
        assert score == pytest.approx(scale_expected(40000, 500000))

    def test_zero_volume_day_is_excluded(self):
        dates = ["20260820", "20260821"]
        trend = _investor_trend(dates, [30000, 30000], [10000, 10000])
        rows = [{"trade_date": "20260820", "volume": 0}, {"trade_date": "20260821", "volume": 500000}]
        score = compute_supply_demand_score(trend, rows)
        # 거래량 0인 날은 제외되고 마지막 하루만 반영
        assert score == pytest.approx(90.0)

    def test_window_days_limits_lookback(self):
        dates = ["20260101", "20260817", "20260818", "20260819", "20260820", "20260821"]
        # 아주 오래된 첫 날짜는 극단적 순매도지만 window_days=5라 최근 5일만 봄
        foreign = [-999999, 30000, 30000, 30000, 30000, 30000]
        institution = [0, 10000, 10000, 10000, 10000, 10000]
        trend = _investor_trend(dates, foreign, institution)
        score = compute_supply_demand_score(trend, _price_rows(dates), window_days=5)
        assert score == pytest.approx(90.0)


def scale_expected(net_qty, volume, span=0.10):
    ratio = net_qty / volume
    points = 50.0 * (1 + ratio / span)
    return max(0.0, min(100.0, points))
