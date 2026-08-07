from market_intelligence.base_analyzer import BaseAnalyzer
from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)

class NewsAnalyzer(BaseAnalyzer):
    """뉴스 감정 분석기 (한국 주식 시장, 2026년 8월 기준)"""
    
    def __init__(self):
        super().__init__(name="news", weight=0.09)
        
        # 뉴스 감정 분류 기준 (2026-08-07)
        self.sentiment_types = {
            "positive": {
                "display_name": "긍정적 뉴스",
                "base_score": 75,
                "examples": "ESG 정책 확대, 기관 매수, 실적 개선, 신기술",
                "weight": 0.35,
                "current_volume": 5  # 기사 수 (추정)
            },
            "neutral": {
                "display_name": "중립적 뉴스",
                "base_score": 50,
                "examples": "시장 공시, 기술 동향, 정책 논의",
                "weight": 0.35,
                "current_volume": 7  # 기사 수 (추정)
            },
            "negative": {
                "display_name": "부정적 뉴스",
                "base_score": 25,
                "examples": "지정학적 리스크, 약세 보도, 지표 악화",
                "weight": 0.30,
                "current_volume": 6  # 기사 수 (추정)
            }
        }
        
        # 공시 유형별 영향도 (0~100)
        self.disclosure_types = {
            "critical": {
                "display_name": "중요 공시",
                "impact_points": 40,  # 최대 40점 변동 가능
                "examples": "M&A, 대규모 계약, 경영진 교체",
                "weight": 0.40
            },
            "important": {
                "display_name": "일반 공시",
                "impact_points": 20,
                "examples": "분기 실적, 정책 발표, 신규 사업",
                "weight": 0.40
            },
            "minor": {
                "display_name": "경미 공시",
                "impact_points": 5,
                "examples": "임원 보임, 행사 안내, 그룹 뉴스",
                "weight": 0.20
            }
        }
    
    def validate(self, data: Dict[str, Any]) -> bool:
        """입력 데이터 검증"""
        # 뉴스 감정 관련 데이터 (최소 1개 필요)
        required_fields = ["news_sentiment_score"]
        return any(field in data for field in required_fields)
    
    def analyze(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        뉴스 감정 및 공시 영향도 분석
        
        Returns Dict with sentiment analysis and disclosure impact
        """
        try:
            # 1. 직접 입력된 뉴스 감정 점수 사용
            if "news_sentiment_score" in data:
                sentiment_score = data.get("news_sentiment_score", 50)
                sentiment_score = max(0, min(100, sentiment_score))  # 0~100
            else:
                # 뉴스 감정 계산 (기사 수 기반)
                positive_count = data.get("positive_news_count", 5)
                neutral_count = data.get("neutral_news_count", 7)
                negative_count = data.get("negative_news_count", 6)
                
                sentiment_score = self._calculate_sentiment(
                    positive_count, neutral_count, negative_count
                )
            
            # 2. 공시 영향도 분석
            disclosure_score = self._analyze_disclosure(data)
            
            # 3. 뉴스 빈도 분석
            total_news = data.get("total_news_count", 18)
            news_frequency = self._analyze_frequency(total_news)
            
            # 4. 뉴스 임팩트 (감정 + 공시 + 빈도)
            news_impact = (
                sentiment_score * 0.50 +  # 감정이 가장 중요
                disclosure_score * 0.35 +  # 공시 영향도
                news_frequency * 0.15      # 빈도
            )
            
            # 5. 감정 분류
            sentiment_label = self._classify_sentiment(sentiment_score)
            
            logger.info(
                f"News Analysis: Sentiment={sentiment_score:.1f}, "
                f"Disclosure={disclosure_score:.1f}, "
                f"Frequency={news_frequency:.1f}, "
                f"Impact={news_impact:.1f}, "
                f"Label={sentiment_label}"
            )
            
            return {
                "sentiment_score": sentiment_score,
                "disclosure_score": disclosure_score,
                "frequency_score": news_frequency,
                "impact_score": news_impact,
                "sentiment_label": sentiment_label,
                "news_count": {
                    "positive": data.get("positive_news_count", 5),
                    "neutral": data.get("neutral_news_count", 7),
                    "negative": data.get("negative_news_count", 6),
                    "total": total_news
                },
                "disclosure_details": self._get_disclosure_details(data)
            }
            
        except Exception as e:
            logger.error(f"News analysis error: {e}")
            return {
                "sentiment_score": 50,
                "error": str(e),
                "impact_score": 50
            }
    
    def get_score(self, analysis_result: Dict[str, Any]) -> float:
        """
        분석 결과로부터 최종 뉴스 점수 계산
        
        Args:
            analysis_result: analyze() 반환값 (Dict)
        
        Returns:
            0~100 정규화된 점수
        """
        try:
            # impact_score를 그대로 반환 (이미 0~100 범위)
            score = analysis_result.get("impact_score", 50)
            score = max(0, min(100, score))  # 0~100 범위 보장
            
            sentiment_label = analysis_result.get("sentiment_label", "중립")
            
            logger.info(
                f"News final score: Sentiment={sentiment_label}, "
                f"Score={score:.1f}"
            )
            
            return score
            
        except Exception as e:
            logger.error(f"Score calculation error: {e}")
            return 50.0  # 뉴스 점수는 중립이 기본값
    
    def _calculate_sentiment(self, positive: int, neutral: int, negative: int) -> float:
        """
        뉴스 기사 수를 기반으로 감정 점수 계산
        
        Args:
            positive: 긍정적 기사 수
            neutral: 중립적 기사 수
            negative: 부정적 기사 수
        
        Returns:
            0~100 감정 점수
        """
        total = positive + neutral + negative
        
        if total == 0:
            return 50.0  # 기사가 없으면 중립
        
        # 가중 평균
        # 긍정: 75점, 중립: 50점, 부정: 25점
        sentiment = (
            (positive * 75 + neutral * 50 + negative * 25) / total
        )
        
        return sentiment
    
    def _analyze_disclosure(self, data: Dict[str, Any]) -> float:
        """
        공시 영향도 분석
        
        Args:
            data: 공시 데이터 포함
        
        Returns:
            0~100 공시 영향도 점수
        """
        critical_count = data.get("critical_disclosure_count", 0)
        important_count = data.get("important_disclosure_count", 1)
        minor_count = data.get("minor_disclosure_count", 2)
        
        # 공시 임팩트 계산
        impact = (
            critical_count * 40 +
            important_count * 20 +
            minor_count * 5
        )
        
        # 0~100 범위로 정규화 (최대 100점)
        disclosure_score = min(100, 50 + impact / 4)  # 기본 50점 + 임팩트
        
        return disclosure_score
    
    def _analyze_frequency(self, news_count: int) -> float:
        """
        뉴스 빈도 분석
        
        Args:
            news_count: 총 뉴스 기사 수
        
        Returns:
            0~100 빈도 점수
        """
        # 일반적인 일일 뉴스: 10~20개
        # 0개: 0점, 10개: 50점, 20개: 75점, 30개 이상: 100점
        
        if news_count <= 5:
            return 30.0  # 뉴스 부족
        elif news_count <= 10:
            return 50.0  # 정상
        elif news_count <= 20:
            return 75.0  # 높은 관심
        else:
            return 100.0  # 매우 높은 관심
    
    def _classify_sentiment(self, score: float) -> str:
        """점수를 감정으로 분류"""
        if score >= 70:
            return "매우 긍정적"
        elif score >= 60:
            return "긍정적"
        elif score >= 45:
            return "약간 긍정적"
        elif score >= 55:
            return "중립"
        elif score >= 40:
            return "약간 부정적"
        elif score >= 30:
            return "부정적"
        else:
            return "매우 부정적"
    
    def _get_disclosure_details(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """공시 상세 정보 반환"""
        return {
            "critical_count": data.get("critical_disclosure_count", 0),
            "important_count": data.get("important_disclosure_count", 1),
            "minor_count": data.get("minor_disclosure_count", 2),
            "total_disclosure": data.get("critical_disclosure_count", 0) + 
                               data.get("important_disclosure_count", 1) + 
                               data.get("minor_disclosure_count", 2)
        }
    
    def _get_news_sentiment_trend(self, data: Dict[str, Any]) -> str:
        """뉴스 감정 추세 분석"""
        sentiment_today = data.get("news_sentiment_score", 50)
        sentiment_yesterday = data.get("news_sentiment_yesterday", 50)
        
        diff = sentiment_today - sentiment_yesterday
        
        if diff >= 15:
            return "크게 개선됨"
        elif diff >= 5:
            return "개선됨"
        elif diff > -5:
            return "안정적"
        elif diff >= -15:
            return "악화됨"
        else:
            return "크게 악화됨"