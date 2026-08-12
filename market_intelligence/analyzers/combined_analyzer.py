"""
CombinedAnalyzer - 통합 분석기 (Phase 3)
TechnicalAnalyzer + MarketAnalyzer 결합
최종 신호 자동 생성
"""

import sys
import os
from typing import Dict, Any
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from market_intelligence.base_analyzer import BaseAnalyzer
from market_intelligence.analyzers.technical_analyzer import TechnicalAnalyzer
from market_intelligence.analyzers.market_analyzer import MarketAnalyzer

logger = logging.getLogger(__name__)


class CombinedAnalyzer(BaseAnalyzer):
    """
    통합 분석기
    
    TechnicalAnalyzer (기술지표) + MarketAnalyzer (시장 필터)를 결합
    → 최종 신호 자동 생성
    
    신호 = 기술지표 점수 × 시장 가중치
    """
    
    def __init__(self):
        super().__init__(name="combined", weight=1.0)
        self.technical_analyzer = TechnicalAnalyzer()
        self.market_analyzer = MarketAnalyzer()
        logger.info(f"✅ CombinedAnalyzer 초기화 완료")
    
    def validate(self, data: Dict[str, Any]) -> bool:
        """데이터 검증"""
        # 기술지표 데이터와 시장 데이터 모두 필요
        has_technical = 'closes' in data and len(data.get('closes', [])) >= 60
        has_market = 'kospi_index' in data and 'kosdaq_index' in data
        
        return has_technical and has_market
    
    def analyze(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """통합 분석"""
        # Step 1: 기술지표 분석
        technical_result = self.technical_analyzer.run(data)
        technical_score = technical_result.get('score', 50)
        
        # Step 2: 시장 분석
        market_result = self.market_analyzer.run(data)
        market_multiplier = market_result.get('details', {}).get('signal_multiplier', 1.0)
        
        # Step 3: 통합 신호
        combined_score = technical_score * market_multiplier
        combined_score = max(0, min(100, combined_score))  # 0-100 범위
        
        # Step 4: 신호 판정
        signal = self._generate_signal(combined_score)
        
        result = {
            'technical_score': technical_score,
            'technical_details': technical_result.get('details', {}),
            'market_strength': market_result.get('score', 0),
            'market_regime': market_result.get('details', {}).get('market_regime', 'UNKNOWN'),
            'market_multiplier': market_multiplier,
            'combined_score': combined_score,
            'signal': signal,
            'confidence': self._calculate_confidence(technical_score, market_multiplier)
        }
        
        return result
    
    def get_score(self, analysis_result: Dict[str, Any]) -> float:
        """최종 점수"""
        return analysis_result.get('combined_score', 50)
    
    @staticmethod
    def _generate_signal(score: float) -> str:
        """신호 생성"""
        if score >= 80:
            return "🟢🟢 극강 매수"
        elif score >= 70:
            return "🟢 강한 매수"
        elif score >= 60:
            return "🟢 매수"
        elif score >= 55:
            return "🟡 약한 매수"
        elif score >= 45:
            return "⚪ 중립"
        elif score >= 40:
            return "🟡 약한 매도"
        elif score >= 30:
            return "🔴 매도"
        else:
            return "🔴🔴 극강 매도"
    
    @staticmethod
    def _calculate_confidence(technical_score: float, market_multiplier: float) -> float:
        """신뢰도 계산 (0-100)"""
        # 기술지표가 극단적일수록 신뢰도 높음
        tech_confidence = min(100, abs(technical_score - 50) * 2)
        
        # 시장 배수가 극단적일수록 신뢰도 높음
        mult_confidence = min(100, abs(market_multiplier - 1.0) * 100)
        
        # 종합 신뢰도
        confidence = (tech_confidence + mult_confidence) / 2
        return max(0, min(100, confidence))


if __name__ == "__main__":
    import json
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Mock 데이터
    data = {
        'symbol': '0001',
        'dates': ['20260812'] * 60,
        'opens': [7500] * 60,
        'highs': [7600] * 60,
        'lows': [7400] * 60,
        'closes': [7516.04] + [7510] * 59,
        'volumes': [458190] * 60,
        'kospi_index': 6579.04,
        'kospi_change_rate': 3.68,
        'kosdaq_index': 858.91,
        'kosdaq_change_rate': 0.12
    }
    
    print("=" * 80)
    print("CombinedAnalyzer 테스트 (Phase 3)")
    print("=" * 80)
    
    analyzer = CombinedAnalyzer()
    result = analyzer.run(data)
    
    print("\n【분석 결과】")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    
    details = result.get('details', {})
    print(f"\n【최종 신호】")
    print(f"  기술지표: {details.get('technical_score', 0):.1f}/100")
    print(f"  시장 강도: {details.get('market_strength', 0):.1f}/100 ({details.get('market_regime', 'N/A')})")
    print(f"  시장 배수: {details.get('market_multiplier', 1.0):.2f}x")
    print(f"  최종 점수: {details.get('combined_score', 0):.1f}/100")
    print(f"  신호: {details.get('signal', '불명')}")
    print(f"  신뢰도: {details.get('confidence', 0):.1f}%")
    
    print("\n" + "=" * 80)
    print("✅ 테스트 완료!")
    print("=" * 80)
