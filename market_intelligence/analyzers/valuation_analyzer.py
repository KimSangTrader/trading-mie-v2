"""
ValuationAnalyzer - 기본분석 모듈 (Phase 4)
PER, PBR, 배당수익률 등 기본분석 지표

# valuation_analyzer.py 라인 28 수정
# 【2026-08-13 수정】weight 0.25 → 0.09로 변경

# 이전: super().__init__(name='valuation', weight=0.25)
# 현재: super().__init__(name='valuation', weight=0.09)
"""

import sys
import os
from typing import Dict, Any
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from market_intelligence.base_analyzer import BaseAnalyzer

logger = logging.getLogger(__name__)


class ValuationAnalyzer(BaseAnalyzer):
    """기본분석 모듈 - PER, PBR, 배당수익률 등"""
    
    def __init__(self):
        super().__init__(name="valuation", weight=0.09)
        logger.info(f"✅ ValuationAnalyzer 초기화 완료 (weight={self.weight})")
    
    def validate(self, data: Dict[str, Any]) -> bool:
        """데이터 검증"""
        # 최소 필요 필드
        required = ['per', 'pbr', 'dividend_yield']
        return all(field in data for field in required)
    
    def analyze(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """기본분석 수행"""
        per = data.get('per', 15)  # PER (주가수익비율)
        pbr = data.get('pbr', 1.2)  # PBR (주가순자산비율)
        div_yield = data.get('dividend_yield', 2.5)  # 배당수익률
        
        # PER 점수 (낮을수록 좋음)
        per_score = max(0, 100 - per * 3)  # 15 이상이면 낮은 점수
        
        # PBR 점수 (낮을수록 좋음)
        pbr_score = max(0, 100 - pbr * 30)  # 1.0 이상이면 낮은 점수
        
        # 배당수익률 점수 (높을수록 좋음)
        div_score = min(100, div_yield * 15)  # 최대 100
        
        return {
            'per': per,
            'per_score': per_score,
            'pbr': pbr,
            'pbr_score': pbr_score,
            'dividend_yield': div_yield,
            'dividend_score': div_score
        }
    
    def get_score(self, analysis_result: Dict[str, Any]) -> float:
        """종합 점수"""
        per_score = analysis_result.get('per_score', 50)
        pbr_score = analysis_result.get('pbr_score', 50)
        div_score = analysis_result.get('dividend_score', 50)
        
        # 가중평균
        score = (per_score * 0.35 + pbr_score * 0.35 + div_score * 0.30)
        return max(0, min(100, score))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # Mock 데이터
    data = {
        'per': 12.5,  # 저 PER
        'pbr': 1.1,   # 저 PBR
        'dividend_yield': 3.2  # 높은 배당수익률
    }
    
    analyzer = ValuationAnalyzer()
    result = analyzer.run(data)
    
    print(f"기본분석 점수: {result.get('score', 0):.1f}/100")
    print(f"평가: {'매력적' if result.get('score', 0) > 60 else '보통' if result.get('score', 0) > 40 else '과평가'}")
