"""
AdvancedCombinedAnalyzer - 고급 통합 엔진 (Phase 4)
기술지표 + 시장필터 + 기본분석 3가지 통합
최종 신호 + 신뢰도 + 거래 강도
"""

import sys
import os
from typing import Dict, Any
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from market_intelligence.base_analyzer import BaseAnalyzer
from market_intelligence.analyzers.technical_analyzer import TechnicalAnalyzer
from market_intelligence.analyzers.market_analyzer import MarketAnalyzer
from market_intelligence.analyzers.valuation_analyzer import ValuationAnalyzer

logger = logging.getLogger(__name__)


class AdvancedCombinedAnalyzer(BaseAnalyzer):
    """고급 통합 엔진 - 3가지 분석 통합"""
    
    def __init__(self):
        super().__init__(name="advanced_combined", weight=1.0)
        self.technical = TechnicalAnalyzer()
        self.market = MarketAnalyzer()
        self.valuation = ValuationAnalyzer()
        logger.info("✅ AdvancedCombinedAnalyzer 초기화 완료")
    
    def validate(self, data: Dict[str, Any]) -> bool:
        """모든 분석에 필요한 데이터 검증"""
        return (
            len(data.get('closes', [])) >= 60 and
            'kospi_index' in data and
            'per' in data
        )
    
    def analyze(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """3가지 분석 통합"""
        # Step 1: 기술지표 분석 (가중치: 35%)
        tech_result = self.technical.run(data)
        tech_score = tech_result.get('score', 50)
        
        # Step 2: 시장 분석 (가중치: 35%)
        market_result = self.market.run(data)
        market_score = market_result.get('score', 50)
        market_multiplier = market_result.get('details', {}).get('signal_multiplier', 1.0)
        
        # Step 3: 기본분석 (가중치: 30%)
        val_result = self.valuation.run(data)
        val_score = val_result.get('score', 50)
        
        # 종합 점수 (가중평균)
        final_score = (
            tech_score * 0.35 +
            market_score * 0.35 +
            val_score * 0.30
        ) * market_multiplier
        
        final_score = max(0, min(100, final_score))
        
        # 신뢰도 계산
        confidence = self._calculate_confidence(tech_score, market_score, val_score)
        
        # 거래 강도
        trade_strength = self._calculate_trade_strength(final_score, confidence)
        
        return {
            'technical_score': tech_score,
            'market_score': market_score,
            'valuation_score': val_score,
            'market_multiplier': market_multiplier,
            'final_score': final_score,
            'confidence': confidence,
            'trade_strength': trade_strength,
            'signal': self._generate_signal(final_score),
            'recommendation': self._generate_recommendation(final_score, confidence, trade_strength),
            'risk_level': self._assess_risk(market_score, val_score)
        }
    
    def get_score(self, analysis_result: Dict[str, Any]) -> float:
        """최종 점수"""
        return analysis_result.get('final_score', 50)
    
    @staticmethod
    def _calculate_confidence(tech: float, market: float, val: float) -> float:
        """신뢰도 계산 (0-100)"""
        # 3개 지표의 의견이 일치할수록 높음
        avg = (tech + market + val) / 3
        variance = ((tech - avg)**2 + (market - avg)**2 + (val - avg)**2) / 3
        
        # 분산이 작을수록 신뢰도 높음
        confidence = max(0, 100 - variance / 10)
        return min(100, confidence)
    
    @staticmethod
    def _calculate_trade_strength(score: float, confidence: float) -> str:
        """거래 강도 (매매 추천도)"""
        strength_score = score * (confidence / 100)
        
        if strength_score >= 80:
            return "극강 추천 (전량 매수)"
        elif strength_score >= 70:
            return "강 추천 (공격적 매수)"
        elif strength_score >= 60:
            return "중 추천 (정상 매수)"
        elif strength_score >= 50:
            return "약 추천 (분할 매수)"
        elif strength_score >= 40:
            return "약 권유 (관망)"
        elif strength_score >= 30:
            return "약 주의 (분할 매도)"
        elif strength_score >= 20:
            return "중 주의 (정상 매도)"
        else:
            return "강 주의 (전량 매도)"
    
    @staticmethod
    def _generate_signal(score: float) -> str:
        """매매 신호"""
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
    def _generate_recommendation(score: float, confidence: float, strength: str) -> str:
        """투자 권고"""
        if score >= 70 and confidence >= 60:
            return "강력한 매수 권장"
        elif score >= 60 and confidence >= 50:
            return "매수 권장"
        elif score >= 45:
            return "중립 - 추가 관찰 필요"
        elif score >= 30:
            return "매도 검토"
        else:
            return "강한 매도 권장"
    
    @staticmethod
    def _assess_risk(market: float, val: float) -> str:
        """위험도 평가"""
        if market >= 70 and val >= 60:
            return "낮음 ✅ (강세장 + 저평가)"
        elif market >= 60 or val >= 60:
            return "중간 ⚠️"
        elif market >= 40 or val >= 40:
            return "높음 🔴"
        else:
            return "매우높음 🔴🔴 (약세장 + 고평가)"


if __name__ == "__main__":
    import json
    
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    
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
        'kosdaq_change_rate': 0.12,
        'per': 12.5,
        'pbr': 1.1,
        'dividend_yield': 3.2
    }
    
    print("=" * 80)
    print("AdvancedCombinedAnalyzer 테스트 (Phase 4 - 고급 통합 엔진)")
    print("=" * 80)
    
    analyzer = AdvancedCombinedAnalyzer()
    result = analyzer.run(data)
    
    details = result.get('details', {})
    
    print("\n【점수 분석】")
    print(f"  기술지표: {details.get('technical_score', 0):.1f}/100")
    print(f"  시장분석: {details.get('market_score', 0):.1f}/100")
    print(f"  기본분석: {details.get('valuation_score', 0):.1f}/100")
    print(f"  시장배수: {details.get('market_multiplier', 1.0):.2f}x")
    
    print("\n【최종 결과】")
    print(f"  최종 점수: {details.get('final_score', 0):.1f}/100")
    print(f"  신뢰도: {details.get('confidence', 0):.1f}%")
    print(f"  신호: {details.get('signal', '불명')}")
    
    print("\n【투자 권고】")
    print(f"  강도: {details.get('trade_strength', '불명')}")
    print(f"  권고: {details.get('recommendation', '불명')}")
    print(f"  위험: {details.get('risk_level', '불명')}")
    
    print("\n" + "=" * 80)
    print("✅ Phase 4 완성!")
    print("=" * 80)
