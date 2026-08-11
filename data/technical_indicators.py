"""
기술 지표 계산 유틸리티
MACD, RSI, 볼린저밴드, 이동평균
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
        
        return rsi
    
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