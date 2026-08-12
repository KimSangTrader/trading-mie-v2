"""
MarketAnalyzer - 시장 분석기 (BaseAnalyzer 상속)
KOSPI/KOSDAQ 지수 기반 시장 강도 판정 + 신호 가중치 적용
"""

import sys
import os
from typing import Dict, Any
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from market_intelligence.base_analyzer import BaseAnalyzer
from data.kis_client import KISClient

logger = logging.getLogger(__name__)


class MarketAnalyzer(BaseAnalyzer):
    """시장 분석기 - KOSPI/KOSDAQ 기반"""
    
    def __init__(self):
        super().__init__(name="market", weight=0.30)
        self.kis_client = KISClient()
        logger.info(f"✅ MarketAnalyzer 초기화 완료 (weight={self.weight})")
    
    def validate(self, data: Dict[str, Any]) -> bool:
        """데이터 검증"""
        print(f"【validate() 호출】")
        
        # 필수 필드 확인
        required_fields = ["kospi_index", "kosdaq_index"]
        
        if not all(field in data for field in required_fields):
            print(f"❌ 필수 필드 누락")
            return False
        
        # 값 확인 (양수)
        if data["kospi_index"] <= 0 or data["kosdaq_index"] <= 0:
            print(f"❌ 지수 값이 0 이하")
            return False
        
        print(f"✅ 검증 성공")
        return True
    
    def analyze(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """시장 분석"""
        kospi = data.get("kospi_index", 0)
        kosdaq = data.get("kosdaq_index", 0)
        kospi_change = data.get("kospi_change_rate", 0)
        kosdaq_change = data.get("kosdaq_change_rate", 0)
        
        print(f"【analyze() 호출】KOSPI: {kospi_change:+.2f}%, KOSDAQ: {kosdaq_change:+.2f}%")
        
        # 평균 변화율
        avg_change = (kospi_change + kosdaq_change) / 2
        
        # 상관계수
        corr = self._calculate_correlation(kospi_change, kosdaq_change)
        
        # 시장 강도
        market_strength = self._calculate_market_strength(kospi_change, kosdaq_change, corr)
        
        # 시장 체제
        regime = self._determine_market_regime(market_strength, avg_change, corr)
        
        # 신호 가중치
        multiplier = self._calculate_weight_multiplier(regime, market_strength)
        
        result = {
            "kospi_index": kospi,
            "kosdaq_index": kosdaq,
            "kospi_change_rate": kospi_change,
            "kosdaq_change_rate": kosdaq_change,
            "market_strength": market_strength,
            "market_regime": regime,
            "signal_multiplier": multiplier,
            "signal_strength": self._interpret_signal_strength(regime, multiplier)
        }
        
        print(f"✅ 분석 완료: {regime} ({market_strength:.1f}/100, {multiplier:.2f}x)")
        return result
    
    def get_score(self, analysis_result: Dict[str, Any]) -> float:
        """점수 산출"""
        score = analysis_result.get("market_strength", 50)
        return max(0, min(100, score))
    
    @staticmethod
    def _calculate_correlation(kospi_change: float, kosdaq_change: float) -> float:
        """상관계수"""
        if (kospi_change > 0 and kosdaq_change > 0) or (kospi_change < 0 and kosdaq_change < 0):
            return 0.8
        else:
            return -0.5
    
    @staticmethod
    def _calculate_market_strength(kospi_change: float, kosdaq_change: float, correlation: float) -> float:
        """시장 강도 (0-100)"""
        avg_change = (kospi_change + kosdaq_change) / 2
        change_score = min(100, 50 + abs(avg_change) * 10)
        
        if avg_change > 0:
            direction_score = min(100, 50 + (avg_change * 10))
        elif avg_change < 0:
            direction_score = max(0, 50 - (abs(avg_change) * 10))
        else:
            direction_score = 50
        
        correlation_score = 50 + (correlation * 50)
        
        market_strength = (
            direction_score * 0.50 +
            correlation_score * 0.30 +
            change_score * 0.20
        )
        
        return max(0, min(100, market_strength))
    
    @staticmethod
    def _determine_market_regime(market_strength: float, avg_change: float, correlation: float) -> str:
        """시장 체제 판정"""
        if market_strength >= 85:
            return "TECH_BULL"
        elif market_strength >= 70:
            return "STRONG_BULL"
        elif market_strength >= 60:
            return "BULL"
        elif market_strength >= 45:
            return "NEUTRAL"
        elif market_strength >= 35:
            return "BEAR"
        elif market_strength >= 20:
            return "STABLE_BEAR"
        else:
            return "CRASH_BEAR"
    
    @staticmethod
    def _calculate_weight_multiplier(regime: str, market_strength: float) -> float:
        """신호 가중치"""
        multipliers = {
            "TECH_BULL": 1.5,
            "STRONG_BULL": 1.2,
            "BULL": 1.0,
            "NEUTRAL": 0.8,
            "BEAR": 0.6,
            "STABLE_BEAR": 0.5,
            "CRASH_BEAR": 0.3
        }
        
        base = multipliers.get(regime, 1.0)
        strength_adjustment = (market_strength - 50) / 500
        return max(0.3, min(1.5, base * (1 + strength_adjustment)))
    
    @staticmethod
    def _interpret_signal_strength(regime: str, multiplier: float) -> str:
        """신호 강도 해석"""
        if multiplier >= 1.3:
            return "공격적 매수 신호 강함 🟢🟢"
        elif multiplier >= 1.0:
            return "매수 신호 🟢"
        elif multiplier >= 0.8:
            return "중립 신호 ⚪"
        elif multiplier >= 0.6:
            return "약한 매도 신호 🟡"
        elif multiplier >= 0.4:
            return "매도 신호 🔴"
        else:
            return "강한 매도 신호 🔴🔴"