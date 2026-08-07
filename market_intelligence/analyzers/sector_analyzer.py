from market_intelligence.base_analyzer import BaseAnalyzer
from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)

class SectorAnalyzer(BaseAnalyzer):
    """업종 분석기 (한국 주식 시장, 2026년 8월 기준)"""
    
    def __init__(self):
        super().__init__(name="sector", weight=0.18)
        
        # 한국 주식 시장 8개 주요 업종 기준값 (2026-08-07)
        self.sectors = {
            "IT_Semiconductor": {
                "display_name": "IT/반도체",
                "base_index": 1500,
                "bull_level": 1650,  # 10% 상승
                "bear_level": 1350,  # 10% 하락
                "weight": 0.25  # KOSPI에서 가장 높은 비중
            },
            "Finance": {
                "display_name": "금융/은행",
                "base_index": 950,
                "bull_level": 1045,  # 10% 상승
                "bear_level": 855,   # 10% 하락
                "weight": 0.15
            },
            "Chemicals_Energy": {
                "display_name": "화학/에너지",
                "base_index": 650,
                "bull_level": 715,
                "bear_level": 585,
                "weight": 0.12
            },
            "Consumer": {
                "display_name": "소비재/유통",
                "base_index": 800,
                "bull_level": 880,
                "bear_level": 720,
                "weight": 0.12
            },
            "Telecom_Media": {
                "display_name": "통신/미디어",
                "base_index": 700,
                "bull_level": 770,
                "bear_level": 630,
                "weight": 0.08
            },
            "Healthcare_Pharma": {
                "display_name": "의료/제약",
                "base_index": 1200,
                "bull_level": 1320,
                "bear_level": 1080,
                "weight": 0.10
            },
            "Construction_Real_Estate": {
                "display_name": "건설/부동산",
                "base_index": 550,
                "bull_level": 605,
                "bear_level": 495,
                "weight": 0.10
            },
            "Secondary_Battery": {
                "display_name": "2차전지/ESG",
                "base_index": 900,
                "bull_level": 990,
                "bear_level": 810,
                "weight": 0.08
            }
        }
    
    def validate(self, data: Dict[str, Any]) -> bool:
        """입력 데이터 검증"""
        # 최소 4개 이상의 업종 데이터 필요
        required_sectors = [
            "IT_Semiconductor", "Finance", 
            "Healthcare_Pharma", "Secondary_Battery"
        ]
        return all(sector in data for sector in required_sectors)
    
    def analyze(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        한국 주식 시장 업종별 성과 분석
        
        Returns Dict with sector scores and market analysis
        """
        try:
            sector_scores = {}
            sector_details = {}
            
            # 1. 각 업종 점수 계산
            for sector_key, sector_info in self.sectors.items():
                index_value = data.get(sector_key, sector_info["base_index"])
                score = self._analyze_sector(sector_key, index_value)
                
                sector_scores[sector_key] = score
                sector_details[sector_key] = {
                    "display_name": sector_info["display_name"],
                    "index": index_value,
                    "score": score,
                    "weight": sector_info["weight"]
                }
            
            # 2. 강한 업종/약한 업종 식별
            strongest = max(sector_scores.items(), key=lambda x: x[1])
            weakest = min(sector_scores.items(), key=lambda x: x[1])
            
            # 3. 평균 업종 점수
            avg_sector_score = sum(sector_scores.values()) / len(sector_scores)
            
            # 4. 가중 평균 (업종별 시장 비중 고려)
            weighted_score = sum(
                sector_scores[sector] * self.sectors[sector]["weight"]
                for sector in sector_scores
            ) / sum(info["weight"] for info in self.sectors.values())
            
            logger.info(
                f"Sector Analysis: Strongest={strongest[0]}({strongest[1]:.1f}), "
                f"Weakest={weakest[0]}({weakest[1]:.1f}), "
                f"Average={avg_sector_score:.1f}, "
                f"Weighted={weighted_score:.1f}"
            )
            
            return {
                "sector_scores": sector_scores,
                "sector_details": sector_details,
                "strongest_sector": {
                    "name": strongest[0],
                    "display_name": self.sectors[strongest[0]]["display_name"],
                    "score": strongest[1]
                },
                "weakest_sector": {
                    "name": weakest[0],
                    "display_name": self.sectors[weakest[0]]["display_name"],
                    "score": weakest[1]
                },
                "average_score": avg_sector_score,
                "weighted_score": weighted_score,
                "sector_count": len(sector_scores)
            }
            
        except Exception as e:
            logger.error(f"Sector analysis error: {e}")
            return {
                "sector_scores": {},
                "error": str(e),
                "weighted_score": 0
            }
    
    def get_score(self, analysis_result: Dict[str, Any]) -> float:
        """
        분석 결과로부터 최종 업종 점수 계산
        
        Args:
            analysis_result: analyze() 반환값 (Dict)
        
        Returns:
            0~100 정규화된 점수
        """
        try:
            # weighted_score를 그대로 반환 (이미 0~100 범위)
            score = analysis_result.get("weighted_score", 0)
            score = max(0, min(100, score))  # 0~100 범위 보장
            
            strongest = analysis_result.get("strongest_sector", {})
            weakest = analysis_result.get("weakest_sector", {})
            
            logger.info(
                f"Sector final score: Strongest={strongest.get('display_name')}({strongest.get('score', 0):.1f}), "
                f"Weakest={weakest.get('display_name')}({weakest.get('score', 0):.1f}) "
                f"→ {score:.1f}"
            )
            
            return score
            
        except Exception as e:
            logger.error(f"Score calculation error: {e}")
            return 0.0
    
    def _analyze_sector(self, sector_key: str, index_value: float) -> float:
        """
        개별 업종 지수 분석
        
        Args:
            sector_key: 업종 키
            index_value: 업종 지수값
        
        Returns:
            0~100 정규화된 업종 점수
        """
        sector_info = self.sectors[sector_key]
        base = sector_info["base_index"]
        bull_level = sector_info["bull_level"]
        bear_level = sector_info["bear_level"]
        
        # 3단계 분석
        if index_value >= bull_level:
            # 강세: bull_level 이상 → 75~100
            return min(100, 75 + (index_value - bull_level) / (bull_level * 0.1))
        elif index_value >= base:
            # 중간~강세: base~bull_level → 50~75
            return 50 + (index_value - base) / (bull_level - base) * 25
        elif index_value >= bear_level:
            # 약세~중간: bear_level~base → 25~50
            return 25 + (index_value - bear_level) / (base - bear_level) * 25
        else:
            # 약세: bear_level 미만 → 0~25
            return max(0, (index_value / bear_level) * 25)