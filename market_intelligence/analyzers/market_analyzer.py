"""
MarketAnalyzer - 시장분석 모듈
KOSPI/KOSDAQ 이중 필터로 시장 강도 판정 및 신호 가중치 계산

================================================================================
【변경 이력】
================================================================================
【2026-08-12】Phase 2 최초 생성
- MarketAnalyzer 클래스 생성 (BaseAnalyzer 상속)
- KOSPI/KOSDAQ 상관계수 계산
- 시장 강도 판정 (0-100점)
- 시장 체제 판정 (7가지: TECH_BULL ~ CRASH_BEAR)
- 신호 가중치 계산 (0.3x ~ 1.5x)

【2026-08-13】KISClient 자동 초기화 + Fall-back 메커니즘
- 변경 사항:
  * __init__(self, kis_client=None) 파라미터 추가
  * kis_client=None일 때 자동으로 KISClient() 초기화 시도
  * 초기화 실패 시에만 Mock 모드로 Fall-back
  * try-except로 안전하게 처리
- 목적: 
  * 실제 환경: 자동 KIS API 연결 ✅
  * CI 환경: .env 없으면 자동 Mock 모드 전환 ✅
  * 기존 사용법 100% 유지
- 영향: 기존 기능 유지 + CI 호환성 개선

【2026-08-13】실시간 오늘 데이터 조회 기능 추가
- 변경 사항:
  * __main__ 섹션 완전 개선
  * get_kospi_kosdaq() 메서드 호출로 실시간 데이터 자동 조회
  * Mock 데이터 → 실제 오늘 데이터로 변경
  * 에러 처리 추가 (조회 실패 시 Mock 데이터로 Fall-back)
  * 실시간 데이터 출력 기능 추가
- 목적: 테스트 실행 시 실제 오늘 시장 데이터로 분석
- 영향: 실시간 테스트 가능, 기존 기능 100% 유지
================================================================================

"""

import sys
import os
from typing import Dict, Any, Optional
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from market_intelligence.base_analyzer import BaseAnalyzer

logger = logging.getLogger(__name__)


