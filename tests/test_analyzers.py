import pytest
from market_intelligence.analyzers import (
    MarketAnalyzer,
    SectorAnalyzer,
    MoneyFlowAnalyzer,
    ThemeAnalyzer,
    NewsAnalyzer,
    TechnicalAnalyzer,
    ValuationAnalyzer
)


class TestMarketAnalyzer:
    """MarketAnalyzer 테스트"""
    
    def test_initialization(self):
        analyzer = MarketAnalyzer()
        assert analyzer.name == "market"
        assert analyzer.weight == 0.18
    
    def test_validate_valid_data(self):
        analyzer = MarketAnalyzer()
        data = {
            "kospi_index": 2500,
            "kosdaq_index": 850,
            "market_volume": 1000000000
        }
        assert analyzer.validate(data) is True
    
    def test_validate_invalid_data(self):
        analyzer = MarketAnalyzer()
        data = {"wrong_key": 100}
        assert analyzer.validate(data) is False


class TestSectorAnalyzer:
    """SectorAnalyzer 테스트"""
    
    def test_initialization(self):
        analyzer = SectorAnalyzer()
        assert analyzer.name == "sector"
        assert analyzer.weight == 0.18


class TestMoneyFlowAnalyzer:
    """MoneyFlowAnalyzer 테스트"""
    
    def test_initialization(self):
        analyzer = MoneyFlowAnalyzer()
        assert analyzer.name == "moneyflow"
        assert analyzer.weight == 0.14


class TestThemeAnalyzer:
    """ThemeAnalyzer 테스트"""
    
    def test_initialization(self):
        analyzer = ThemeAnalyzer()
        assert analyzer.name == "theme"
        assert analyzer.weight == 0.14


class TestNewsAnalyzer:
    """NewsAnalyzer 테스트"""
    
    def test_initialization(self):
        analyzer = NewsAnalyzer()
        assert analyzer.name == "news"
        assert analyzer.weight == 0.09


class TestTechnicalAnalyzer:
    """TechnicalAnalyzer 테스트"""
    
    def test_initialization(self):
        analyzer = TechnicalAnalyzer()
        assert analyzer.name == "technical"
        assert analyzer.weight == 0.18


class TestValuationAnalyzer:
    """ValuationAnalyzer 테스트"""
    
    def test_initialization(self):
        analyzer = ValuationAnalyzer()
        assert analyzer.name == "valuation"
        assert analyzer.weight == 0.09


class TestAllAnalyzers:
    """모든 분석기 통합 테스트"""
    
    def test_all_analyzers_weight_sum(self):
        """모든 분석기 가중치 합계 테스트"""
        analyzers = [
            MarketAnalyzer(),
            SectorAnalyzer(),
            MoneyFlowAnalyzer(),
            ThemeAnalyzer(),
            NewsAnalyzer(),
            TechnicalAnalyzer(),
            ValuationAnalyzer()
        ]
        
        total_weight = sum(a.weight for a in analyzers)
        
        # 가중치 합계가 1.0에 가까워야 함 (100%)
        assert abs(total_weight - 1.0) < 0.01
    
    def test_all_analyzers_runnable(self):
        """모든 분석기 실행 가능 테스트"""
        analyzers = [
            MarketAnalyzer(),
            SectorAnalyzer(),
            MoneyFlowAnalyzer(),
            ThemeAnalyzer(),
            NewsAnalyzer(),
            TechnicalAnalyzer(),
            ValuationAnalyzer()
        ]
        
        # 모든 분석기가 BaseAnalyzer를 상속받았는지 확인
        for analyzer in analyzers:
            assert hasattr(analyzer, "run")
            assert hasattr(analyzer, "validate")
            assert hasattr(analyzer, "analyze")
            assert hasattr(analyzer, "get_score")