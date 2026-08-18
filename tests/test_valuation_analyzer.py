"""
ValuationAnalyzer 테스트 (Phase 5-5: 시장 대비 상대평가로 전면 교체)

================================================================================
【변경 이력】
================================================================================
【2026-08-14】최초 생성 (Phase 5-2, KISClient 직접 결합 버전 테스트)

【2026-08-14】Phase 5-5 반영 - 전면 재작성
- ValuationAnalyzer가 API를 호출하지 않는 순수 계산기로 바뀌면서 kis_client
  주입/Mock 관련 테스트를 모두 제거하고, 상대평가 로직 자체를 검증하도록 교체
- 검증 대상: 저평가/고평가 판정, 시장 기준값 결측 시 데이터 품질 반영,
  코인 자산 중립 처리, 지표 일부만 있을 때 재정규화
================================================================================
"""

import pytest
from market_intelligence.analyzers.valuation_analyzer import ValuationAnalyzer


class TestValuationAnalyzerInitialization:
    def test_initialization(self):
        analyzer = ValuationAnalyzer()
        assert analyzer.name == "valuation"
        assert analyzer.weight == 0.09


class TestValuationAnalyzerRelativeScoring:
    """시장(KOSPI/KOSDAQ) 중앙값 대비 상대평가 핵심 로직"""

    def test_undervalued_stock_scores_above_neutral(self):
        analyzer = ValuationAnalyzer()
        data = {
            "symbol": "005930", "market": "KOSPI",
            "per": 15.2, "market_per": 18.4,
            "pbr": 1.40, "market_pbr": 1.72,
            "dividend_yield": 2.50, "market_dividend_yield": 2.05,
        }
        result = analyzer.run(data)
        assert result["success"] is True
        assert result["score"] > 50.0
        assert result["details"]["data_source"] == "relative"
        assert result["details"]["data_quality"] == 100.0

    def test_overvalued_stock_scores_below_neutral(self):
        analyzer = ValuationAnalyzer()
        data = {
            "symbol": "247540", "market": "KOSDAQ",
            "per": 40.0, "market_per": 27.8,
            "pbr": 4.50, "market_pbr": 2.31,
            "dividend_yield": 0.10, "market_dividend_yield": 0.82,
        }
        result = analyzer.run(data)
        assert result["score"] < 50.0

    def test_exactly_at_market_median_scores_neutral(self):
        analyzer = ValuationAnalyzer()
        data = {
            "symbol": "005930", "market": "KOSPI",
            "per": 18.4, "market_per": 18.4,
            "pbr": 1.72, "market_pbr": 1.72,
            "dividend_yield": 2.05, "market_dividend_yield": 2.05,
        }
        result = analyzer.run(data)
        assert result["score"] == pytest.approx(50.0, abs=0.01)

    def test_extreme_relative_value_clips_to_0_and_100(self):
        analyzer = ValuationAnalyzer()
        # PER이 시장의 1/10 수준 (극단적 저평가) → 상한 100 근처로 클립
        cheap = {"per": 1.0, "market_per": 18.4}
        # PER이 시장의 5배 (극단적 고평가) → 하한 0 근처로 클립
        expensive = {"per": 90.0, "market_per": 18.4}

        cheap_result = analyzer.run(cheap)
        expensive_result = analyzer.run(expensive)

        assert cheap_result["details"]["per_relative_score"] == 100.0
        assert expensive_result["details"]["per_relative_score"] == 0.0


class TestValuationAnalyzerPartialData:
    """일부 지표만 있을 때 나머지 지표로 재정규화"""

    def test_only_per_available_reweights_to_full_score(self):
        analyzer = ValuationAnalyzer()
        # PBR/배당 시장 기준값이 없어 PER만 계산 가능
        data = {"per": 15.2, "market_per": 18.4}
        result = analyzer.run(data)
        details = result["details"]

        assert details["data_quality"] == pytest.approx(100 / 3, abs=0.1)
        assert details["pbr_relative_score"] is None
        assert details["dividend_relative_score"] is None
        # PER 단독 재정규화 점수와 종합 점수가 같아야 함
        assert result["score"] == pytest.approx(details["per_relative_score"], abs=0.01)

    def test_no_relative_metrics_returns_neutral_with_low_quality(self):
        analyzer = ValuationAnalyzer()
        data = {"symbol": "005930", "per": 15.2, "pbr": 1.4}  # market_* 전부 없음
        result = analyzer.run(data)
        details = result["details"]

        assert result["score"] == 50.0
        assert details["data_source"] == "insufficient_data"
        assert details["data_quality"] == 0.0
        assert details["applicable"] is False


class TestValuationAnalyzerCoinAssets:
    def test_coin_returns_neutral_score(self):
        analyzer = ValuationAnalyzer()
        data = {"symbol": "BTC", "asset_type": "coin"}
        result = analyzer.run(data)

        assert result["score"] == 50.0
        assert result["details"]["applicable"] is False
        assert result["details"]["data_source"] == "not_applicable"

    def test_crypto_alias_also_neutral(self):
        analyzer = ValuationAnalyzer()
        data = {"symbol": "ETH", "asset_type": "crypto"}
        result = analyzer.run(data)
        assert result["score"] == 50.0


class TestValuationAnalyzerEdgeCases:
    def test_zero_or_negative_values_are_treated_as_missing(self):
        analyzer = ValuationAnalyzer()
        data = {"per": 0, "market_per": 18.4, "pbr": -1.2, "market_pbr": 1.72}
        result = analyzer.run(data)
        # per<=0, pbr<=0 이므로 둘 다 계산 불가 → 데이터 부족 처리
        assert result["details"]["data_source"] == "insufficient_data"

    def test_validate_accepts_any_dict(self):
        analyzer = ValuationAnalyzer()
        assert analyzer.validate({}) is True
        assert analyzer.validate({"asset_type": "coin"}) is True
        assert analyzer.validate("not a dict") is False
