"""
TechnicalAnalyzer - 기술지표 분석기 (BaseAnalyzer 상속)
KIS API 기반 60일 데이터 수집 + 기술지표 계산 + 종합 점수 산출
"""

import sys
import os
from typing import Dict, Any
import logging

# 프로젝트 경로 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from market_intelligence.base_analyzer import BaseAnalyzer
from data.kis_client import KISClient
from data.technical_indicators import TechnicalIndicators

logger = logging.getLogger(__name__)


class TechnicalAnalyzer(BaseAnalyzer):
    """
    기술지표 분석기
    
    MACD, RSI, 볼린저밴드, 이동평균선을 계산하고 종합 점수 산출
    BaseAnalyzer의 4단계 파이프라인을 구현:
    1. validate() - 데이터 검증
    2. analyze() - 기술지표 계산
    3. get_score() - 점수 산출
    4. run() - 메인 실행 (BaseAnalyzer의 run() 메서드)
    """
    
    def __init__(self):
        """초기화"""
        super().__init__(name="technical", weight=0.18)
        
        # KIS API 클라이언트
        self.kis_client = KISClient()
        
        # 기술지표 가중치 설정
        self.indicator_weights = {
            "macd": 0.30,
            "rsi": 0.30,
            "bollinger_band": 0.20,
            "moving_average": 0.20
        }
        
        logger.info(f"✅ TechnicalAnalyzer 초기화 완료 (weight={self.weight})")
    
    def validate(self, data: Dict[str, Any]) -> bool:
        """
        데이터 검증
        
        Args:
            data: 검증할 데이터
            
        Returns:
            bool: 데이터 유효성 여부
        """
        try:
            # 필수 필드 확인
            required_fields = ["symbol", "dates", "opens", "highs", "lows", "closes", "volumes"]
            
            if not all(field in data for field in required_fields):
                logger.warning(f"❌ 필수 필드 누락: {required_fields}")
                return False
            
            # 최소 60개 데이터 포인트 필요
            min_points = 60
            if len(data["closes"]) < min_points:
                logger.warning(f"❌ 데이터 부족: {len(data['closes'])}/{min_points}")
                return False
            
            # 데이터 타입 확인
            if not isinstance(data["closes"], (list, tuple)):
                logger.warning("❌ closes 데이터 타입 오류")
                return False
            
            logger.debug(f"✅ 데이터 검증 성공 ({len(data['closes'])}개 포인트)")
            return True
            
        except Exception as e:
            logger.error(f"❌ 데이터 검증 오류: {e}")
            return False
    
    def analyze(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        기술지표 분석 수행
        
        Args:
            data: 분석 데이터
            
        Returns:
            dict: 분석 결과
        """
        try:
            symbol = data.get("symbol", "UNKNOWN")
            closes = data.get("closes", [])
            opens = data.get("opens", [])
            highs = data.get("highs", [])
            lows = data.get("lows", [])
            
            logger.info(f"📊 {symbol} 기술지표 분석 시작 ({len(closes)}개 캔들)")
            
            result = {
                "symbol": symbol,
                "data_points": len(closes),
                "indicators": {}
            }
            
            # 1️⃣ MACD 계산
            macd_result = TechnicalIndicators.calculate_macd(closes)
            if macd_result:
                result["indicators"]["macd"] = macd_result
                logger.debug(f"✅ MACD 계산 완료: {macd_result}")
            else:
                logger.warning("⚠️ MACD 계산 실패")
                result["indicators"]["macd"] = None
            
            # 2️⃣ RSI 계산
            rsi_result = self._calculate_rsi(closes)
            if rsi_result is not None:
                result["indicators"]["rsi"] = rsi_result
                logger.debug(f"✅ RSI 계산 완료: {rsi_result:.2f}")
            else:
                logger.warning("⚠️ RSI 계산 실패")
                result["indicators"]["rsi"] = None
            
            # 3️⃣ 볼린저 밴드 계산
            bb_result = self._calculate_bollinger_bands(closes)
            if bb_result:
                result["indicators"]["bollinger_band"] = bb_result
                logger.debug(f"✅ 볼린저 밴드 계산 완료")
            else:
                logger.warning("⚠️ 볼린저 밴드 계산 실패")
                result["indicators"]["bollinger_band"] = None
            
            # 4️⃣ 이동평균선 계산
            ma_result = self._calculate_moving_averages(closes)
            if ma_result:
                result["indicators"]["moving_average"] = ma_result
                logger.debug(f"✅ 이동평균선 계산 완료")
            else:
                logger.warning("⚠️ 이동평균선 계산 실패")
                result["indicators"]["moving_average"] = None
            
            logger.info(f"✅ {symbol} 분석 완료")
            return result
            
        except Exception as e:
            logger.error(f"❌ 분석 오류: {e}", exc_info=True)
            return {"symbol": data.get("symbol", "UNKNOWN"), "indicators": {}, "error": str(e)}
    
    def get_score(self, analysis_result: Dict[str, Any]) -> float:
        """
        분석 결과로부터 점수 계산
        
        각 기술지표별로 0-100 점수 산출 후 가중평균
        
        Args:
            analysis_result: analyze() 반환값
            
        Returns:
            float: 0-100 범위의 종합 점수
        """
        try:
            indicators = analysis_result.get("indicators", {})
            scores = {}
            
            # 1️⃣ MACD 점수
            macd = indicators.get("macd")
            if macd and macd.get("macd_value") is not None:
                macd_score = self._score_macd(macd)
                scores["macd"] = macd_score
                logger.debug(f"📊 MACD 점수: {macd_score:.1f}")
            else:
                scores["macd"] = 50.0  # 기본값
            
            # 2️⃣ RSI 점수
            rsi = indicators.get("rsi")
            if rsi is not None:
                rsi_score = self._score_rsi(rsi)
                scores["rsi"] = rsi_score
                logger.debug(f"📊 RSI 점수: {rsi_score:.1f}")
            else:
                scores["rsi"] = 50.0
            
            # 3️⃣ 볼린저 밴드 점수
            bb = indicators.get("bollinger_band")
            if bb:
                bb_score = self._score_bollinger_band(bb)
                scores["bollinger_band"] = bb_score
                logger.debug(f"📊 BB 점수: {bb_score:.1f}")
            else:
                scores["bollinger_band"] = 50.0
            
            # 4️⃣ 이동평균선 점수
            ma = indicators.get("moving_average")
            if ma:
                ma_score = self._score_moving_average(ma)
                scores["moving_average"] = ma_score
                logger.debug(f"📊 MA 점수: {ma_score:.1f}")
            else:
                scores["moving_average"] = 50.0
            
            # 종합 점수 (가중평균)
            total_score = (
                scores["macd"] * self.indicator_weights["macd"] +
                scores["rsi"] * self.indicator_weights["rsi"] +
                scores["bollinger_band"] * self.indicator_weights["bollinger_band"] +
                scores["moving_average"] * self.indicator_weights["moving_average"]
            )
            
            # 0-100 범위로 정규화
            total_score = max(0, min(100, total_score))
            
            logger.info(f"✅ 종합 점수 계산 완료: {total_score:.1f}/100")
            logger.debug(f"   MACD: {scores['macd']:.1f}, RSI: {scores['rsi']:.1f}, BB: {scores['bollinger_band']:.1f}, MA: {scores['moving_average']:.1f}")
            
            return total_score
            
        except Exception as e:
            logger.error(f"❌ 점수 계산 오류: {e}", exc_info=True)
            return 50.0  # 기본값
    
    # ============================================================================
    # 점수 계산 헬퍼 메서드
    # ============================================================================
    
    @staticmethod
    def _score_macd(macd: Dict[str, float]) -> float:
        """MACD 기반 점수 (0-100)"""
        macd_value = macd.get("macd_value", 0)
        histogram = macd.get("histogram", 0)
        
        if histogram > 0:
            # 양수: 매수 신호
            if macd_value > 0:
                return min(100, 50 + abs(histogram) * 10)
            else:
                return min(100, 50 + histogram * 5)
        else:
            # 음수: 매도 신호
            if macd_value < 0:
                return max(0, 50 - abs(histogram) * 10)
            else:
                return max(0, 50 - abs(histogram) * 5)
    
    @staticmethod
    def _score_rsi(rsi: float) -> float:
        """RSI 기반 점수 (0-100)"""
        # RSI 직접 사용 (30 이하: 과매도, 70 이상: 과매수)
        if rsi >= 70:
            return max(0, 100 - (rsi - 70) * 2)  # 과매수: 감점
        elif rsi <= 30:
            return min(100, 30 + (30 - rsi) * 2)  # 과매도: 가점
        else:
            return rsi  # 정상 범위
    
    @staticmethod
    def _score_bollinger_band(bb: Dict[str, float]) -> float:
        """볼린저 밴드 기반 점수 (0-100)"""
        position = bb.get("position", "middle")
        
        if position == "upper":
            return 30  # 과매수
        elif position == "lower":
            return 70  # 과매도
        else:
            return 50  # 중립
    
    @staticmethod
    def _score_moving_average(ma: Dict[str, Any]) -> float:
        """이동평균선 기반 점수 (0-100)"""
        current = ma.get("current", 0)
        ma20 = ma.get("ma20", 0)
        ma50 = ma.get("ma50", 0)
        ma200 = ma.get("ma200", 0)
        
        trend = ma.get("trend", "UNKNOWN")
        
        # 추세 기반 점수
        if trend == "STRONG_UPTREND":
            return 80
        elif trend == "UPTREND":
            return 65
        elif trend == "NEUTRAL":
            return 50
        elif trend == "DOWNTREND":
            return 35
        elif trend == "STRONG_DOWNTREND":
            return 20
        else:
            return 50
    
    # ============================================================================
    # 지표 계산 헬퍼 메서드
    # ============================================================================
    
    @staticmethod
    def _calculate_rsi(prices, period=14):
        """RSI 계산 (Relative Strength Index)"""
        try:
            if len(prices) < period + 1:
                return None
            
            deltas = []
            for i in range(1, len(prices)):
                deltas.append(prices[i] - prices[i-1])
            
            seed = deltas[:period + 1]
            up = sum(d for d in seed if d >= 0) / period
            down = -sum(d for d in seed if d < 0) / period
            
            if down == 0:
                return 100.0 if up > 0 else 0.0
            
            rs = up / down
            rsi = 100.0 - (100.0 / (1.0 + rs))
            
            return rsi
            
        except Exception as e:
            logger.error(f"RSI 계산 오류: {e}")
            return None
    
    @staticmethod
    def _calculate_bollinger_bands(prices, period=20, std_dev=2):
        """볼린저 밴드 계산"""
        try:
            if len(prices) < period:
                return None
            
            recent_prices = prices[-period:]
            
            # 중간선 (이동평균)
            middle = sum(recent_prices) / period
            
            # 표준편차
            variance = sum((p - middle) ** 2 for p in recent_prices) / period
            std = variance ** 0.5
            
            # 상단/하단
            upper = middle + (std * std_dev)
            lower = middle - (std * std_dev)
            
            # 현재가 위치
            current = prices[-1]
            if current >= upper:
                position = "upper"
            elif current <= lower:
                position = "lower"
            else:
                position = "middle"
            
            return {
                "upper": upper,
                "middle": middle,
                "lower": lower,
                "position": position
            }
            
        except Exception as e:
            logger.error(f"볼린저 밴드 계산 오류: {e}")
            return None
    
    @staticmethod
    def _calculate_moving_averages(prices):
        """이동평균선 계산 (MA20, MA50, MA200)"""
        try:
            ma20 = sum(prices[-20:]) / 20 if len(prices) >= 20 else None
            ma50 = sum(prices[-50:]) / 50 if len(prices) >= 50 else None
            ma200 = sum(prices[-60:]) / 60 if len(prices) >= 60 else None
            
            current = prices[-1]
            
            # 추세 판정
            if ma200 is not None:
                if current > ma20 > ma50 > ma200:
                    trend = "STRONG_UPTREND"
                elif current > ma20 > ma50 and current > ma200:
                    trend = "UPTREND"
                elif current < ma20 < ma50 < ma200:
                    trend = "STRONG_DOWNTREND"
                elif current < ma20 < ma50 and current < ma200:
                    trend = "DOWNTREND"
                else:
                    trend = "NEUTRAL"
            elif ma50 is not None:
                if current > ma20 > ma50:
                    trend = "UPTREND"
                elif current < ma20 < ma50:
                    trend = "DOWNTREND"
                else:
                    trend = "NEUTRAL"
            else:
                trend = "UNKNOWN"
            
            return {
                "ma20": ma20,
                "ma50": ma50,
                "ma200": ma200,
                "current": current,
                "trend": trend
            }
            
        except Exception as e:
            logger.error(f"이동평균선 계산 오류: {e}")
            return None


# ============================================================================
# 테스트
# ============================================================================

if __name__ == "__main__":
    import json
    
    try:
        # 로깅 설정
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        
        print("=" * 80)
        print("TechnicalAnalyzer 테스트")
        print("=" * 80)
        
        # 1️⃣ 분석기 생성
        analyzer = TechnicalAnalyzer()
        
        # 2️⃣ KIS API에서 데이터 수집
        print("\n【Step 1】데이터 수집...")
        data = analyzer.kis_client.get_daily_price("0001", days=60)
        
        if not data or len(data.get("closes", [])) == 0:
            print("❌ 데이터 수집 실패")
            exit(1)
        
        print(f"✅ {len(data['closes'])}일치 데이터 수집 완료")
        
        # 3️⃣ BaseAnalyzer의 run() 메서드 호출 (4단계 파이프라인)
        print("\n【Step 2】분석 실행 (run() 파이프라인)...")
        result = analyzer.run(data)
        
        # 4️⃣ 결과 출력
        print("\n【분석 결과】")
        print(json.dumps(result, indent=2, ensure_ascii=False))
        
        # 5️⃣ 신호 판정
        score = result.get("score", 0)
        if score >= 70:
            signal = "🟢 강한 매수 신호"
        elif score >= 60:
            signal = "🟢 매수 신호"
        elif score >= 55:
            signal = "🟡 약한 매수 신호"
        elif score >= 45:
            signal = "⚪ 중립"
        elif score >= 40:
            signal = "🟡 약한 매도 신호"
        elif score >= 30:
            signal = "🔴 매도 신호"
        else:
            signal = "🔴 강한 매도 신호"
        
        print(f"\n【신호】")
        print(f"  점수: {score:.1f}/100")
        print(f"  신호: {signal}")
        
        print("\n" + "=" * 80)
        print("✅ 테스트 완료!")
        print("=" * 80)
        
    except Exception as e:
        print(f"❌ 테스트 오류: {e}")
        import traceback
        traceback.print_exc()