"""
기술 지표 계산 유틸리티
MACD, RSI, 볼린저밴드, 이동평균

================================================================================
【변경 이력】
================================================================================
【2026-08-23】calculate_rsi() 반환값을 float()로 감쌈 (Phase 5-17 라이브 검증 중 발견)
- 배경: 이 함수는 원래 numpy 배열 연산(up/down이 np.float64)을 그대로 반환해서
  타입 힌트("-> float")와 달리 실제로는 numpy.float64를 돌려주고 있었다. 지금까지는
  이 값이 print/로그 출력에만 쓰여서 문제가 드러나지 않았는데, 이번에 StockAnalyzer가
  이 값을 계층형 순위 점수 계산에 쓰고 그 결과를 stock_hierarchical_scores 테이블에
  INSERT하면서 처음으로 psycopg2가 np.float64를 SQL 파라미터로 못 받아 에러가 났다
  (에러 메시지가 `np.float64(...)`를 스키마명으로 잘못 파싱해서 `schema "np" does not
  exist`로 나옴 - 실제 원인은 numpy 타입임). 근본 원인(여기)에서 한 번 고치고,
  market_intelligence/collectors/hierarchical_ranking_pipeline.py의 DB 저장
  경계에서도 방어적으로 float() 캐스팅을 추가해 다른 경로로 numpy 타입이 새어
  들어와도 막는다. calculate_ema/calculate_macd/calculate_bollinger_bands/
  calculate_moving_averages도 내부적으로 np.mean/np.std를 쓰는 건 동일하지만, 이번
  세션에서 실제로 DB INSERT까지 이어지는 경로는 calculate_rsi뿐이라 나머지는
  건드리지 않았다 - 라이브 검증 중 비슷한 에러가 나면 같은 패턴으로 고치면 된다.
================================================================================
"""

import numpy as np
from typing import List, Dict

class TechnicalIndicators:
    """기술 지표 계산"""
    
    @staticmethod
    def calculate_sma(prices: List[float], period: int) -> List[float]:
        """Simple Moving Average (단순 이동평균)"""
        return np.convolve(prices, np.ones(period)/period, mode='valid').tolist()
    
    @staticmethod
    def calculate_ema(prices: List[float], period: int) -> List[float]:
        """Exponential Moving Average (지수 이동평균)"""
        ema = []
        multiplier = 2 / (period + 1)
        
        sma = np.mean(prices[:period])
        ema.append(sma)
        
        for i in range(period, len(prices)):
            ema.append((prices[i] * multiplier) + (ema[-1] * (1 - multiplier)))
        
        return ema
    
    @staticmethod
    def calculate_macd(prices: List[float]) -> Dict:
        """MACD (Moving Average Convergence Divergence)"""
        ema12 = TechnicalIndicators.calculate_ema(prices, 12)
        ema26 = TechnicalIndicators.calculate_ema(prices, 26)
        
        # 두 EMA의 길이를 맞추기
        min_len = min(len(ema12), len(ema26))
        macd_line = [ema12[i] - ema26[i] for i in range(min_len)]
        
        # Signal line (MACD의 9일 EMA)
        signal = TechnicalIndicators.calculate_ema(macd_line, 9)
        
        # 최신값
        macd_value = macd_line[-1] if macd_line else 0
        signal_value = signal[-1] if signal else 0
        histogram = macd_value - signal_value
        
        return {
            "macd": macd_value,
            "signal": signal_value,
            "histogram": histogram
        }
    
    @staticmethod
    def calculate_rsi(prices: List[float], period: int = 14) -> float:
        """RSI (Relative Strength Index)"""
        if len(prices) < period:
            return 50
        
        deltas = np.diff(prices[-period-1:])
        seed = deltas[:period]
        
        up = seed[seed >= 0].sum() / period
        down = -seed[seed < 0].sum() / period
        
        rs = up / down if down != 0 else 0
        rsi = 100 - (100 / (1 + rs)) if rs >= 0 else 0

        return float(rsi)
    
    @staticmethod
    def calculate_bollinger_bands(prices: List[float], period: int = 20, std_dev: float = 2) -> Dict:
        """Bollinger Bands (볼린저 밴드)"""
        if len(prices) < period:
            return {"upper": 0, "middle": 0, "lower": 0, "width": 0}
        
        sma = np.mean(prices[-period:])
        std = np.std(prices[-period:])
        
        upper = sma + (std * std_dev)
        lower = sma - (std * std_dev)
        
        return {
            "upper": upper,
            "middle": sma,
            "lower": lower,
            "width": upper - lower
        }
    
    @staticmethod
    def calculate_moving_averages(prices: List[float]) -> Dict:
        """다양한 이동평균"""
        return {
            "ma5": np.mean(prices[-5:]) if len(prices) >= 5 else prices[-1],
            "ma20": np.mean(prices[-20:]) if len(prices) >= 20 else prices[-1],
            "ma60": np.mean(prices[-60:]) if len(prices) >= 60 else prices[-1]
        }
    
    @staticmethod
    def calculate_all(prices: List[float]) -> Dict:
        """모든 기술 지표 계산"""
        return {
            "macd": TechnicalIndicators.calculate_macd(prices),
            "rsi": TechnicalIndicators.calculate_rsi(prices),
            "bollinger": TechnicalIndicators.calculate_bollinger_bands(prices),
            "moving_averages": TechnicalIndicators.calculate_moving_averages(prices)
        }