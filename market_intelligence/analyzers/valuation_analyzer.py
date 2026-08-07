from market_intelligence.base_analyzer import BaseAnalyzer
from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)

class ValuationAnalyzer(BaseAnalyzer):
    """가치 분석기 (한국 주식 시장, 2026년 8월 기준)"""
    
    def __init__(self):
        super().__init__(name="valuation", weight=0.09)
        
        # 가치 평가 지표 설정
        self.valuation_metrics = {
            "per": {
                "display_name": "PER (주가수익비율)",
                "description": "Price to Earnings Ratio",
                "market_average": 15.0,  # 시장 평균 15배
                "weight": 0.35,
                "current_value": 12.0,
                "current_status": "저평가"
            },
            "pbr": {
                "display_name": "PBR (주가순자산비율)",
                "description": "Price to Book Ratio",
                "market_average": 1.2,
                "weight": 0.25,
                "current_value": 1.0,
                "current_status": "저평가~평가"
            },
            "growth": {
                "display_name": "성장성",
                "description": "Expected Growth Rate",
                "market_average": 5.0,
                "weight": 0.25,
                "current_value": 4.0,
                "current_status": "저성장"
            },
            "dividend_yield": {
                "display_name": "배당률",
                "description": "Dividend Yield",
                "market_average": 2.5,
                "weight": 0.15,
                "current_value": 3.5,
                "current_status": "양호"
            }
        }
    
    def validate(self, data: Dict[str, Any]) -> bool:
        """입력 데이터 검증"""
        # 최소 2개 이상의 가치 지표 필요
        required_metrics = ["per_value", "pbr_value"]
        return all(key in data for key in required_metrics)
    
    def analyze(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        가치 분석 수행
        
        Returns Dict with valuation scores
        """
        try:
            # 1. PER 분석
            per_score = self._analyze_per(
                data.get("per_value", 12.0),
                data.get("per_average", 15.0)
            )
            
            # 2. PBR 분석
            pbr_score = self._analyze_pbr(
                data.get("pbr_value", 1.0),
                data.get("pbr_average", 1.2)
            )
            
            # 3. 성장성 분석
            growth_score = self._analyze_growth(
                data.get("growth_rate", 4.0),
                data.get("growth_average", 5.0)
            )
            
            # 4. 배당률 분석
            dividend_score = self._analyze_dividend(
                data.get("dividend_yield", 3.5),
                data.get("dividend_average", 2.5)
            )
            
            # 5. 종합 점수 (가중 평균)
            valuation_score = (
                per_score * 0.35 +
                pbr_score * 0.25 +
                growth_score * 0.25 +
                dividend_score * 0.15
            )
            
            # 6. 가치 평가 결론
            valuation = self._classify_valuation(valuation_score)
            
            logger.info(
                f"Valuation Analysis: PER={per_score:.1f}, "
                f"PBR={pbr_score:.1f}, Growth={growth_score:.1f}, "
                f"Dividend={dividend_score:.1f}, Score={valuation_score:.1f}, "
                f"Valuation={valuation}"
            )
            
            return {
                "per_score": per_score,
                "pbr_score": pbr_score,
                "growth_score": growth_score,
                "dividend_score": dividend_score,
                "valuation_score": valuation_score,
                "valuation": valuation,
                "metrics": {
                    "per": {"score": per_score, "value": data.get("per_value", 12.0)},
                    "pbr": {"score": pbr_score, "value": data.get("pbr_value", 1.0)},
                    "growth": {"score": growth_score, "value": data.get("growth_rate", 4.0)},
                    "dividend": {"score": dividend_score, "value": data.get("dividend_yield", 3.5)}
                }
            }
            
        except Exception as e:
            logger.error(f"Valuation analysis error: {e}")
            return {
                "valuation_score": 50,
                "error": str(e),
                "valuation": "unknown"
            }
    
    def get_score(self, analysis_result: Dict[str, Any]) -> float:
        """
        분석 결과로부터 최종 가치 점수 계산
        
        Args:
            analysis_result: analyze() 반환값 (Dict)
        
        Returns:
            0~100 정규화된 점수
        """
        try:
            score = analysis_result.get("valuation_score", 50)
            score = max(0, min(100, score))  # 0~100 범위 보장
            
            valuation = analysis_result.get("valuation", "unknown")
            
            logger.info(
                f"Valuation final score: Rating={valuation}, "
                f"Score={score:.1f}"
            )
            
            return score
            
        except Exception as e:
            logger.error(f"Score calculation error: {e}")
            return 50.0
    
    def _analyze_per(self, per_value: float, per_average: float) -> float:
        """
        PER 분석
        
        Args:
            per_value: 현재 PER
            per_average: 시장 평균 PER
        
        Returns:
            0~100 점수
        """
        # PER 기준:
        # 시장 평균의 70% 이하: 저평가 (70~100)
        # 시장 평균의 70~100%: 평가 (50~70)
        # 시장 평균의 100~130%: 고평가 (30~50)
        # 시장 평균의 130% 이상: 극도의 고평가 (0~30)
        
        ratio = per_value / per_average
        
        if ratio <= 0.7:
            # 저평가
            return 70 + (0.7 - ratio) / 0.7 * 30
        elif ratio <= 1.0:
            # 평가
            return 50 + (1.0 - ratio) / 0.3 * 20
        elif ratio <= 1.3:
            # 고평가
            return 30 + (1.3 - ratio) / 0.3 * 20
        else:
            # 극도의 고평가
            return max(0, 30 - (ratio - 1.3) / 0.7 * 30)
    
    def _analyze_pbr(self, pbr_value: float, pbr_average: float) -> float:
        """
        PBR 분석
        
        Args:
            pbr_value: 현재 PBR
            pbr_average: 시장 평균 PBR
        
        Returns:
            0~100 점수
        """
        # PBR 기준:
        # 0.8 이하: 저평가 (70~100)
        # 0.8~1.2: 평가 (50~70)
        # 1.2~1.5: 고평가 (30~50)
        # 1.5 이상: 극도의 고평가 (0~30)
        
        if pbr_value <= 0.8:
            return 70 + (0.8 - pbr_value) / 0.8 * 30
        elif pbr_value <= 1.2:
            return 50 + (1.2 - pbr_value) / 0.4 * 20
        elif pbr_value <= 1.5:
            return 30 + (1.5 - pbr_value) / 0.3 * 20
        else:
            return max(0, 30 - (pbr_value - 1.5) / 1.0 * 30)
    
    def _analyze_growth(self, growth_rate: float, growth_average: float) -> float:
        """
        성장성 분석
        
        Args:
            growth_rate: 예상 성장률 (%)
            growth_average: 시장 평균 성장률 (%)
        
        Returns:
            0~100 점수
        """
        # 성장성 기준:
        # 시장 평균의 130% 이상: 고성장 (70~100)
        # 시장 평균의 100~130%: 평균 성장 (50~70)
        # 시장 평균의 70~100%: 저성장 (30~50)
        # 시장 평균의 70% 이하: 극도의 저성장 (0~30)
        
        if growth_average == 0:
            return 50  # 기준이 없으면 중립
        
        ratio = growth_rate / growth_average
        
        if ratio >= 1.3:
            return 70 + min(30, (ratio - 1.3) / 0.7 * 30)
        elif ratio >= 1.0:
            return 50 + (ratio - 1.0) / 0.3 * 20
        elif ratio >= 0.7:
            return 30 + (ratio - 0.7) / 0.3 * 20
        else:
            return max(0, 30 - (0.7 - ratio) / 0.7 * 30)
    
    def _analyze_dividend(self, dividend_yield: float, dividend_average: float) -> float:
        """
        배당률 분석
        
        Args:
            dividend_yield: 현재 배당률 (%)
            dividend_average: 시장 평균 배당률 (%)
        
        Returns:
            0~100 점수
        """
        # 배당률 기준:
        # 시장 평균의 150% 이상: 높은 배당 (70~100)
        # 시장 평균의 100~150%: 평균 배당 (50~70)
        # 시장 평균의 50~100%: 낮은 배당 (30~50)
        # 시장 평균의 50% 이하: 극도의 낮은 배당 (0~30)
        
        if dividend_average == 0:
            return 50  # 배당이 없으면 중립
        
        ratio = dividend_yield / dividend_average
        
        if ratio >= 1.5:
            return 70 + min(30, (ratio - 1.5) / 0.5 * 30)
        elif ratio >= 1.0:
            return 50 + (ratio - 1.0) / 0.5 * 20
        elif ratio >= 0.5:
            return 30 + (ratio - 0.5) / 0.5 * 20
        else:
            return max(0, 30 - (0.5 - ratio) / 0.5 * 30)
    
    def _classify_valuation(self, score: float) -> str:
        """가치 평가 분류"""
        if score >= 70:
            return "저평가 (강한 매수)"
        elif score >= 55:
            return "약간 저평가 (매수)"
        elif score >= 45:
            return "적정 평가 (중립)"
        elif score >= 30:
            return "약간 고평가 (매도)"
        else:
            return "고평가 (강한 매도)"