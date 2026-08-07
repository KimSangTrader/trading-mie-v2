from market_intelligence.base_analyzer import BaseAnalyzer
from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)

class MoneyFlowAnalyzer(BaseAnalyzer):
    """수급 동향 분석기 (한국 주식 시장, 2026년 8월 기준)"""
    
    def __init__(self):
        super().__init__(name="moneyflow", weight=0.14)
        
        # 수급 주체별 기준값 (2026-08-07)
        self.money_flows = {
            "foreign": {
                "display_name": "외국인",
                "base_volume": 0,  # 0 = 중립
                "bull_level": 5000000000,  # 500억 순매수 = 강세
                "bear_level": -5000000000,  # -500억 순매도 = 약세
                "weight": 0.40  # 가장 영향력 있음
            },
            "institutional": {
                "display_name": "기관",
                "base_volume": 0,
                "bull_level": 3000000000,  # 300억 순매수
                "bear_level": -3000000000,  # -300억 순매도
                "weight": 0.30
            },
            "retail": {
                "display_name": "개인",
                "base_volume": 0,
                "bull_level": 2000000000,  # 200억 순매수
                "bear_level": -2000000000,  # -200억 순매도
                "weight": 0.20
            },
            "program": {
                "display_name": "프로그램",
                "base_volume": 0,
                "bull_level": 1000000000,  # 100억 순매수
                "bear_level": -1000000000,  # -100억 순매도
                "weight": 0.10
            }
        }
    
    def validate(self, data: Dict[str, Any]) -> bool:
        """입력 데이터 검증"""
        # 최소 3개 이상의 수급 데이터 필수 (외국인, 기관, 개인)
        required_flows = ["foreign", "institutional", "retail"]
        return all(flow in data for flow in required_flows)
    
    def analyze(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        한국 주식 시장 수급 동향 분석
        
        Returns Dict with moneyflow scores and sentiment analysis
        """
        try:
            flow_scores = {}
            flow_details = {}
            
            # 1. 각 수급 주체별 점수 계산
            for flow_key, flow_info in self.money_flows.items():
                volume = data.get(flow_key, flow_info["base_volume"])
                score = self._analyze_flow(flow_key, volume)
                
                flow_scores[flow_key] = score
                flow_details[flow_key] = {
                    "display_name": flow_info["display_name"],
                    "volume": volume,
                    "volume_billion": volume / 1000000000,  # 억 단위로 변환
                    "score": score,
                    "weight": flow_info["weight"],
                    "sentiment": self._get_sentiment(score)
                }
            
            # 2. 가장 강한/약한 수급 주체 식별
            strongest = max(flow_scores.items(), key=lambda x: x[1])
            weakest = min(flow_scores.items(), key=lambda x: x[1])
            
            # 3. 평균 수급 점수
            avg_flow_score = sum(flow_scores.values()) / len(flow_scores)
            
            # 4. 가중 평균 (수급 주체별 영향력 고려)
            weighted_score = sum(
                flow_scores[flow] * self.money_flows[flow]["weight"]
                for flow in flow_scores
            ) / sum(info["weight"] for info in self.money_flows.values())
            
            # 5. 수급 심리 분석
            sentiment = self._analyze_sentiment(flow_scores)
            
            logger.info(
                f"MoneyFlow Analysis: Strongest={strongest[0]}({strongest[1]:.1f}), "
                f"Weakest={weakest[0]}({weakest[1]:.1f}), "
                f"Average={avg_flow_score:.1f}, "
                f"Weighted={weighted_score:.1f}, "
                f"Sentiment={sentiment}"
            )
            
            return {
                "flow_scores": flow_scores,
                "flow_details": flow_details,
                "strongest_flow": {
                    "name": strongest[0],
                    "display_name": self.money_flows[strongest[0]]["display_name"],
                    "score": strongest[1]
                },
                "weakest_flow": {
                    "name": weakest[0],
                    "display_name": self.money_flows[weakest[0]]["display_name"],
                    "score": weakest[1]
                },
                "average_score": avg_flow_score,
                "weighted_score": weighted_score,
                "sentiment": sentiment,
                "flow_count": len(flow_scores)
            }
            
        except Exception as e:
            logger.error(f"MoneyFlow analysis error: {e}")
            return {
                "flow_scores": {},
                "error": str(e),
                "weighted_score": 0,
                "sentiment": "unknown"
            }
    
    def get_score(self, analysis_result: Dict[str, Any]) -> float:
        """
        분석 결과로부터 최종 수급 점수 계산
        
        Args:
            analysis_result: analyze() 반환값 (Dict)
        
        Returns:
            0~100 정규화된 점수
        """
        try:
            # weighted_score를 그대로 반환 (이미 0~100 범위)
            score = analysis_result.get("weighted_score", 0)
            score = max(0, min(100, score))  # 0~100 범위 보장
            
            strongest = analysis_result.get("strongest_flow", {})
            weakest = analysis_result.get("weakest_flow", {})
            sentiment = analysis_result.get("sentiment", "unknown")
            
            logger.info(
                f"MoneyFlow final score: Strongest={strongest.get('display_name')}({strongest.get('score', 0):.1f}), "
                f"Weakest={weakest.get('display_name')}({weakest.get('score', 0):.1f}), "
                f"Sentiment={sentiment} "
                f"→ {score:.1f}"
            )
            
            return score
            
        except Exception as e:
            logger.error(f"Score calculation error: {e}")
            return 0.0
    
    def _analyze_flow(self, flow_key: str, volume: float) -> float:
        """
        개별 수급 주체 분석
        
        Args:
            flow_key: 수급 주체 키 (foreign, institutional, retail, program)
            volume: 수급량 (양수=매수, 음수=매도)
        
        Returns:
            0~100 정규화된 수급 점수
        """
        flow_info = self.money_flows[flow_key]
        base = flow_info["base_volume"]
        bull_level = flow_info["bull_level"]
        bear_level = flow_info["bear_level"]
        
        # 3단계 분석
        if volume >= bull_level:
            # 강한 매수: bull_level 이상 → 75~100
            return min(100, 75 + (volume - bull_level) / (bull_level * 0.2))
        elif volume >= base:
            # 약한 매수: base~bull_level → 50~75
            return 50 + (volume - base) / (bull_level - base) * 25
        elif volume >= bear_level:
            # 약한 매도: bear_level~base → 25~50
            return 25 + (volume - bear_level) / (base - bear_level) * 25
        else:
            # 강한 매도: bear_level 미만 → 0~25
            return max(0, (volume / bear_level) * 25)
    
    def _get_sentiment(self, score: float) -> str:
        """점수를 감정(심리)으로 변환"""
        if score >= 70:
            return "강한 매수"
        elif score >= 55:
            return "약한 매수"
        elif score >= 45:
            return "중립"
        elif score >= 30:
            return "약한 매도"
        else:
            return "강한 매도"
    
    def _analyze_sentiment(self, flow_scores: Dict[str, float]) -> str:
        """
        전체 수급 심리 분석
        
        Args:
            flow_scores: 각 수급 주체별 점수
        
        Returns:
            종합 시장 심리 (강매수/약매수/중립/약매도/강매도)
        """
        foreign_score = flow_scores.get("foreign", 50)
        institutional_score = flow_scores.get("institutional", 50)
        retail_score = flow_scores.get("retail", 50)
        
        # 수급 심리 분석 로직
        if foreign_score < 40 and institutional_score >= 60 and retail_score >= 60:
            return "하한선 지지 신호"  # 외국인 매도, 기관/개인 매수
        elif foreign_score >= 60 and institutional_score < 40:
            return "상한선 저항 신호"  # 외국인 매수, 기관 매도
        elif foreign_score >= 60 and institutional_score >= 60 and retail_score >= 60:
            return "강한 상승 신호"  # 모두 매수
        elif foreign_score < 40 and institutional_score < 40 and retail_score < 40:
            return "강한 하락 신호"  # 모두 매도
        else:
            avg_score = sum(flow_scores.values()) / len(flow_scores)
            if avg_score >= 60:
                return "약한 상승 신호"
            elif avg_score >= 40:
                return "중립 신호"
            else:
                return "약한 하락 신호"