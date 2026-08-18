"""
MarketValuation 테스트 (Phase 5-4: KOSPI/KOSDAQ 중앙값 계산)

================================================================================
【변경 이력】
================================================================================
【2026-08-14】최초 생성
- KOSPI/KOSDAQ 분리 계산, 결측값 제외, 표본 없는 시장 제외 검증
================================================================================
"""

import pytest
from market_intelligence.market_valuation import MarketValuation, KOSPI, KOSDAQ


class TestMarketValuationMedians:
    def test_separates_kospi_and_kosdaq(self):
        records = [
            {"symbol": "005930", "market": KOSPI, "per": 15.2, "pbr": 1.85, "dividend_yield": 1.72},
            {"symbol": "005380", "market": KOSPI, "per": 18.4, "pbr": 1.72, "dividend_yield": 2.05},
            {"symbol": "247540", "market": KOSDAQ, "per": 32.1, "pbr": 3.40, "dividend_yield": 0.10},
        ]
        medians = MarketValuation.calculate_medians(records)

        assert KOSPI in medians
        assert KOSDAQ in medians
        assert medians[KOSPI]["sample_size"] == 2
        assert medians[KOSDAQ]["sample_size"] == 1
        # KOSPI와 KOSDAQ이 절대 하나로 합쳐지지 않아야 함
        assert medians[KOSPI]["per_median"] != medians[KOSDAQ]["per_median"]

    def test_median_calculation_is_correct(self):
        records = [
            {"symbol": "A", "market": KOSPI, "per": 10, "pbr": 1.0, "dividend_yield": 1.0},
            {"symbol": "B", "market": KOSPI, "per": 20, "pbr": 2.0, "dividend_yield": 2.0},
            {"symbol": "C", "market": KOSPI, "per": 30, "pbr": 3.0, "dividend_yield": 3.0},
        ]
        medians = MarketValuation.calculate_medians(records)
        assert medians[KOSPI]["per_median"] == 20
        assert medians[KOSPI]["pbr_median"] == 2.0
        assert medians[KOSPI]["dividend_median"] == 2.0

    def test_invalid_and_missing_values_excluded(self):
        records = [
            {"symbol": "A", "market": KOSPI, "per": 10, "pbr": 1.0, "dividend_yield": 1.0},
            {"symbol": "B", "market": KOSPI, "per": None, "pbr": 0, "dividend_yield": -5},
            {"symbol": "C", "market": KOSPI, "per": 30, "pbr": 3.0, "dividend_yield": 3.0},
        ]
        medians = MarketValuation.calculate_medians(records)
        # None/0/음수는 제외되고 유효한 A, C만으로 중앙값 계산
        assert medians[KOSPI]["per_median"] == 20  # median(10, 30)
        assert medians[KOSPI]["sample_size"] == 3  # sample_size는 전체 레코드 수 기준

    def test_market_with_no_valid_data_is_excluded(self):
        records = [
            {"symbol": "A", "market": KOSPI, "per": 10, "pbr": 1.0, "dividend_yield": 1.0},
            {"symbol": "B", "market": KOSDAQ, "per": None, "pbr": None, "dividend_yield": None},
        ]
        medians = MarketValuation.calculate_medians(records)
        assert KOSPI in medians
        assert KOSDAQ not in medians

    def test_records_without_market_are_skipped(self):
        records = [
            {"symbol": "A", "per": 10, "pbr": 1.0, "dividend_yield": 1.0},  # market 없음
        ]
        medians = MarketValuation.calculate_medians(records)
        assert medians == {}

    def test_empty_input_returns_empty_dict(self):
        assert MarketValuation.calculate_medians([]) == {}


class TestGetMarketBaseline:
    def test_returns_valuation_analyzer_compatible_keys(self):
        records = [
            {"symbol": "A", "market": KOSPI, "per": 18.4, "pbr": 1.72, "dividend_yield": 2.05},
        ]
        medians = MarketValuation.calculate_medians(records)
        baseline = MarketValuation.get_market_baseline(medians, KOSPI)

        assert baseline == {
            "market_per": 18.4,
            "market_pbr": 1.72,
            "market_dividend_yield": 2.05,
        }

    def test_unknown_market_returns_all_none(self):
        baseline = MarketValuation.get_market_baseline({}, KOSPI)
        assert baseline == {
            "market_per": None,
            "market_pbr": None,
            "market_dividend_yield": None,
        }
