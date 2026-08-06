from abc import ABC, abstractmethod
from typing import Dict, Any, List
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class BaseAnalyzer(ABC):
    """
    모든 분석기의 기본 클래스
    
    각 분석기는 이 클래스를 상속받아 다음을 구현해야 함:
    - analyze(): 분석 수행
    - validate(): 데이터 검증
    - get_score(): 점수 계산
    """
    
    def __init__(self, name: str, weight: float = 1.0):
        """
        초기화
        
        Args:
            name: 분석기 이름 (예: "market", "sector", "moneyflow")
            weight: 최종 점수에 대한 가중치 (0~1)
        """
        self.name = name
        self.weight = weight
        self.last_analysis_time = None
        self.last_score = None
        self.errors = []
        
    def run(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        분석 수행 (메인 진입점)
        
        Args:
            data: 분석에 필요한 데이터
            
        Returns:
            분석 결과 (score, details, timestamp)
        """
        try:
            # 1. 데이터 검증
            if not self.validate(data):
                raise ValueError(f"Data validation failed for {self.name}")
            
            # 2. 분석 수행
            result = self.analyze(data)
            
            # 3. 점수 계산
            score = self.get_score(result)
            
            # 4. 결과 반환
            return {
                "analyzer": self.name,
                "score": score,
                "weight": self.weight,
                "details": result,
                "timestamp": datetime.utcnow().isoformat(),
                "success": True
            }
            
        except Exception as e:
            logger.error(f"Error in {self.name}: {str(e)}")
            self.errors.append(str(e))
            return {
                "analyzer": self.name,
                "score": 0,
                "weight": self.weight,
                "details": {},
                "timestamp": datetime.utcnow().isoformat(),
                "success": False,
                "error": str(e)
            }
    
    @abstractmethod
    def validate(self, data: Dict[str, Any]) -> bool:
        """
        데이터 검증 (자식 클래스에서 구현)
        
        Args:
            data: 분석 데이터
            
        Returns:
            검증 성공 여부
        """
        pass
    
    @abstractmethod
    def analyze(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        실제 분석 수행 (자식 클래스에서 구현)
        
        Args:
            data: 분석 데이터
            
        Returns:
            분석 결과 상세 정보
        """
        pass
    
    @abstractmethod
    def get_score(self, analysis_result: Dict[str, Any]) -> float:
        """
        분석 결과로부터 점수 계산 (자식 클래스에서 구현)
        
        Args:
            analysis_result: analyze() 반환값
            
        Returns:
            0~100 사이의 점수
        """
        pass
    
    def get_error_summary(self) -> List[str]:
        """에러 목록 반환"""
        return self.errors
    
    def reset_errors(self):
        """에러 목록 초기화"""
        self.errors = []


class ScoreResult:
    """점수 결과를 담는 클래스"""
    
    def __init__(self, score: float, details: Dict[str, Any] = None):
        """
        초기화
        
        Args:
            score: 0~100 점수
            details: 추가 정보
        """
        self.score = max(0, min(100, score))  # 0~100 범위로 정규화
        self.details = details or {}
        self.timestamp = datetime.utcnow()
    
    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리로 변환"""
        return {
            "score": self.score,
            "details": self.details,
            "timestamp": self.timestamp.isoformat()
        }