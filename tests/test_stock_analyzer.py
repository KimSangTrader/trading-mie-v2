"""
StockAnalyzer 테스트 (Phase 5-15: 개별 종목 100점 분석기 신규)

================================================================================
【변경 이력】
================================================================================
【2026-08-23】최초 생성
================================================================================
"""

import pytest

from market_intelligence.analyzers.stock_analyzer import StockAnalyzer


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


class TestStockAnalyzerValidation:
    def test_validate_requires_price_rows(self):
        analyzer = StockAnalyzer()
        assert analyzer.validate({"price_rows": [1]}) is True
        assert analyzer.validate({"price_rows": []}) is False
        assert analyzer.validate({}) is False
        assert analyzer.validate("nope") is False


class TestStockAnalyzerAnalyze:
    def test_strong_stock_scores_above_neutral(self):
        analyzer = StockAnalyzer()
        result = analyzer.run({
            "price_rows": _price_rows("005930", 0.6),
            "symbol": "005930", "market": "KOSPI",
            "per": 12.0, "pbr": 1.0, "dividend_yield": 3.0,
            "market_per": 18.0, "market_pbr": 1.7, "market_dividend_yield": 2.0,
            "sector_return_20d": 2.0,
        })
        assert result["score"] > 60
        assert result["details"]["data_quality"] == 100.0

    def test_weak_stock_scores_below_neutral(self):
        analyzer = StockAnalyzer()
        result = analyzer.run({
            "price_rows": _price_rows("999999", -0.6),
            "symbol": "999999", "market": "KOSPI",
            "per": 40.0, "pbr": 5.0, "dividend_yield": 0.1,
            "market_per": 18.0, "market_pbr": 1.7, "market_dividend_yield": 2.0,
            "sector_return_20d": 2.0,
        })
        assert result["score"] < 40

    def test_missing_optional_inputs_still_produce_a_score(self):
        # 밸류에이션/Sector 상대강도 입력이 전혀 없어도(가격 데이터만 있어도) 죽지 않아야 함
        analyzer = StockAnalyzer()
        result = analyzer.run({"price_rows": _price_rows("005930", 0.1)})
        assert 0 <= result["score"] <= 100
        assert result["details"]["sector_relative_pct"] is None
        assert result["details"]["valuation_score_100"] == 50.0  # 데이터 없으니 중립

    def test_sector_median_preferred_over_market_median(self):
        analyzer = StockAnalyzer()
        rows = _price_rows("005930", 0.1)
        result_sector = analyzer.run({
            "price_rows": rows, "per": 15.0,
            "sector_per_median": 15.0,  # 종목 PER == Sector 중앙값 → 상대평가 중립(50점) 근처
            "market_per": 30.0,  # market과는 크게 차이나야 basis 우선순위를 구분할 수 있음
        })
        assert result_sector["details"]["valuation_basis"] == "sector"
        # PER 15.0 / sector_per_median 15.0 = 1.0(시장과 동일) → per_relative_score는 50점 근방이어야 함
        assert result_sector["details"]["valuation_score_100"] == pytest.approx(50.0, abs=1.0)

    def test_supply_demand_excluded_when_not_provided(self):
        analyzer = StockAnalyzer()
        result = analyzer.run({"price_rows": _price_rows("005930", 0.1)})
        assert result["details"]["supply_demand_points"] is None

    def test_supply_demand_included_when_provided(self):
        analyzer = StockAnalyzer()
        result = analyzer.run({
            "price_rows": _price_rows("005930", 0.1),
            "supply_demand_score": 90.0,
        })
        assert result["details"]["supply_demand_points"] == pytest.approx(22.5)  # 90 * 25/100

    def test_sector_relative_points_reflect_excess_return(self):
        analyzer = StockAnalyzer()
        # 종목 자체는 완만한 상승(20일 수익률은 알 수 없지만 sector_return_20d를 매우 낮게
        # 줘서 상대강도가 크게 플러스가 되도록 구성)
        result = analyzer.run({
            "price_rows": _price_rows("005930", 0.3),
            "sector_return_20d": -50.0,  # 극단적으로 낮은 Sector 수익률 - 상대강도 극대화
        })
        assert result["details"]["sector_relative_pct"] > 0
        assert result["details"]["sector_relative_points"] == 20.0  # 상한 클리핑
