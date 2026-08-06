import pytest
from market_intelligence.intelligence_manager import IntelligenceManager
from market_intelligence.base_analyzer import BaseAnalyzer
from typing import Dict, Any


class DummyAnalyzer(BaseAnalyzer):
    """테스트용 Dummy 분석기"""
    
    def __init__(self, name: str, score: float = 50.0, weight: float = 1.0):
        super().__init__(name=name, weight=weight)
        self.test_score = score
    
    def validate(self, data: Dict[str, Any]) -> bool:
        return True
    
    def analyze(self, data: Dict[str, Any]) -> Dict[str, Any]:
        return {"test": "data"}
    
    def get_score(self, analysis_result: Dict[str, Any]) -> float:
        return self.test_score


class TestIntelligenceManager:
    """IntelligenceManager 테스트"""
    
    def test_manager_initialization(self):
        """매니저 초기화 테스트"""
        manager = IntelligenceManager()
        assert len(manager.analyzers) == 0
        assert len(manager.final_scores) == 0
    
    def test_register_analyzer(self):
        """분석기 등록 테스트"""
        manager = IntelligenceManager()
        analyzer = DummyAnalyzer("test1", score=50.0, weight=0.5)
        
        manager.register_analyzer(analyzer)
        
        assert "test1" in manager.analyzers
        assert manager.analyzers["test1"] == analyzer
    
    def test_unregister_analyzer(self):
        """분석기 제거 테스트"""
        manager = IntelligenceManager()
        analyzer = DummyAnalyzer("test1")
        
        manager.register_analyzer(analyzer)
        assert "test1" in manager.analyzers
        
        result = manager.unregister_analyzer("test1")
        assert result is True
        assert "test1" not in manager.analyzers
    
    def test_run_all_single_analyzer(self):
        """단일 분석기 실행 테스트"""
        manager = IntelligenceManager()
        analyzer = DummyAnalyzer("market", score=80.0, weight=1.0)
        manager.register_analyzer(analyzer)
        
        data = {"test": "data"}
        result = manager.run_all(data)
        
        assert result["final_score"] == 80.0
        assert result["success_count"] == 1
        assert result["fail_count"] == 0
        assert result["total_analyzers"] == 1
    
    def test_run_all_multiple_analyzers(self):
        """복수 분석기 실행 테스트"""
        manager = IntelligenceManager()
        
        # 3개 분석기 등록
        manager.register_analyzer(DummyAnalyzer("analyzer1", score=60.0, weight=0.2))
        manager.register_analyzer(DummyAnalyzer("analyzer2", score=80.0, weight=0.3))
        manager.register_analyzer(DummyAnalyzer("analyzer3", score=100.0, weight=0.5))
        
        data = {"test": "data"}
        result = manager.run_all(data)
        
        # 가중 평균: (60*0.2 + 80*0.3 + 100*0.5) / (0.2+0.3+0.5)
        # = (12 + 24 + 50) / 1.0 = 86.0
        assert result["final_score"] == 86.0
        assert result["success_count"] == 3
        assert result["fail_count"] == 0
    
    def test_list_analyzers(self):
        """분석기 목록 테스트"""
        manager = IntelligenceManager()
        manager.register_analyzer(DummyAnalyzer("analyzer1"))
        manager.register_analyzer(DummyAnalyzer("analyzer2"))
        
        analyzer_list = manager.list_analyzers()
        
        assert len(analyzer_list) == 2
        assert "analyzer1" in analyzer_list
        assert "analyzer2" in analyzer_list
    
    def test_get_analyzer(self):
        """분석기 조회 테스트"""
        manager = IntelligenceManager()
        analyzer = DummyAnalyzer("test_analyzer")
        manager.register_analyzer(analyzer)
        
        retrieved = manager.get_analyzer("test_analyzer")
        
        assert retrieved == analyzer
        assert retrieved.name == "test_analyzer"
    
    def test_get_summary(self):
        """결과 요약 테스트"""
        manager = IntelligenceManager()
        manager.register_analyzer(DummyAnalyzer("analyzer1", score=75.0))
        
        data = {"test": "data"}
        manager.run_all(data)
        
        summary = manager.get_summary()
        
        assert "final_score" in summary
        assert "analyzed_at" in summary
        assert "analyzers_run" in summary