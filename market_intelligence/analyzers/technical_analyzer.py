"""
TechnicalAnalyzer - 기술지표 분석 모듈
MACD, RSI, 볼린저밴드, 이동평균선을 이용한 기술적 분석

================================================================================
【변경 이력】
================================================================================
【2026-08-12】Phase 1 최초 생성
- TechnicalAnalyzer 클래스 생성 (BaseAnalyzer 상속)
- MACD, RSI, 볼린저밴드, 이동평균선 계산
- 기술지표 점수 산출 (0-100)
- KIS API로 60일 데이터 자동 수집
- 4단계 파이프라인 구현 (validate → analyze → get_score → run)

【2026-08-13】KISClient 자동 초기화 + 실시간 데이터 조회 기능 추가
- 변경 사항:
  * __init__(self, kis_client=None) 파라미터 추가
  * kis_client=None일 때 자동으로 KISClient() 초기화 시도
  * 초기화 실패 시에만 Mock 모드로 Fall-back
  * __main__ 섹션: get_daily_price() 호출로 실시간 60일 데이터 조회
  * Mock 데이터 → 실제 오늘 데이터로 변경
- 목적:
  * 실제 환경: 자동 KIS API 연결 및 실시간 데이터 조회 ✅
  * CI 환경: .env 없으면 자동 Mock 모드 전환 ✅
  * 테스트 시 실제 오늘 기술지표 분석
- 영향: 기존 기능 유지 + 실시간 테스트 가능

【2026-08-13】technical_indicators.py 메서드명 변경 (복수형)
- 변경 사항:
  * calculate_bollinger_band() → calculate_bollinger_bands() (복수형)
  * calculate_moving_average() → calculate_moving_averages() (복수형)
  * 관련 메서드 호출부 모두 수정
  * _score_bollinger_band() 메서드명 유지 (내부 메서드)
  * _score_moving_average() 메서드명 유지 (내부 메서드)
- 목적: technical_indicators.py 실제 메서드명과 일치
- 영향: 메서드 호출 정상화, 기존 로직 100% 유지
================================================================================

"""

import sys
import os
from typing import Dict, Any, Optional, List
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from market_intelligence.base_analyzer import BaseAnalyzer
from data.technical_indicators import TechnicalIndicators

logger = logging.getLogger(__name__)


