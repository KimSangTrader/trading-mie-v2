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
        self.last_run_time: Optional[datetime] = None
        self.last_results: Optional[Dict[str, Any]] = None  # ← 추가!
        
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
        모든 등록된 분석기 실행
        
        Args:
            data: 분석 데이터
        
        Returns:
            모든 분석기의 결과 종합
        """
        logger.info(f"Running {len(self.analyzers)} analyzers...")
        
        individual_scores = {}
        total_weighted_score = 0
        total_weight = 0
        errors = []
        success_count = 0
        fail_count = 0  # ← fail_count로 변경!
        
        try:
            # 1. 각 분석기 실행
            for analyzer_name, analyzer in self.analyzers.items():
                try:
                    # validate 확인
                    if not analyzer.validate(data):
                        logger.warning(f"Validation failed for {analyzer_name}")
                        fail_count += 1  # ← fail_count로 변경!
                        continue
                    
                    # analyze 실행
                    result = analyzer.run(data)
                    
                    score = result.get("score", 0)
                    weight = analyzer.weight
                    
                    individual_scores[analyzer_name] = {
                        "score": score,
                        "weight": weight,
                        "timestamp": result.get("timestamp")
                    }
                    
                    total_weighted_score += score * weight
                    total_weight += weight
                    success_count += 1
                    
                except Exception as e:
                    logger.error(f"Error in {analyzer_name}: {str(e)}")
                    errors.append({
                        "analyzer": analyzer_name,
                        "error": str(e)
                    })
                    fail_count += 1  # ← fail_count로 변경!
            
            # 2. 최종 점수 계산
            if total_weight > 0:
                final_score = total_weighted_score / total_weight
            else:
                final_score = 0
            
            # 3. 결과 저장
            self.last_run_time = datetime.utcnow()
            self.last_results = {
                "success": True,
                "error": None,
                "individual_scores": individual_scores,
                "final_score": final_score,
                "total_weight": total_weight,
                "success_count": success_count,
                "fail_count": fail_count,
                "total_analyzers": len(self.analyzers),  # ← 추가!
                "analyzed_at": self.last_run_time.isoformat(),
                "errors": errors if errors else None
            }
            
            return self.last_results
            
        except Exception as e:
            logger.error(f"run_all() failed: {str(e)}")
            self.last_run_time = datetime.utcnow()
            result = {
                "success": False,
                "error": str(e),
                "individual_scores": {},
                "final_score": 0,
                "success_count": 0,
                "fail_count": len(self.analyzers),
                "total_analyzers": len(self.analyzers),  # ← 추가!
                "analyzed_at": self.last_run_time.isoformat()
            }
            self.last_results = result
            return result
        
    def get_summary(self) -> Dict[str, Any]:
        """
        최종 분석 결과 요약 반환
        
        Returns:
            최종 점수, 타임스탐프, 에러 포함
        """
        if self.last_results is None:
            return {"error": "No analysis has been run yet"}
        
        return {
            "final_score": self.last_results.get("final_score", 0),
            "success": self.last_results.get("success", False),
            "success_count": self.last_results.get("success_count", 0),
            "fail_count": self.last_results.get("fail_count", 0),
            "analyzers_run": self.last_results.get("success_count", 0),  # ← 추가!
            "analyzed_at": self.last_results.get("analyzed_at"),
            "individual_scores": self.last_results.get("individual_scores", {}),
            "errors": self.last_results.get("errors")
        }
    
    def get_analyzer(self, name: str) -> BaseAnalyzer:
        """분석기 조회"""
        return self.analyzers.get(name)
    
    def list_analyzers(self) -> List[str]:
        """등록된 분석기 목록"""
        return list(self.analyzers.keys())