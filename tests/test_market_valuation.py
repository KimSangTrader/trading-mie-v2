"""
MarketValuation 테스트 (Phase 5-4: KOSPI/KOSDAQ 중앙값 계산)

================================================================================
【변경 이력】
================================================================================
【2026-08-14】최초 생성
- KOSPI/KOSDAQ 분리 계산, 결측값 제외, 표본 없는 시장 제외 검증

【2026-08-24】Phase 5-19: group_by 일반화(Sector별 중앙값) + build_relative_baseline() 검증 추가
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


class TestGroupBySector:
    def test_group_by_sector_computes_per_sector_medians(self):
        records = [
            {"symbol": "A", "sector": "반도체", "per": 10, "pbr": 1.0, "dividend_yield": 1.0},
            {"symbol": "B", "sector": "반도체", "per": 20, "pbr": 2.0, "dividend_yield": 2.0},
            {"symbol": "C", "sector": "이차전지", "per": 40, "pbr": 4.0, "dividend_yield": 0.5},
        ]
        medians = MarketValuation.calculate_medians(records, group_by="sector")
        assert "반도체" in medians
        assert "이차전지" in medians
        assert medians["반도체"]["per_median"] == 15
        assert medians["이차전지"]["per_median"] == 40
        # 서로 다른 Sector는 절대 섞이지 않아야 함(KOSPI/KOSDAQ 분리 원칙과 동일)
        assert medians["반도체"]["per_median"] != medians["이차전지"]["per_median"]

    def test_default_group_by_is_still_market(self):
        # group_by 인자를 안 주면 기존 동작(시장별) 그대로 - 하위 호환
        records = [{"symbol": "A", "market": KOSPI, "sector": "반도체", "per": 10, "pbr": 1.0, "dividend_yield": 1.0}]
        medians = MarketValuation.calculate_medians(records)
        assert KOSPI in medians
        assert "반도체" not in medians

    def test_valid_count_excludes_missing_and_invalid_values(self):
        records = [
            {"symbol": "A", "sector": "반도체", "per": 10, "pbr": 1.0, "dividend_yield": 1.0},
            {"symbol": "B", "sector": "반도체", "per": None, "pbr": 0, "dividend_yield": -5},
            {"symbol": "C", "sector": "반도체", "per": 30, "pbr": 3.0, "dividend_yield": 3.0},
        ]
        medians = MarketValuation.calculate_medians(records, group_by="sector")
        # sample_size는 전체 레코드 수(3), valid_count는 실제 유효값 개수(per=2, pbr=2, dividend=2)
        assert medians["반도체"]["sample_size"] == 3
        assert medians["반도체"]["per_valid_count"] == 2
        assert medians["반도체"]["pbr_valid_count"] == 2
        assert medians["반도체"]["dividend_valid_count"] == 2

    def test_records_without_sector_are_skipped_when_grouping_by_sector(self):
        records = [{"symbol": "A", "per": 10, "pbr": 1.0, "dividend_yield": 1.0}]  # sector 없음
        medians = MarketValuation.calculate_medians(records, group_by="sector")
        assert medians == {}


class TestBuildRelativeBaseline:
    def _sector_medians(self, valid_count=10):
        return {
            "반도체": {
                "per_median": 16.0, "pbr_median": 1.5, "dividend_median": 1.8,
                "sample_size": valid_count,
                "per_valid_count": valid_count, "pbr_valid_count": valid_count,
                "dividend_valid_count": valid_count,
            }
        }

    def _market_medians(self):
        return {
            KOSPI: {
                "per_median": 20.0, "pbr_median": 2.0, "dividend_median": 2.2,
                "sample_size": 500,
                "per_valid_count": 500, "pbr_valid_count": 500, "dividend_valid_count": 500,
            }
        }

    def test_prefers_sector_median_when_sample_sufficient(self):
        baseline, source = MarketValuation.build_relative_baseline(
            self._sector_medians(valid_count=10), self._market_medians(), "반도체", KOSPI
        )
        assert baseline == {"market_per": 16.0, "market_pbr": 1.5, "market_dividend_yield": 1.8}
        assert source == "sector"

    def test_falls_back_to_market_when_sector_sample_too_small(self):
        baseline, source = MarketValuation.build_relative_baseline(
            self._sector_medians(valid_count=2), self._market_medians(), "반도체", KOSPI,
            min_sector_valid_samples=5,
        )
        assert baseline == {"market_per": 20.0, "market_pbr": 2.0, "market_dividend_yield": 2.2}
        assert source == "market"

    def test_falls_back_to_market_when_sector_unknown(self):
        baseline, source = MarketValuation.build_relative_baseline(
            self._sector_medians(), self._market_medians(), None, KOSPI
        )
        assert baseline == {"market_per": 20.0, "market_pbr": 2.0, "market_dividend_yield": 2.2}
        assert source == "market"

    def test_mixed_source_when_only_some_sector_metrics_reliable(self):
        sector_medians = {
            "반도체": {
                "per_median": 16.0, "pbr_median": None, "dividend_median": 1.8,
                "sample_size": 10, "per_valid_count": 10, "pbr_valid_count": 0,
                "dividend_valid_count": 10,
            }
        }
        baseline, source = MarketValuation.build_relative_baseline(
            sector_medians, self._market_medians(), "반도체", KOSPI
        )
        # pbr만 sector 중앙값이 없어서 시장값으로 대체, per/dividend는 sector 값 유지
        assert baseline == {"market_per": 16.0, "market_pbr": 2.0, "market_dividend_yield": 1.8}
        assert source == "mixed"

    def test_none_when_neither_sector_nor_market_available(self):
        baseline, source = MarketValuation.build_relative_baseline({}, {}, "반도체", KOSPI)
        assert baseline == {"market_per": None, "market_pbr": None, "market_dividend_yield": None}
        assert source == "none"
