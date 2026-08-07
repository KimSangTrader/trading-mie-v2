from market_intelligence.base_analyzer import BaseAnalyzer
from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)

class MarketAnalyzer(BaseAnalyzer):
    """시장 지표 분석기 (한국 주식 시장, 2026년 8월 기준)"""
    
    def __init__(self):
        super().__init__(name="market", weight=0.18)
        # 2026년 8월 기준값 (실시간 데이터 기반)
        
        # KOSPI 기준값 (현재: 6,258.77)
        self.kospi_current = 6258.77
        self.kospi_bull_level = 6800   # 강세: 8% 상승
        self.kospi_bear_level = 5800   # 약세: 7% 하락
        
        # KOSDAQ 기준값 (현재: 798.81)
        self.kosdaq_current = 798.81
        self.kosdaq_bull_level = 900   # 강세: 13% 상승
        self.kosdaq_bear_level = 700   # 약세: 12% 하락
        
        # 시장 거래량 기준값
        self.volume_normal = 1350000000  # 1,350억 (평상시)
        self.volume_high = 1800000000    # 1,800억 (활발)
        self.volume_low = 1000000000     # 1,000억 (저조)
    
    def validate(self, data: Dict[str, Any]) -> bool:
        """입력 데이터 검증"""
        required_keys = ["kospi_index", "kosdaq_index", "market_volume"]
        return all(key in data for key in required_keys)
    
    def analyze(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        한국 주식 시장 지표 분석 (2026년 8월 7일 기준)
        
        Returns Dict with score and details
        """
        try:
            # 1. KOSPI 지수 분석 (40% 가중치)
            kospi = data.get("kospi_index", self.kospi_current)
            kospi_score = self._analyze_kospi(kospi)
            
            # 2. KOSDAQ 지수 분석 (30% 가중치)
            kosdaq = data.get("kosdaq_index", self.kosdaq_current)
            kosdaq_score = self._analyze_kosdaq(kosdaq)
            
            # 3. 시장 거래량 분석 (30% 가중치)
            volume = data.get("market_volume", self.volume_normal)
            volume_score = self._analyze_volume(volume)
            
            # 4. 가중 평균 (아직 최종 점수 계산 안 함 - get_score에서)
            raw_score = (
                kospi_score * 0.4 +
                kosdaq_score * 0.3 +
                volume_score * 0.3
            )
            
            # 5. Dict 반환 (get_score에서 처리)
            return {
                "raw_score": raw_score,
                "kospi": {
                    "value": kospi,
                    "score": kospi_score,
                    "weight": 0.4
                },
                "kosdaq": {
                    "value": kosdaq,
                    "score": kosdaq_score,
                    "weight": 0.3
                },
                "volume": {
                    "value": volume,
                    "score": volume_score,
                    "weight": 0.3
                },
                "timestamp": None
            }
            
        except Exception as e:
            logger.error(f"Market analysis error: {e}")
            return {
                "raw_score": 0,
                "kospi": {"score": 0},
                "kosdaq": {"score": 0},
                "volume": {"score": 0},
                "error": str(e)
            }
    
    def get_score(self, analysis_result: Dict[str, Any]) -> float:
        """
        분석 결과로부터 최종 점수 계산
        
        Args:
            analysis_result: analyze() 반환값 (Dict)
        
        Returns:
            0~100 정규화된 점수
        """
        try:
            # raw_score를 그대로 반환 (이미 0~100 범위)
            score = analysis_result.get("raw_score", 0)
            score = max(0, min(100, score))  # 0~100 범위 보장
            
            logger.info(
                f"Market final score: KOSPI={analysis_result['kospi'].get('score', 0):.1f}, "
                f"KOSDAQ={analysis_result['kosdaq'].get('score', 0):.1f}, "
                f"Volume={analysis_result['volume'].get('score', 0):.1f} "
                f"→ {score:.1f}"
            )
            
            return score
            
        except Exception as e:
            logger.error(f"Score calculation error: {e}")
            return 0.0
    
    def _analyze_kospi(self, kospi: float) -> float:
        """KOSPI 지수 분석"""
        base = 6300
        
        if kospi >= self.kospi_bull_level:
            return min(100, 75 + (kospi - self.kospi_bull_level) / 200)
        elif kospi >= base:
            return 50 + (kospi - base) / 500 * 25
        elif kospi >= self.kospi_bear_level:
            return 25 + (kospi - self.kospi_bear_level) / 500 * 25
        else:
            return max(0, (kospi / self.kospi_bear_level) * 25)
    
    def _analyze_kosdaq(self, kosdaq: float) -> float:
        """KOSDAQ 지수 분석"""
        base = 800
        
        if kosdaq >= self.kosdaq_bull_level:
            return min(100, 75 + (kosdaq - self.kosdaq_bull_level) / 50)
        elif kosdaq >= base:
            return 50 + (kosdaq - base) / 100 * 25
        elif kosdaq >= self.kosdaq_bear_level:
            return 25 + (kosdaq - self.kosdaq_bear_level) / 100 * 25
        else:
            return max(0, (kosdaq / self.kosdaq_bear_level) * 25)
    
    def _analyze_volume(self, volume: float) -> float:
        """시장 거래량 분석"""
        if volume >= self.volume_high:
            return min(100, 75 + (volume - self.volume_high) / 500000000)
        elif volume >= self.volume_normal:
            return 50 + (volume - self.volume_normal) / (self.volume_high - self.volume_normal) * 25
        elif volume >= self.volume_low:
            return 25 + (volume - self.volume_low) / (self.volume_normal - self.volume_low) * 25
        else:
            return max(0, (volume / self.volume_low) * 25)