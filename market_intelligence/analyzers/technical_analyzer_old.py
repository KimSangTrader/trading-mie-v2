"""
TechnicalAnalyzer - 기술지표 분석 엔진
MACD, RSI, 볼린저밴드, 이동평균선을 계산하고 종합 점수 산출
"""

import numpy as np
import sys
import os
from datetime import datetime

# 프로젝트 루트 추가
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data.kis_client import KISClient


class TechnicalAnalyzer:
    """기술지표 분석 엔진"""
    
    def __init__(self):
        """초기화"""
        self.kis_client = KISClient()
        self.data = None
        
    def fetch_data(self, symbol: str, days: int = 60) -> bool:
        """KIS API에서 데이터 수집"""
        try:
            print(f"\n📊 {symbol} 데이터 수집 중...")
            
            self.data = self.kis_client.get_daily_price(symbol, days=days)
            
            if not self.data or len(self.data['closes']) == 0:
                print(f"❌ 데이터 수집 실패")
                return False
            
            print(f"✅ {len(self.data['closes'])}일치 데이터 수집 완료")
            return True
            
        except Exception as e:
            print(f"❌ 데이터 수집 오류: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def calculate_macd(self, fast=12, slow=26, signal=9):
        """
        MACD 계산
        Returns: {macd_line, signal_line, histogram}
        """
        try:
            closes = np.array(self.data['closes'], dtype=float)
            
            if len(closes) < slow:
                return None
            
            # EMA 계산
            ema_fast = self._calculate_ema(closes, fast)
            ema_slow = self._calculate_ema(closes, slow)
            
            # MACD Line
            macd_line = ema_fast - ema_slow
            
            # Signal Line (MACD의 EMA)
            signal_line = self._calculate_ema(macd_line, signal)
            
            # Histogram
            histogram = macd_line - signal_line
            
            return {
                'macd_line': macd_line[-1],
                'signal_line': signal_line[-1],
                'histogram': histogram[-1]
            }
            
        except Exception as e:
            print(f"❌ MACD 계산 오류: {e}")
            return None
    
    def calculate_rsi(self, period=14):
        """
        RSI(상대강도지수) 계산
        Returns: RSI 값 (0-100)
        """
        try:
            closes = np.array(self.data['closes'], dtype=float)
            
            if len(closes) < period + 1:
                return None
            
            # 변화량 계산
            deltas = np.diff(closes)
            
            # 상승/하락 분리
            seed = deltas[:period + 1]
            up = seed[seed >= 0].sum() / period
            down = -seed[seed < 0].sum() / period
            
            rs = up / down if down != 0 else 0
            rsi = 100.0 - (100.0 / (1.0 + rs)) if rs > 0 else 0
            
            return rsi
            
        except Exception as e:
            print(f"❌ RSI 계산 오류: {e}")
            return None
    
    def calculate_bollinger_bands(self, period=20, std_dev=2):
        """
        볼린저 밴드 계산
        Returns: {upper, middle, lower, bandwidth}
        """
        try:
            closes = np.array(self.data['closes'], dtype=float)
            
            if len(closes) < period:
                return None
            
            # 중간선 (20일 SMA)
            middle = np.mean(closes[-period:])
            
            # 표준편차
            std = np.std(closes[-period:])
            
            # 상단/하단
            upper = middle + (std * std_dev)
            lower = middle - (std * std_dev)
            
            # 대역폭
            bandwidth = ((upper - lower) / middle) * 100 if middle != 0 else 0
            
            return {
                'upper': upper,
                'middle': middle,
                'lower': lower,
                'bandwidth': bandwidth,
                'position': self._get_bb_position(closes[-1], upper, lower, middle)
            }
            
        except Exception as e:
            print(f"❌ 볼린저 밴드 계산 오류: {e}")
            return None
    
    def calculate_moving_averages(self):
        """
        이동평균선 계산
        Returns: {ma20, ma50, ma200, trend}
        """
        try:
            closes = np.array(self.data['closes'], dtype=float)
            
            ma20 = np.mean(closes[-20:]) if len(closes) >= 20 else None
            ma50 = np.mean(closes[-50:]) if len(closes) >= 50 else None
            ma200 = np.mean(closes[-60:]) if len(closes) >= 60 else None  # 60일 사용
            
            current = closes[-1]
            
            # 추세 판정
            trend = self._get_ma_trend(current, ma20, ma50, ma200)
            
            return {
                'ma20': ma20,
                'ma50': ma50,
                'ma200': ma200,
                'current': current,
                'trend': trend
            }
            
        except Exception as e:
            print(f"❌ 이동평균선 계산 오류: {e}")
            return None
    
    def calculate_score(self):
        """
        종합 점수 계산 (0-100)
        4개 지표 동등 가중치 (25%)
        """
        try:
            scores = {}
            
            # 1. MACD 점수
            macd = self.calculate_macd()
            if macd:
                if macd['histogram'] > 0:
                    macd_score = min(100, 50 + (macd['histogram'] / abs(macd['macd_line']) * 50)) if macd['macd_line'] != 0 else 50
                else:
                    macd_score = max(0, 50 - (abs(macd['histogram']) / abs(macd['macd_line']) * 50)) if macd['macd_line'] != 0 else 50
                scores['MACD'] = min(100, max(0, macd_score))
            else:
                scores['MACD'] = 50
            
            # 2. RSI 점수
            rsi = self.calculate_rsi()
            if rsi is not None:
                if 30 <= rsi <= 70:
                    scores['RSI'] = 50 + (rsi - 50) * 0.5  # 중립대 점수
                else:
                    scores['RSI'] = rsi  # 과매수/과매도 신호
            else:
                scores['RSI'] = 50
            
            # 3. 볼린저 밴드 점수
            bb = self.calculate_bollinger_bands()
            if bb:
                position = bb['position']
                if position == 'upper':
                    scores['BB'] = 70  # 과매수 신호
                elif position == 'lower':
                    scores['BB'] = 30  # 과매도 신호
                else:
                    scores['BB'] = 50  # 중립
            else:
                scores['BB'] = 50
            
            # 4. 이동평균선 점수
            ma = self.calculate_moving_averages()
            if ma:
                trend = ma['trend']
                if trend == 'STRONG_UPTREND':
                    scores['MA'] = 80
                elif trend == 'UPTREND':
                    scores['MA'] = 65
                elif trend == 'DOWNTREND':
                    scores['MA'] = 35
                elif trend == 'STRONG_DOWNTREND':
                    scores['MA'] = 20
                else:
                    scores['MA'] = 50
            else:
                scores['MA'] = 50
            
            # 종합 점수 (평균)
            total_score = (scores['MACD'] + scores['RSI'] + scores['BB'] + scores['MA']) / 4
            
            return {
                'total': total_score,
                'macd': scores['MACD'],
                'rsi': scores['RSI'],
                'bb': scores['BB'],
                'ma': scores['MA'],
                'breakdown': scores
            }
            
        except Exception as e:
            print(f"❌ 점수 계산 오류: {e}")
            return None
    
    def analyze(self, symbol: str, days: int = 60):
        """
        전체 분석 수행
        """
        try:
            print("=" * 80)
            print(f"기술지표 분석: {symbol}")
            print("=" * 80)
            
            # Step 1: 데이터 수집
            if not self.fetch_data(symbol, days):
                return None
            
            # Step 2: 지표 계산
            macd = self.calculate_macd()
            rsi = self.calculate_rsi()
            bb = self.calculate_bollinger_bands()
            ma = self.calculate_moving_averages()
            score = self.calculate_score()
            
            # Step 3: 결과 출력
            self.format_report(symbol, macd, rsi, bb, ma, score)
            
            return {
                'symbol': symbol,
                'macd': macd,
                'rsi': rsi,
                'bb': bb,
                'ma': ma,
                'score': score,
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            print(f"❌ 분석 오류: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def format_report(self, symbol, macd, rsi, bb, ma, score):
        """분석 결과 보고서 출력"""
        try:
            print(f"\n【{symbol} 기술지표 분석 결과】")
            print("=" * 80)
            
            # MACD
            if macd:
                print(f"\n【MACD】")
                print(f"  MACD Line:    {macd['macd_line']:>10.2f}")
                print(f"  Signal Line:  {macd['signal_line']:>10.2f}")
                print(f"  Histogram:    {macd['histogram']:>10.2f} {'🟢 매수신호' if macd['histogram'] > 0 else '🔴 매도신호'}")
            
            # RSI
            if rsi is not None:
                print(f"\n【RSI(14)】")
                print(f"  RSI:          {rsi:>10.2f}")
                if rsi >= 70:
                    print(f"  상태:         과매수 (매도신호) 🔴")
                elif rsi >= 60:
                    print(f"  상태:         강세 🟢")
                elif rsi >= 40:
                    print(f"  상태:         중립 ⚪")
                elif rsi >= 30:
                    print(f"  상태:         약세 🔴")
                else:
                    print(f"  상태:         과매도 (매수신호) 🟢")
            
            # 볼린저 밴드
            if bb:
                print(f"\n【볼린저 밴드(20, 2)】")
                print(f"  상단:         {bb['upper']:>10.2f}")
                print(f"  중앙:         {bb['middle']:>10.2f}")
                print(f"  하단:         {bb['lower']:>10.2f}")
                print(f"  대역폭:       {bb['bandwidth']:>10.2f}%")
                print(f"  위치:         {bb['position']:>10} {'(과매수)🔴' if bb['position'] == 'upper' else '(과매도)🟢' if bb['position'] == 'lower' else '(중립)⚪'}")
            
            # 이동평균선
            if ma:
                print(f"\n【이동평균선】")
                if ma['ma20']:
                    print(f"  MA20:         {ma['ma20']:>10.2f}")
                if ma['ma50']:
                    print(f"  MA50:         {ma['ma50']:>10.2f}")
                if ma['ma200']:
                    print(f"  MA200:        {ma['ma200']:>10.2f}")
                print(f"  현재가:       {ma['current']:>10.2f}")
                print(f"  추세:         {ma['trend']:>10}")
            
            # 종합 점수
            if score:
                print(f"\n【종합 점수】")
                print(f"  ────────────────────────────────────")
                print(f"  MACD:         {score['macd']:>10.1f}/100")
                print(f"  RSI:          {score['rsi']:>10.1f}/100")
                print(f"  BB:           {score['bb']:>10.1f}/100")
                print(f"  MA:           {score['ma']:>10.1f}/100")
                print(f"  ────────────────────────────────────")
                print(f"  종합 점수:    {score['total']:>10.1f}/100")
                
                if score['total'] >= 70:
                    signal = "강한 매수 신호 🟢🟢"
                elif score['total'] >= 60:
                    signal = "매수 신호 🟢"
                elif score['total'] >= 55:
                    signal = "약한 매수 신호 🟡"
                elif score['total'] >= 45:
                    signal = "중립 ⚪"
                elif score['total'] >= 40:
                    signal = "약한 매도 신호 🟡"
                elif score['total'] >= 30:
                    signal = "매도 신호 🔴"
                else:
                    signal = "강한 매도 신호 🔴🔴"
                
                print(f"  신호:         {signal}")
            
            print("\n" + "=" * 80)
            
        except Exception as e:
            print(f"❌ 보고서 출력 오류: {e}")
    
    # ============================================================================
    # 헬퍼 메서드
    # ============================================================================
    
    @staticmethod
    def _calculate_ema(data, period):
        """지수이동평균 계산"""
        ema = np.zeros(len(data))
        ema[0] = data[0]
        k = 2.0 / (period + 1)
        for i in range(1, len(data)):
            ema[i] = data[i] * k + ema[i - 1] * (1 - k)
        return ema
    
    @staticmethod
    def _get_bb_position(current, upper, lower, middle):
        """볼린저 밴드 내 현재가 위치"""
        if current >= upper:
            return 'upper'
        elif current <= lower:
            return 'lower'
        else:
            return 'middle'
    
    @staticmethod
    def _get_ma_trend(current, ma20, ma50, ma200):
        """이동평균선 기반 추세 판정"""
        if ma200 is None:
            if ma50 is None:
                return 'UNKNOWN'
            if current > ma20 > ma50:
                return 'UPTREND'
            elif current < ma20 < ma50:
                return 'DOWNTREND'
            else:
                return 'NEUTRAL'
        
        if current > ma20 > ma50 > ma200:
            return 'STRONG_UPTREND'
        elif current > ma20 > ma50 and current > ma200:
            return 'UPTREND'
        elif current < ma20 < ma50 < ma200:
            return 'STRONG_DOWNTREND'
        elif current < ma20 < ma50 and current < ma200:
            return 'DOWNTREND'
        else:
            return 'NEUTRAL'


# ============================================================================
# 메인: 테스트
# ============================================================================

if __name__ == "__main__":
    try:
        analyzer = TechnicalAnalyzer()
        
        # KOSPI 분석
        result = analyzer.analyze("0001", days=60)
        
        if result:
            print(f"\n✅ 분석 완료!")
            print(f"   종합 점수: {result['score']['total']:.1f}/100")
        
    except Exception as e:
        print(f"❌ 오류: {e}")
        import traceback
        traceback.print_exc()