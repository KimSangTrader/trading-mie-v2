import pytest
from market_intelligence.base_analyzer import BaseAnalyzer, ScoreResult
from typing import Dict, Any


class MockAnalyzer(BaseAnalyzer):
    """테스트용 Mock 분석기"""
    
    def __init__(self):
        super().__init__(name="test", weight=0.5)
    
    def validate(self, data: Dict[str, Any]) -> bool:
        return "test_value" in data
    
    def analyze(self, data: Dict[str, Any]) -> Dict[str, Any]:
        return {"result": data["test_value"] * 2}
    
    def get_score(self, analysis_result: Dict[str, Any]) -> float:
        return 75.0


class TestBaseAnalyzer:
    """BaseAnalyzer 테스트"""
    
    def test_analyzer_initialization(self):
        """분석기 초기화 테스트"""
        analyzer = MockAnalyzer()
        assert analyzer.name == "test"
        assert analyzer.weight == 0.5
    
    def test_valid_data(self):
        """올바른 데이터 처리 테스트"""
        analyzer = MockAnalyzer()
        data = {"test_value": 10}
        
        result = analyzer.run(data)
        
        assert result["success"] is True
        assert result["score"] == 75.0
        assert result["weight"] == 0.5
        assert result["analyzer"] == "test"
    
    def test_invalid_data(self):
        """잘못된 데이터 처리 테스트"""
        analyzer = MockAnalyzer()
        data = {"wrong_key": 10}
        
        result = analyzer.run(data)
        
        assert result["success"] is False
        assert result["error"] is not None
        assert result["score"] == 0
    
    def test_score_normalization(self):
        """점수 정규화 테스트"""
        # 100 초과
        score = ScoreResult(150.0)
        assert score.score == 100.0
        
        # 0 미만
        score = ScoreResult(-50.0)
        assert score.score == 0.0
        
        # 정상 범위
        score = ScoreResult(75.5)
        assert score.score == 75.5
    
    def test_analyzer_errors(self):
        """에러 처리 테스트"""
        analyzer = MockAnalyzer()
        
        # 에러 발생
        analyzer.run({"wrong_key": 10})
        
        # 에러 목록 확인
        errors = analyzer.get_error_summary()
        assert len(errors) > 0
        
        # 에러 초기화
        analyzer.reset_errors()
        assert len(analyzer.get_error_summary()) == 0


class TestScoreResult:
    """ScoreResult 테스트"""
    
    def test_score_result_creation(self):
        """ScoreResult 생성 테스트"""
        result = ScoreResult(85.5, {"detail": "info"})
        assert result.score == 85.5
        assert result.details["detail"] == "info"
    
    def test_score_result_to_dict(self):
        """ScoreResult 딕셔너리 변환 테스트"""
        result = ScoreResult(85.5)
        data = result.to_dict()
        
        assert data["score"] == 85.5
        assert "timestamp" in data
        assert "details" in data