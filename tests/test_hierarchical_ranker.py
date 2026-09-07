"""
hierarchical_ranker 테스트 (Phase 5-16: 계층형 최종 결합)

================================================================================
【변경 이력】
================================================================================
【2026-08-23】최초 생성
【2026-08-23】_MARKET_REGIME_SPAN_PCT 3.0→6.0 변경에 맞춰 상한/하한 테스트 값 조정
  (hierarchical_ranker.py 변경이력 참고 - 사용자가 실제 KIS 화면에서 확인한 최근
  일간 등락률 표준편차 기준으로 폭을 넓힘)
================================================================================
"""

import pytest

from market_intelligence.hierarchical_ranker import (
    compute_market_regime_score,
    rank_stocks,
)


def _price_rows(ticker, daily_pct_change, days=65, start_price=10000, market="KOSPI"):
    rows = []
    price = start_price
    for day in range(days):
        rows.append({
            "ticker": ticker, "market": market,
            "trade_date": f"20260{(day // 28) % 9 + 1}{(day % 28) + 1:02d}",
            "close": round(price, 2), "volume": 10000,
        })
        price *= (1 + daily_pct_change / 100)
    return rows


class TestComputeMarketRegimeScore:
    def test_zero_change_is_neutral(self):
        assert compute_market_regime_score(0.0) == pytest.approx(50.0)

    def test_positive_change_above_neutral(self):
        assert compute_market_regime_score(6.0) == pytest.approx(100.0)  # +6%가 상한

    def test_negative_change_below_neutral(self):
        assert compute_market_regime_score(-6.0) == pytest.approx(0.0)

    def test_none_stays_none(self):
        assert compute_market_regime_score(None) is None


class TestRankStocks:
    def _sector_analysis(self):
        return {
            "sector_scores": {"IT_Semiconductor": 80.0, "Consumer": 30.0},
            "sector_details": {
                "IT_Semiconductor": {"return_20d_pct": 10.0},
                "Consumer": {"return_20d_pct": -5.0},
            },
        }

    def _theme_analysis(self):
        return {"theme_scores": {"AI": 90.0, "Semiconductor": 85.0}}

    def test_full_data_matches_manual_weighted_average(self):
        stocks = [{
            "symbol": "005930", "market": "KOSPI", "sector": "IT_Semiconductor",
            "primary_theme": "AI", "secondary_themes": ["Semiconductor"],
            "price_rows": _price_rows("005930", 0.3),
            "per": 12.0, "pbr": 1.0, "dividend_yield": 3.0,
            "market_per": 18.0, "market_pbr": 1.7, "market_dividend_yield": 2.0,
        }]
        results = rank_stocks(
            stocks,
            market_regime_scores={"KOSPI": 70.0, "KOSDAQ": 40.0},
            sector_analysis=self._sector_analysis(),
            theme_analysis=self._theme_analysis(),
        )
        r = results[0]
        assert r["market_score"] == 70.0
        assert r["sector_score"] == 80.0
        # theme_score = AI(90)*0.7 + Semiconductor(85)*0.2 + 0*0.1 몫 -> 재정규화(available만): (90*0.7+85*0.2)/(0.7+0.2)
        expected_theme = (90.0 * 0.70 + 85.0 * 0.20) / (0.70 + 0.20)
        assert r["theme_score"] == pytest.approx(expected_theme)

        manual_final = (
            r["market_score"] * 0.10 + r["sector_score"] * 0.20 +
            r["theme_score"] * 0.20 + r["stock_score"] * 0.50
        )
        assert r["final_score"] == pytest.approx(manual_final)

    def test_missing_theme_renormalizes_over_remaining_levels(self):
        stocks = [{
            "symbol": "999999", "market": "KOSPI", "sector": "IT_Semiconductor",
            # primary_theme 없음 -> theme_score는 None이 됨
            "price_rows": _price_rows("999999", 0.3),
        }]
        results = rank_stocks(
            stocks,
            market_regime_scores={"KOSPI": 70.0},
            sector_analysis=self._sector_analysis(),
            theme_analysis=self._theme_analysis(),
        )
        r = results[0]
        assert r["theme_score"] is None
        expected = (
            r["market_score"] * (10.0 / 80.0) + r["sector_score"] * (20.0 / 80.0) +
            r["stock_score"] * (50.0 / 80.0)
        )
        assert r["final_score"] == pytest.approx(expected)

    def test_sector_and_theme_ranks_assigned_within_group(self):
        stocks = [
            {"symbol": "AAA", "market": "KOSPI", "sector": "IT_Semiconductor",
             "primary_theme": "AI", "price_rows": _price_rows("AAA", 0.6)},
            {"symbol": "BBB", "market": "KOSPI", "sector": "IT_Semiconductor",
             "primary_theme": "AI", "price_rows": _price_rows("BBB", -0.6)},
        ]
        results = rank_stocks(
            stocks, market_regime_scores={"KOSPI": 50.0},
            sector_analysis=self._sector_analysis(), theme_analysis=self._theme_analysis(),
        )
        by_symbol = {r["symbol"]: r for r in results}
        assert by_symbol["AAA"]["final_score"] > by_symbol["BBB"]["final_score"]
        assert by_symbol["AAA"]["sector_rank"] == 1
        assert by_symbol["BBB"]["sector_rank"] == 2
        assert by_symbol["AAA"]["theme_rank"] == 1
        assert by_symbol["BBB"]["theme_rank"] == 2

    def test_stock_with_no_sector_gets_no_sector_rank(self):
        stocks = [{"symbol": "CCC", "market": "KOSPI", "price_rows": _price_rows("CCC", 0.1)}]
        results = rank_stocks(
            stocks, market_regime_scores={"KOSPI": 50.0},
            sector_analysis=self._sector_analysis(), theme_analysis=self._theme_analysis(),
        )
        assert "sector_rank" not in results[0]