class MarketAnalyzer(BaseAnalyzer):
    """
    시장분석 모듈 - KOSPI/KOSDAQ 이중 필터
    
    역할:
    1. KOSPI와 KOSDAQ 지수 변화율 수집
    2. 두 지수의 상관계수 계산
    3. 시장 강도 (0-100점) 판정
    4. 시장 체제 (7가지) 판정
    5. 신호 가중치 (0.3x ~ 1.5x) 계산
    
    가중치: 0.30 (Phase 2에서 정의)
    
    사용법:
    - 실제 환경: MarketAnalyzer() → 자동 KIS API 연결
    - 테스트 환경: MarketAnalyzer(kis_client=None) → Mock 모드
    """
    
    def __init__(self, kis_client: Optional[Any] = None):
        """
        【2026-08-13 수정】KISClient 자동 초기화 + Fall-back
        
        kis_client 파라미터:
        - None (기본값): KISClient 자동 초기화 시도
          * 성공: 실제 KIS API 연결
          * 실패: Mock 모드로 자동 전환
        - 명시적 전달: 그 값 사용
        """
        super().__init__(name='market', weight=0.30)
        
        if kis_client is None:
            # KISClient 자동 초기화 시도
            try:
                from data.kis_client import KISClient
                self.kis_client = KISClient()
                logger.info(f'✅ MarketAnalyzer 초기화 완료 (KIS API 연결됨, weight={self.weight})')
            except Exception as e:
                # 초기화 실패 → Mock 모드로 Fall-back
                logger.warning(f'⚠️  KISClient 초기화 실패: {str(e)}')
                logger.info(f'✅ MarketAnalyzer 초기화 완료 (Mock 모드, weight={self.weight})')
                self.kis_client = None
        else:
            # 명시적으로 전달된 kis_client 사용
            self.kis_client = kis_client
            if kis_client is not None:
                logger.info(f'✅ MarketAnalyzer 초기화 완료 (KIS API 연결, weight={self.weight})')
            else:
                logger.info(f'✅ MarketAnalyzer 초기화 완료 (Mock 모드, weight={self.weight})')
    
    def validate(self, data: Dict[str, Any]) -> bool:
        """
        데이터 검증
        
        필수 필드:
        - kospi_index (float): KOSPI 지수값
        - kosdaq_index (float): KOSDAQ 지수값
        """
        required = ['kospi_index', 'kosdaq_index']
        return all(field in data for field in required)
    
    def analyze(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        시장분석 수행
        
        Step 1: 상관계수 계산
        Step 2: 시장 강도 판정
        Step 3: 시장 체제 판정
        Step 4: 신호 가중치 계산
        """
        kospi_index = data.get('kospi_index', 0)
        kospi_change = data.get('kospi_change_rate', 0)
        kosdaq_index = data.get('kosdaq_index', 0)
        kosdaq_change = data.get('kosdaq_change_rate', 0)
        
        # Step 1: 상관계수 계산
        correlation = self._calculate_correlation(kospi_change, kosdaq_change)
        
        # Step 2: 시장 강도
        market_strength = self._calculate_market_strength(kospi_change, kosdaq_change, correlation)
        
        # Step 3: 시장 체제
        market_regime = self._determine_market_regime(market_strength, (kospi_change + kosdaq_change) / 2, correlation)
        
        # Step 4: 신호 가중치
        signal_multiplier = self._calculate_weight_multiplier(market_regime, market_strength)
        
        logger.info(f'【analyze() 호출】KOSPI: {kospi_change:+.2f}%, KOSDAQ: {kosdaq_change:+.2f}%')
        logger.info(f'✅ 분석 완료: {market_regime} ({market_strength:.1f}/100, {signal_multiplier:.2f}x)')
        
        return {
            'kospi_index': kospi_index,
            'kosdaq_index': kosdaq_index,
            'kospi_change_rate': kospi_change,
            'kosdaq_change_rate': kosdaq_change,
            'market_strength': market_strength,
            'market_regime': market_regime,
            'signal_multiplier': signal_multiplier,
            'signal_strength': self._get_signal_strength(signal_multiplier)
        }
    
    def get_score(self, analysis_result: Dict[str, Any]) -> float:
        """시장 강도 점수 (0-100)"""
        return analysis_result.get('market_strength', 50)
    
    @staticmethod
    def _calculate_correlation(kospi_change: float, kosdaq_change: float) -> float:
        """
        상관계수 계산 (0-1)
        
        요소:
        1. 부호 일치도 (같은 방향이면 1.0, 반대면 0.5)
        2. 크기 유사도 (변화율 비율)
        """
        # 부호 일치도
        if (kospi_change > 0 and kosdaq_change > 0) or (kospi_change < 0 and kosdaq_change < 0):
            sign_match = 1.0
        else:
            sign_match = 0.5
        
        # 크기 유사도
        max_change = max(abs(kospi_change), abs(kosdaq_change))
        min_change = min(abs(kospi_change), abs(kosdaq_change))
        
        if max_change > 0:
            size_match = 0.8 + (min_change / max_change) * 0.2
        else:
            size_match = 1.0
        
        correlation = (sign_match + size_match) / 2
        return min(1.0, correlation)
    
    @staticmethod
    def _calculate_market_strength(kospi_change: float, kosdaq_change: float, correlation: float) -> float:
        """
        시장 강도 계산 (0-100)
        
        3가지 요소의 가중평균:
        - 방향성: 50% (상승/하강 추세)
        - 동행성: 30% (상관계수 기반 신뢰도)
        - 변화율: 20% (변화폭 크기)
        """
        avg_change = (kospi_change + kosdaq_change) / 2
        
        direction_score = 50 + (avg_change * 10)
        correlation_score = 50 + (correlation * 50)
        change_score = min(100, 50 + abs(avg_change) * 10)
        
        market_strength = (direction_score * 0.50) + (correlation_score * 0.30) + (change_score * 0.20)
        return max(0, min(100, market_strength))
    
    @staticmethod
    def _determine_market_regime(market_strength: float, avg_change: float, correlation: float) -> str:
        """
        시장 체제 판정 (7가지)
        
        | 체제 | 점수범위 | 의미 |
        |------|---------|------|
        | TECH_BULL | 85+ | 극강세 |
        | STRONG_BULL | 70-84 | 강세 |
        | BULL | 60-69 | 약한 강세 |
        | NEUTRAL | 50-59 | 중립 |
        | BEAR | 40-49 | 약한 약세 |
        | STABLE_BEAR | 30-39 | 안정적 약세 |
        | CRASH_BEAR | 0-29 | 극약세 |
        """
        if market_strength >= 85:
            return "TECH_BULL"
        elif market_strength >= 70:
            return "STRONG_BULL"
        elif market_strength >= 60:
            return "BULL"
        elif market_strength >= 50:
            return "NEUTRAL"
        elif market_strength >= 40:
            return "BEAR"
        elif market_strength >= 30:
            return "STABLE_BEAR"
        else:
            return "CRASH_BEAR"
    
    @staticmethod
    def _calculate_weight_multiplier(regime: str, market_strength: float) -> float:
        """
        신호 가중치 배수 계산 (0.3x ~ 1.5x)
        
        기본 배수 (시장 체제별):
        - TECH_BULL: 1.5x (공격적 매수)
        - STRONG_BULL: 1.2x (강세)
        - BULL: 1.0x (기본)
        - NEUTRAL: 0.8x (신중)
        - BEAR: 0.6x (약세)
        - STABLE_BEAR: 0.5x (안정적 약세)
        - CRASH_BEAR: 0.3x (거의 무시)
        
        미세조정: 시장 강도에 따라 ±5% 조정
        """
        multipliers = {
            "TECH_BULL": 1.5,
            "STRONG_BULL": 1.2,
            "BULL": 1.0,
            "NEUTRAL": 0.8,
            "BEAR": 0.6,
            "STABLE_BEAR": 0.5,
            "CRASH_BEAR": 0.3
        }
        
        base_multiplier = multipliers.get(regime, 1.0)
        strength_adjustment = (market_strength - 50) / 500
        final_multiplier = base_multiplier * (1 + strength_adjustment)
        
        return max(0.3, min(1.5, final_multiplier))
    
    @staticmethod
    def _get_signal_strength(multiplier: float) -> str:
        """신호 강도 해석 (사람이 읽을 수 있는 형식)"""
        if multiplier >= 1.4:
            return "공격적 매수 신호 🟢🟢"
        elif multiplier >= 1.0:
            return "매수 신호 🟢"
        elif multiplier >= 0.8:
            return "약한 매수 신호 🟡"
        elif multiplier >= 0.6:
            return "중립 신호 ⚪"
        else:
            return "약한 매도 신호 🔴"


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    analyzer = MarketAnalyzer()
    
    # 【2026-08-13 추가】실시간 오늘 데이터 조회
    if analyzer.kis_client is not None:
        print("=" * 80)
        print("【실시간 오늘 데이터 사용】")
        print("=" * 80)
        try:
            # KISClient에서 실시간 KOSPI/KOSDAQ 데이터 가져오기
            kospi_kosdaq_data = analyzer.kis_client.get_kospi_kosdaq()
            
            data = {
                'kospi_index': kospi_kosdaq_data.get('kospi_index', 0),
                'kospi_change_rate': kospi_kosdaq_data.get('kospi_change_rate', 0),
                'kosdaq_index': kospi_kosdaq_data.get('kosdaq_index', 0),
                'kosdaq_change_rate': kospi_kosdaq_data.get('kosdaq_change_rate', 0)
            }
            
            print(f"\n【오늘 실시간 데이터】")
            print(f"  KOSPI: {data['kospi_index']:.2f} ({data['kospi_change_rate']:+.2f}%)")
            print(f"  KOSDAQ: {data['kosdaq_index']:.2f} ({data['kosdaq_change_rate']:+.2f}%)")
            
        except Exception as e:
            print(f"❌ 실시간 데이터 조회 실패: {e}")
            print("Mock 데이터로 대체합니다.\n")
            data = {
                'kospi_index': 6579.04,
                'kospi_change_rate': 3.68,
                'kosdaq_index': 858.91,
                'kosdaq_change_rate': 0.12
            }
    else:
        # Mock 모드
        print("=" * 80)
        print("【Mock 데이터 사용】")
        print("=" * 80)
        data = {
            'kospi_index': 6579.04,
            'kospi_change_rate': 3.68,
            'kosdaq_index': 858.91,
            'kosdaq_change_rate': 0.12
        }
    
    # 분석 실행
    print()
    result = analyzer.run(data)
    
    print("\n【분석 결과】")
    details = result.get('details', {})
    print(f"  점수: {details.get('market_strength', 0):.1f}/100")
    print(f"  체제: {details.get('market_regime', 'N/A')}")
    print(f"  배수: {details.get('signal_multiplier', 1.0):.2f}x")
    print(f"  신호: {details.get('signal_strength', 'N/A')}")
    print("=" * 80)