from typing import Dict, List, Any
from datetime import datetime
import logging
from market_intelligence.base_analyzer import BaseAnalyzer

logger = logging.getLogger(__name__)


class IntelligenceManager:
    """
    모든 분석기를 관리하는 클래스
    
    책임:
    - 분석기 등록 및 관리
    - 모든 분석기 실행
    - 최종 점수 계산
    - 결과 정렬
    """
    
    def __init__(self):
        """초기화"""
        self.analyzers: Dict[str, BaseAnalyzer] = {}
        self.final_scores: List[Dict[str, Any]] = []
        self.last_run_time = None
        
    def register_analyzer(self, analyzer: BaseAnalyzer) -> None:
        """
        분석기 등록
        
        Args:
            analyzer: BaseAnalyzer를 상속한 분석기
        """
        if analyzer.name in self.analyzers:
            logger.warning(f"Analyzer '{analyzer.name}' already registered. Overwriting...")
        
        self.analyzers[analyzer.name] = analyzer
        logger.info(f"Analyzer '{analyzer.name}' registered (weight: {analyzer.weight})")
    
    def unregister_analyzer(self, name: str) -> bool:
        """
        분석기 제거
        
        Args:
            name: 분석기 이름
            
        Returns:
            제거 성공 여부
        """
        if name in self.analyzers:
            del self.analyzers[name]
            logger.info(f"Analyzer '{name}' unregistered")
            return True
        return False
    
    def run_all(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        모든 분석기 실행
        
        Args:
            data: 모든 분석기에 필요한 데이터
            
        Returns:
            {
                "final_score": float,
                "by_analyzer": [...],
                "timestamp": str,
                "success_count": int,
                "fail_count": int
            }
        """
        logger.info(f"Running {len(self.analyzers)} analyzers...")
        
        results = []
        success_count = 0
        fail_count = 0
        total_weight = 0
        weighted_score = 0
        
        # 1. 모든 분석기 실행
        for name, analyzer in self.analyzers.items():
            result = analyzer.run(data)
            results.append(result)
            
            if result["success"]:
                success_count += 1
                total_weight += result["weight"]
                weighted_score += result["score"] * result["weight"]
            else:
                fail_count += 1
        
        # 2. 최종 점수 계산
        if total_weight > 0:
            final_score = weighted_score / total_weight
        else:
            final_score = 0
        
        # 3. 결과 저장 및 반환
        self.last_run_time = datetime.utcnow()
        self.final_scores = results
        
        return {
            "final_score": round(final_score, 2),
            "by_analyzer": results,
            "timestamp": self.last_run_time.isoformat(),
            "success_count": success_count,
            "fail_count": fail_count,
            "total_analyzers": len(self.analyzers)
        }
    
    def get_summary(self) -> Dict[str, Any]:
        """최근 분석 결과 요약"""
        if not self.final_scores:
            return {"error": "No analysis has been run yet"}
        
        total_weight = sum(r.get("weight", 1) for r in self.final_scores)
        if total_weight == 0:
            final_score = 0
        else:
            final_score = sum(r.get("score", 0) * r.get("weight", 1) 
                             for r in self.final_scores) / total_weight
        
        return {
            "final_score": round(final_score, 2),
            "analyzed_at": self.last_run_time.isoformat() if self.last_run_time else "Not run yet",
            "analyzers_run": len([r for r in self.final_scores if r.get("success")])
        }
    
    def get_analyzer(self, name: str) -> BaseAnalyzer:
        """분석기 조회"""
        return self.analyzers.get(name)
    
    def list_analyzers(self) -> List[str]:
        """등록된 분석기 목록"""
        return list(self.analyzers.keys())