class TechnicalAnalyzer(BaseAnalyzer):
    """
    기술지표 분석 모듈 - 기술적 분석
    
    역할:
    1. 60일 일자별 가격 데이터 수집
    2. 기술지표 계산 (MACD, RSI, 볼린저밴드, MA)
    3. 기술지표 점수 종합 (0-100)
    4. 매수/매도 신호 생성
    
    기술지표 가중치:
    - MACD: 30% (추세 방향 확인)
    - RSI: 30% (과매수/과매도)
    - 볼린저밴드: 20% (변동성)
    - 이동평균선: 20% (추세 강도)
    
    가중치: 0.18 (Phase 1에서 정의)
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
        super().__init__(name='technical', weight=0.18)
        
        if kis_client is None:
            # KISClient 자동 초기화 시도
            try:
                from data.kis_client import KISClient
                self.kis_client = KISClient()
                logger.info(f'✅ TechnicalAnalyzer 초기화 완료 (KIS API 연결됨, weight={self.weight})')
            except Exception as e:
                # 초기화 실패 → Mock 모드로 Fall-back
                logger.warning(f'⚠️  KISClient 초기화 실패: {str(e)}')
                logger.info(f'✅ TechnicalAnalyzer 초기화 완료 (Mock 모드, weight={self.weight})')
                self.kis_client = None
        else:
            # 명시적으로 전달된 kis_client 사용
            self.kis_client = kis_client
            if kis_client is not None:
                logger.info(f'✅ TechnicalAnalyzer 초기화 완료 (KIS API 연결, weight={self.weight})')
            else:
                logger.info(f'✅ TechnicalAnalyzer 초기화 완료 (Mock 모드, weight={self.weight})')
    
    def validate(self, data: Dict[str, Any]) -> bool:
        """
        데이터 검증
        
        필수 필드:
        - closes (list): 종가 리스트 (최소 60개)
        - opens (list): 시가 리스트
        - highs (list): 고가 리스트
        - lows (list): 저가 리스트
        - volumes (list): 거래량 리스트
        """
        required = ['closes', 'opens', 'highs', 'lows', 'volumes']
        has_fields = all(field in data for field in required)
        has_enough_data = len(data.get('closes', [])) >= 60
        return has_fields and has_enough_data
    
    def analyze(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        기술지표 분석 수행
        
        Step 1: MACD 계산 (추세)
        Step 2: RSI 계산 (과매수/과매도)
        Step 3: 볼린저밴드 계산 (변동성)
        Step 4: 이동평균선 계산 (추세 강도)
        Step 5: 종합 점수 산출
        
        【2026-08-13 수정】메서드명 변경 (복수형)
        - calculate_bollinger_band() → calculate_bollinger_bands()
        - calculate_moving_average() → calculate_moving_averages()
        """
        closes = data.get('closes', [])
        opens = data.get('opens', [])
        highs = data.get('highs', [])
        lows = data.get('lows', [])
        volumes = data.get('volumes', [])
        
        logger.info(f'📊 {data.get("symbol", "0001")} 기술지표 분석 시작 ({len(closes)}개 캔들)')
        
        # Step 1: MACD
        macd_result = TechnicalIndicators.calculate_macd(closes)
        macd_score = self._score_macd(macd_result)
        
        # Step 2: RSI
        rsi_result = TechnicalIndicators.calculate_rsi(closes)
        rsi_score = self._score_rsi(rsi_result)
        
        # Step 3: 볼린저밴드 【2026-08-13 수정】메서드명 변경
        bb_result = TechnicalIndicators.calculate_bollinger_bands(closes)
        bb_score = self._score_bollinger_band(bb_result, closes[-1])
        
        # Step 4: 이동평균선 【2026-08-13 수정】메서드명 변경
        ma_result = TechnicalIndicators.calculate_moving_averages(closes)
        ma_score = self._score_moving_average(ma_result, closes[-1])
        
        logger.info(f'✅ {data.get("symbol", "0001")} 분석 완료')
        
        return {
            'symbol': data.get('symbol', 'unknown'),
            'data_points': len(closes),
            'indicators': {
                'macd': macd_result,
                'rsi': rsi_result,
                'bollinger_bands': bb_result,
                'moving_averages': ma_result
            },
            'scores': {
                'macd_score': macd_score,
                'rsi_score': rsi_score,
                'bb_score': bb_score,
                'ma_score': ma_score
            }
        }
    
    def get_score(self, analysis_result: Dict[str, Any]) -> float:
        """
        종합 점수 계산 (0-100)
        
        가중평균:
        - MACD 점수: 30%
        - RSI 점수: 30%
        - BB 점수: 20%
        - MA 점수: 20%
        """
        scores = analysis_result.get('scores', {})
        macd_score = scores.get('macd_score', 50)
        rsi_score = scores.get('rsi_score', 50)
        bb_score = scores.get('bb_score', 50)
        ma_score = scores.get('ma_score', 50)
        
        final_score = (
            macd_score * 0.30 +
            rsi_score * 0.30 +
            bb_score * 0.20 +
            ma_score * 0.20
        )
        
        logger.info(f'✅ 종합 점수 계산 완료: {final_score:.1f}/100')
        
        return max(0, min(100, final_score))
    
    @staticmethod
    def _score_macd(macd_result: Dict[str, float]) -> float:
        """MACD 점수 (0-100)"""
        histogram = macd_result.get('histogram', 0)
        macd_line = macd_result.get('macd', 0)
        signal = macd_result.get('signal', 0)
        
        if histogram > 0 and macd_line > signal:
            return 70  # 강한 상승
        elif histogram > 0:
            return 60  # 약한 상승
        elif histogram < 0 and macd_line < signal:
            return 30  # 강한 하강
        else:
            return 40  # 약한 하강
    
    @staticmethod
    def _score_rsi(rsi_value: float) -> float:
        """RSI 점수 (0-100)"""
        if rsi_value >= 70:
            return 30  # 과매수
        elif rsi_value >= 60:
            return 60  # 강한 매수
        elif rsi_value >= 50:
            return 70  # 매수
        elif rsi_value >= 40:
            return 60  # 약한 매도
        elif rsi_value >= 30:
            return 40  # 매도
        else:
            return 30  # 과매도
    
    @staticmethod
    def _score_bollinger_band(bb_result: Dict[str, Any], current_price: float) -> float:
        """
        볼린저밴드 점수 (0-100)
        
        bb_result 구조:
        {
            'upper': float,
            'middle': float,
            'lower': float,
            'position': str ('upper', 'middle', 'lower')
        }
        """
        position = bb_result.get('position', 'middle')
        
        if position == 'upper':
            return 30  # 상단 터치 → 조정 가능성
        elif position == 'lower':
            return 70  # 하단 터치 → 반등 가능성
        else:
            return 50  # 중간 → 중립
    
    @staticmethod
    def _score_moving_average(ma_result: Dict[str, Any], current_price: float) -> float:
        """
        이동평균선 점수 (0-100)
        
        ma_result 구조:
        {
            'sma_20': float,
            'sma_50': float,
            'ema_12': float,
            'ema_26': float
        }
        """
        sma_20 = ma_result.get('sma_20', current_price)
        sma_50 = ma_result.get('sma_50', current_price)
        
        # 단순한 추세 판정
        if current_price > sma_20 > sma_50:
            return 70  # 상승 추세
        elif current_price < sma_20 < sma_50:
            return 30  # 하강 추세
        else:
            return 50  # 중립


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    analyzer = TechnicalAnalyzer()
    
    # 【2026-08-13 추가】실시간 오늘 데이터 조회
    if analyzer.kis_client is not None:
        print("=" * 80)
        print("【실시간 오늘 데이터 사용】")
        print("=" * 80)
        try:
            # KISClient에서 60일 일자별 데이터 가져오기
            symbol = "0001"  # KOSPI
            daily_data = analyzer.kis_client.get_daily_price(symbol, days=60)
            
            data = {
                'symbol': symbol,
                'closes': daily_data.get('closes', []),
                'opens': daily_data.get('opens', []),
                'highs': daily_data.get('highs', []),
                'lows': daily_data.get('lows', []),
                'volumes': daily_data.get('volumes', [])
            }
            
            print(f"\n【오늘 실시간 데이터】")
            print(f"  종목: {symbol}")
            print(f"  데이터 포인트: {len(data['closes'])}개")
            if len(data['closes']) > 0:
                print(f"  현재가: {data['closes'][-1]:,.0f}")
                print(f"  고가: {max(data['highs']):,.0f}")
                print(f"  저가: {min(data['lows']):,.0f}")
            
        except Exception as e:
            print(f"❌ 실시간 데이터 조회 실패: {e}")
            print("Mock 데이터로 대체합니다.\n")
            data = {
                'symbol': '0001',
                'opens': [7500] * 60,
                'highs': [7600] * 60,
                'lows': [7400] * 60,
                'closes': [7516.04] + [7510] * 59,
                'volumes': [458190] * 60
            }
    else:
        # Mock 모드
        print("=" * 80)
        print("【Mock 데이터 사용】")
        print("=" * 80)
        data = {
            'symbol': '0001',
            'opens': [7500] * 60,
            'highs': [7600] * 60,
            'lows': [7400] * 60,
            'closes': [7516.04] + [7510] * 59,
            'volumes': [458190] * 60
        }
    
    # 분석 실행
    print()
    result = analyzer.run(data)
    
    print("\n【분석 결과】")
    details = result.get('details', {})
    scores = details.get('scores', {})
    print(f"  MACD 점수: {scores.get('macd_score', 0):.1f}/100")
    print(f"  RSI 점수: {scores.get('rsi_score', 0):.1f}/100")
    print(f"  BB 점수: {scores.get('bb_score', 0):.1f}/100")
    print(f"  MA 점수: {scores.get('ma_score', 0):.1f}/100")
    print(f"  최종 점수: {result.get('score', 0):.1f}/100")
    print("=" * 80)