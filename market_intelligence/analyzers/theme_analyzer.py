from market_intelligence.base_analyzer import BaseAnalyzer
from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)

class ThemeAnalyzer(BaseAnalyzer):
    """테마 분석기 (한국 주식 시장, 2026년 8월 기준)"""
    
    def __init__(self):
        super().__init__(name="theme", weight=0.14)
        
        # 6가지 주요 시장 테마 (2026-08-07)
        self.themes = {
            "geopolitical_risk": {
                "display_name": "지정학적 리스크",
                "base_score": 50,  # 중립
                "bull_level": 70,  # 위험 감소 = 강세
                "bear_level": 30,  # 위험 증가 = 약세
                "weight": 0.15,
                "current_status": "중동 긴장 고조"
            },
            "ai_semiconductor": {
                "display_name": "AI/반도체",
                "base_score": 50,
                "bull_level": 70,  # AI 수요 증가
                "bear_level": 30,  # AI 수요 둔화
                "weight": 0.20,
                "current_status": "SK하이닉스 약세"
            },
            "esg_battery": {
                "display_name": "ESG/2차전지",
                "base_score": 50,
                "bull_level": 75,  # ESG 투자 확대
                "bear_level": 25,  # ESG 투자 축소
                "weight": 0.18,
                "current_status": "저가 매수심 유입"
            },
            "value_buying": {
                "display_name": "저가 매수/가치투자",
                "base_score": 50,
                "bull_level": 75,  # 강한 매수심
                "bear_level": 25,  # 약한 매수심
                "weight": 0.18,
                "current_status": "기관/개인 매수"
            },
            "economic_recovery": {
                "display_name": "경기 회복/사이클",
                "base_score": 50,
                "bull_level": 70,  # 강한 회복
                "bear_level": 30,  # 약한 회복
                "weight": 0.14,
                "current_status": "약한 회복 신호"
            },
            "tech_innovation": {
                "display_name": "기술 혁신",
                "base_score": 50,
                "bull_level": 75,  # 혁신 가속화
                "bear_level": 25,  # 혁신 정체
                "weight": 0.15,
                "current_status": "장기 성장성"
            }
        }
    
    def validate(self, data: Dict[str, Any]) -> bool:
        """입력 데이터 검증"""
        # 최소 4개 이상의 테마 데이터 필요
        required_themes = [
            "geopolitical_risk", "ai_semiconductor", 
            "esg_battery", "value_buying"
        ]
        return all(theme in data for theme in required_themes)
    
    def analyze(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        시장 테마 분석
        
        Returns Dict with theme scores and market trend analysis
        """
        try:
            theme_scores = {}
            theme_details = {}
            
            # 1. 각 테마별 점수 계산
            for theme_key, theme_info in self.themes.items():
                score = data.get(theme_key, theme_info["base_score"])
                score = max(0, min(100, score))  # 0~100 범위 보장
                
                theme_scores[theme_key] = score
                theme_details[theme_key] = {
                    "display_name": theme_info["display_name"],
                    "score": score,
                    "weight": theme_info["weight"],
                    "status": theme_info["current_status"],
                    "strength": self._get_strength(score)
                }
            
            # 2. 가장 강한/약한 테마 식별
            strongest = max(theme_scores.items(), key=lambda x: x[1])
            weakest = min(theme_scores.items(), key=lambda x: x[1])
            
            # 3. 평균 테마 점수
            avg_theme_score = sum(theme_scores.values()) / len(theme_scores)
            
            # 4. 가중 평균 (테마별 영향력 고려)
            weighted_score = sum(
                theme_scores[theme] * self.themes[theme]["weight"]
                for theme in theme_scores
            ) / sum(info["weight"] for info in self.themes.values())
            
            # 5. 테마 시장 심리 분석
            market_theme = self._analyze_market_theme(theme_scores)
            
            logger.info(
                f"Theme Analysis: Strongest={strongest[0]}({strongest[1]:.1f}), "
                f"Weakest={weakest[0]}({weakest[1]:.1f}), "
                f"Average={avg_theme_score:.1f}, "
                f"Weighted={weighted_score:.1f}, "
                f"Theme={market_theme}"
            )
            
            return {
                "theme_scores": theme_scores,
                "theme_details": theme_details,
                "strongest_theme": {
                    "name": strongest[0],
                    "display_name": self.themes[strongest[0]]["display_name"],
                    "score": strongest[1]
                },
                "weakest_theme": {
                    "name": weakest[0],
                    "display_name": self.themes[weakest[0]]["display_name"],
                    "score": weakest[1]
                },
                "average_score": avg_theme_score,
                "weighted_score": weighted_score,
                "market_theme": market_theme,
                "theme_count": len(theme_scores)
            }
            
        except Exception as e:
            logger.error(f"Theme analysis error: {e}")
            return {
                "theme_scores": {},
                "error": str(e),
                "weighted_score": 0,
                "market_theme": "unknown"
            }
    
    def get_score(self, analysis_result: Dict[str, Any]) -> float:
        """
        분석 결과로부터 최종 테마 점수 계산
        
        Args:
            analysis_result: analyze() 반환값 (Dict)
        
        Returns:
            0~100 정규화된 점수
        """
        try:
            # weighted_score를 그대로 반환 (이미 0~100 범위)
            score = analysis_result.get("weighted_score", 0)
            score = max(0, min(100, score))  # 0~100 범위 보장
            
            strongest = analysis_result.get("strongest_theme", {})
            weakest = analysis_result.get("weakest_theme", {})
            market_theme = analysis_result.get("market_theme", "unknown")
            
            logger.info(
                f"Theme final score: Strongest={strongest.get('display_name')}({strongest.get('score', 0):.1f}), "
                f"Weakest={weakest.get('display_name')}({weakest.get('score', 0):.1f}), "
                f"Market Theme={market_theme} "
                f"→ {score:.1f}"
            )
            
            return score
            
        except Exception as e:
            logger.error(f"Score calculation error: {e}")
            return 0.0
    
    def _get_strength(self, score: float) -> str:
        """점수를 테마 강도로 변환"""
        if score >= 70:
            return "매우 강함"
        elif score >= 55:
            return "강함"
        elif score >= 45:
            return "중립"
        elif score >= 30:
            return "약함"
        else:
            return "매우 약함"
    
    def _analyze_market_theme(self, theme_scores: Dict[str, float]) -> str:
        """
        전체 시장 테마 분석
        
        Args:
            theme_scores: 각 테마별 점수
        
        Returns:
            종합 시장 테마 (성장/가치/방어/위험 등)
        """
        ai_sem_score = theme_scores.get("ai_semiconductor", 50)
        esg_bat_score = theme_scores.get("esg_battery", 50)
        value_score = theme_scores.get("value_buying", 50)
        geo_risk_score = theme_scores.get("geopolitical_risk", 50)
        recovery_score = theme_scores.get("economic_recovery", 50)
        tech_score = theme_scores.get("tech_innovation", 50)
        
        # 테마 조합 분석
        growth_themes = ai_sem_score + tech_score  # 성장성
        value_themes = value_score + esg_bat_score  # 가치성
        risk_themes = geo_risk_score  # 위험성
        recovery_themes = recovery_score  # 회복성
        
        # 종합 판단
        if growth_themes >= 140 and geo_risk_score >= 60:
            return "성장+안전형 (양호)"
        elif value_themes >= 140 and value_score >= 65:
            return "가치투자 기회 (매매 신호)"
        elif geo_risk_score <= 40 and recovery_score <= 40:
            return "위험 관리 필요 (방어적)"
        elif growth_themes >= 140:
            return "성장 모멘텀 (공격적)"
        elif value_themes >= 140:
            return "가치 회복 (기회)"
        elif geo_risk_score <= 30:
            return "극도의 위험 (회피 권장)"
        elif recovery_score >= 65 and geo_risk_score >= 60:
            return "회복 기대 (낙관적)"
        else:
            avg_score = sum(theme_scores.values()) / len(theme_scores)
            if avg_score >= 60:
                return "긍정적 테마 우위"
            elif avg_score >= 40:
                return "중립 테마 혼합"
            else:
                return "부정적 테마 우위"
    
    def _analyze_theme_rotation(self, theme_scores: Dict[str, float]) -> Dict[str, str]:
        """
        테마 회전 추세 분석 (향후 확장용)
        
        Args:
            theme_scores: 각 테마별 점수
        
        Returns:
            테마별 강도 변화 추세
        """
        rotation = {}
        for theme_key, score in theme_scores.items():
            if score >= 70:
                rotation[theme_key] = "강세 상승"
            elif score >= 55:
                rotation[theme_key] = "약한 상승"
            elif score >= 45:
                rotation[theme_key] = "중립"
            elif score >= 30:
                rotation[theme_key] = "약한 하락"
            else:
                rotation[theme_key] = "강세 하락"
        
        return rotation