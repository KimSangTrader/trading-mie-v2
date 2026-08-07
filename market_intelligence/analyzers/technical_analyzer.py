from market_intelligence.base_analyzer import BaseAnalyzer
from typing import Dict, Any
import logging
import math

logger = logging.getLogger(__name__)

class TechnicalAnalyzer(BaseAnalyzer):
    """기술적 분석기 (한국 주식 시장, 2026년 8월 기준)"""
    
    def __init__(self):
        super().__init__(name="technical", weight=0.18)
        
        # 기술 지표 설정
        self.technical_indicators = {
            "macd": {
                "display_name": "MACD",
                "description": "Moving Average Convergence Divergence",
                "weight": 0.30,
                "current_status": "약세 (음수)"
            },
            "rsi": {
                "display_name": "RSI",
                "description": "Relative Strength Index",
                "weight": 0.30,
                "current_status": "과도한 매도 (30 이하)"
            },
            "bollinger_band": {
                "display_name": "볼린저 밴드",
                "description": "Bollinger Bands",
                "weight": 0.20,
                "current_status": "하단 밴드 근처"
            },
            "moving_average": {
                "display_name": "이동평균선",
                "description": "Moving Averages",
                "weight": 0.20,
                "current_status": "약세 정렬 (5MA < 20MA < 60MA)"
            }
        }
    
    def validate(self, data: Dict[str, Any]) -> bool:
        """입력 데이터 검증"""
        # 최소 2개 이상의 기술 지표 데이터 필요
        required_indicators = ["macd_value", "rsi_value"]
        return all(key in data for key in required_indicators)
    
    def analyze(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        기술적 분석 수행
        
        Returns Dict with technical indicator scores
        """
        try:
            # 1. MACD 분석
            macd_score = self._analyze_macd(data.get("macd_value", 0))
            
            # 2. RSI 분석
            rsi_score = self._analyze_rsi(data.get("rsi_value", 50))
            
            # 3. 볼린저 밴드 분석
            bb_score = self._analyze_bollinger_band(
                data.get("price", 6258.77),
                data.get("bb_upper", 6600),
                data.get("bb_lower", 5900),
                data.get("bb_middle", 6250)
            )
            
            # 4. 이동평균선 분석
            ma_score = self._analyze_moving_average(
                data.get("ma5", 6280),
                data.get("ma20", 6350),
                data.get("ma60", 6400)
            )
            
            # 5. 종합 점수 (가중 평균)
            technical_score = (
                macd_score * 0.30 +
                rsi_score * 0.30 +
                bb_score * 0.20 +
                ma_score * 0.20
            )
            
            # 6. 기술 신호 분류
            signal = self._classify_signal(technical_score)
            
            logger.info(
                f"Technical Analysis: MACD={macd_score:.1f}, "
                f"RSI={rsi_score:.1f}, BB={bb_score:.1f}, "
                f"MA={ma_score:.1f}, Score={technical_score:.1f}, "
                f"Signal={signal}"
            )
            
            return {
                "macd_score": macd_score,
                "rsi_score": rsi_score,
                "bollinger_band_score": bb_score,
                "moving_average_score": ma_score,
                "technical_score": technical_score,
                "signal": signal,
                "indicators": {
                    "macd": {"score": macd_score, "value": data.get("macd_value", 0)},
                    "rsi": {"score": rsi_score, "value": data.get("rsi_value", 50)},
                    "bollinger_band": {"score": bb_score},
                    "moving_average": {"score": ma_score}
                }
            }
            
        except Exception as e:
            logger.error(f"Technical analysis error: {e}")
            return {
                "technical_score": 50,
                "error": str(e),
                "signal": "unknown"
            }
    
    def get_score(self, analysis_result: Dict[str, Any]) -> float:
        """
        분석 결과로부터 최종 기술 점수 계산
        
        Args:
            analysis_result: analyze() 반환값 (Dict)
        
        Returns:
            0~100 정규화된 점수
        """
        try:
            score = analysis_result.get("technical_score", 50)
            score = max(0, min(100, score))  # 0~100 범위 보장
            
            signal = analysis_result.get("signal", "unknown")
            
            logger.info(
                f"Technical final score: Signal={signal}, "
                f"Score={score:.1f}"
            )
            
            return score
            
        except Exception as e:
            logger.error(f"Score calculation error: {e}")
            return 50.0
    
    def _analyze_macd(self, macd_value: float) -> float:
        """
        MACD 분석
        
        Args:
            macd_value: MACD 값 (음수=약세, 양수=강세)
        
        Returns:
            0~100 점수
        """
        # MACD 기준값: -50 ~ +50
        # -50 = 0점, 0 = 50점, +50 = 100점
        
        if macd_value >= 30:
            return min(100, 70 + (macd_value - 30) / 2)  # 강한 강세
        elif macd_value >= 10:
            return 50 + (macd_value - 10) / 4 * 20  # 약한 강세
        elif macd_value >= -10:
            return 50 + (macd_value + 10) / 20 * 50  # 중립
        elif macd_value >= -30:
            return 30 + (macd_value + 30) / 20 * 20  # 약한 약세
        else:
            return max(0, 30 + (macd_value + 30) / 50 * 30)  # 강한 약세
    
    def _analyze_rsi(self, rsi_value: float) -> float:
        """
        RSI 분석
        
        Args:
            rsi_value: RSI 값 (0~100)
        
        Returns:
            0~100 점수
        """
        # RSI 기준:
        # 70 이상: 과매수 (약세 신호)
        # 30 이하: 과매도 (강세 신호, 회복 기회)
        # 30~70: 중립
        
        if rsi_value >= 70:
            # 과매수: 70~100 → 30~0 (역으로)
            return max(0, 50 - (rsi_value - 70) / 3)
        elif rsi_value >= 50:
            # 약간 강세: 50~70 → 50~60
            return 50 + (rsi_value - 50) / 2
        elif rsi_value >= 30:
            # 중립: 30~50 → 40~50
            return 40 + (rsi_value - 30) / 2
        else:
            # 과매도: 0~30 → 70~40 (회복 신호)
            return 70 - (30 - rsi_value) / 3
    
    def _analyze_bollinger_band(self, price: float, upper: float, middle: float, lower: float) -> float:
        """
        볼린저 밴드 분석
        
        Args:
            price: 현재 가격
            upper: 상단 밴드
            middle: 중간선 (MA20)
            lower: 하단 밴드
        
        Returns:
            0~100 점수
        """
        # 밴드폭 계산
        bandwidth = upper - lower
        if bandwidth == 0:
            return 50
        
        # 정규화 (0~100)
        normalized = (price - lower) / bandwidth * 100
        normalized = max(0, min(100, normalized))
        
        # 해석:
        # 0~20: 하단 근처 (극단적 약세, 회복 기회)
        # 20~40: 하단 구간 (약세)
        # 40~60: 중간 구간 (중립)
        # 60~80: 상단 구간 (강세)
        # 80~100: 상단 근처 (극단적 강세, 조정 가능성)
        
        if normalized <= 20:
            return 70 - normalized / 2  # 극단적 약세 = 회복 신호 (70~60)
        elif normalized <= 40:
            return 60 - (normalized - 20) / 2  # 약세 (60~50)
        elif normalized <= 60:
            return 40 + (normalized - 40) / 4  # 중립 (40~55)
        elif normalized <= 80:
            return 55 + (normalized - 60) / 4  # 강세 (55~70)
        else:
            return 70 + (100 - normalized) / 2  # 극단적 강세 (70~60)
    
    def _analyze_moving_average(self, ma5: float, ma20: float, ma60: float) -> float:
        """
        이동평균선 분석 (5MA, 20MA, 60MA)
        
        Args:
            ma5: 5일 이동평균선
            ma20: 20일 이동평균선
            ma60: 60일 이동평균선
        
        Returns:
            0~100 점수
        """
        # 정렬 상태 확인
        # 강세: 5MA > 20MA > 60MA (황금 교차)
        # 약세: 5MA < 20MA < 60MA (사망 교차)
        # 중립: 혼합
        
        if ma5 > ma20 > ma60:
            # 강세 정렬
            return 75 + min(25, (ma5 - ma20) / ma20 * 50)
        elif ma5 > ma20 and ma20 < ma60:
            # 약한 강세
            return 55 + (ma5 - ma20) / ma20 * 20
        elif ma5 > ma20 and ma20 > ma60:
            # 강한 강세
            return 75
        elif ma5 < ma20 < ma60:
            # 약세 정렬 (사망 교차)
            return 25 - min(25, (ma20 - ma5) / ma20 * 50)
        elif ma5 < ma20 and ma20 > ma60:
            # 약한 약세
            return 45 - (ma20 - ma5) / ma20 * 20
        else:
            # 혼합
            return 50
    
    def _classify_signal(self, score: float) -> str:
        """기술 신호 분류"""
        if score >= 70:
            return "강한 매수"
        elif score >= 55:
            return "약한 매수"
        elif score >= 45:
            return "중립"
        elif score >= 30:
            return "약한 매도"
        else:
            return "강한 매도"