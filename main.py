import logging
from datetime import datetime
from market_intelligence.intelligence_manager import IntelligenceManager
from market_intelligence.analyzers import (
    MarketAnalyzer,
    SectorAnalyzer,
    MoneyFlowAnalyzer,
    ThemeAnalyzer,
    NewsAnalyzer,
    TechnicalAnalyzer,
    ValuationAnalyzer
)
from data.kis_client import KISClient

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_real_market_data():
    """KIS API에서 실시간 시장 데이터 조회"""
    logger.info("\n【실시간 KIS API 데이터 조회 중...】")
    
    try:
        # KIS 클라이언트 초기화
        kis_client = KISClient()
        
        # 토큰 발급
        if not kis_client.get_access_token():
            logger.error("KIS API 토큰 발급 실패")
            return None
        
        # 실시간 KOSPI/KOSDAQ 조회
        real_data = kis_client.get_kospi_kosdaq()
        
        if not real_data:
            logger.error("KIS API 데이터 조회 실패")
            return None
        
        logger.info(f"✅ KOSPI (실제): {real_data.get('kospi_index', 0):.2f}")
        logger.info(f"✅ KOSDAQ (실제): {real_data.get('kosdaq_index', 0):.2f}")
        
        return real_data
        
    except Exception as e:
        logger.error(f"KIS API 조회 오류: {e}")
        return None


def merge_market_data(real_data):
    """
    KIS API 실제 데이터 + 모의 데이터 병합
    
    【실제 데이터】KOSPI, KOSDAQ, 거래량
    【모의/계산 데이터】기술 지표, 뉴스 감정, 수급 상세
    """
    
    if real_data is None:
        logger.warning("실제 데이터 없음 - 완전 모의 데이터로 진행")
        real_data = {}
    
    # 기본 마켓 데이터 (KIS 실제 데이터)
    market_data = {
        # ============ MarketAnalyzer (실제 데이터) ============
        "kospi_index": real_data.get('kospi_index', 6258.77),
        "kosdaq_index": real_data.get('kosdaq_index', 798.81),
        "market_volume": real_data.get('market_volume', 1350000000),
        
        # ============ SectorAnalyzer (모의 데이터) ============
        "IT_Semiconductor": 1425,
        "Finance": 950,
        "Chemicals_Energy": 650,
        "Consumer": 800,
        "Telecom_Media": 700,
        "Healthcare_Pharma": 1200,
        "Construction_Real_Estate": 550,
        "Secondary_Battery": 900,
        
        # ============ MoneyFlowAnalyzer (모의 데이터) ============
        "foreign": -8590000000,
        "institutional": 5791000000,
        "retail": 2500000000,
        "program": 500000000,
        
        # ============ ThemeAnalyzer (모의 데이터) ============
        "geopolitical_risk": 35,
        "ai_semiconductor": 42,
        "esg_battery": 62,
        "value_buying": 68,
        "economic_recovery": 48,
        "tech_innovation": 65,
        
        # ============ NewsAnalyzer (모의 데이터) ============
        "positive_news_count": 5,
        "neutral_news_count": 7,
        "negative_news_count": 6,
        "total_news_count": 18,
        "critical_disclosure_count": 0,
        "important_disclosure_count": 1,
        "minor_disclosure_count": 2,
        "news_sentiment_score": 48.6,
        
        # ============ TechnicalAnalyzer (모의 데이터) ============
        "macd_value": -15,
        "rsi_value": 28,
        "price": real_data.get('kospi_index', 6258.77),
        "bb_upper": 6600,
        "bb_middle": 6250,
        "bb_lower": 5900,
        "ma5": 6200,
        "ma20": 6280,
        "ma60": 6350,
        
        # ============ ValuationAnalyzer (모의 데이터) ============
        "per_value": 12.0,
        "per_average": 15.0,
        "pbr_value": 1.0,
        "pbr_average": 1.2,
        "growth_rate": 4.0,
        "growth_average": 5.0,
        "dividend_yield": 3.5,
        "dividend_average": 2.5
    }
    
    return market_data


def analyze_sentiment(score):
    """점수에 따른 시장 심리 분석"""
    if score >= 70:
        return {
            "mood": "🟢 강한 매수 신호",
            "strategy": "적극적 매수",
            "risk": "낮음"
        }
    elif score >= 60:
        return {
            "mood": "🟢 매수 신호",
            "strategy": "점진적 매수",
            "risk": "낮음~중간"
        }
    elif score >= 50:
        return {
            "mood": "🟡 중립",
            "strategy": "관망 또는 분할 매수",
            "risk": "중간"
        }
    elif score >= 40:
        return {
            "mood": "🔴 매도 신호",
            "strategy": "점진적 매도",
            "risk": "중간~높음"
        }
    else:
        return {
            "mood": "🔴 강한 매도 신호",
            "strategy": "적극적 매도",
            "risk": "높음"
        }


def main():
    """
    MIE V2.0 실시간 분석
    KIS API 실제 데이터 + 분석기 통합
    """
    logger.info("=" * 80)
    logger.info("🎊 MIE V2.0 - 실시간 KIS API 분석 시작!")
    logger.info("=" * 80)
    
    # 1. IntelligenceManager 초기화
    logger.info("\n【Step 1】IntelligenceManager 초기화 중...")
    manager = IntelligenceManager()
    logger.info("✅ IntelligenceManager 준비 완료")
    
    # 2. 7개 분석기 등록
    logger.info("\n【Step 2】7개 분석기 등록 중...")
    analyzers = [
        MarketAnalyzer(),
        SectorAnalyzer(),
        MoneyFlowAnalyzer(),
        ThemeAnalyzer(),
        NewsAnalyzer(),
        TechnicalAnalyzer(),
        ValuationAnalyzer()
    ]
   
    for analyzer in analyzers:
        manager.register_analyzer(analyzer)
        logger.info(f"✅ {analyzer.name} 등록 완료 (weight={analyzer.weight})")
    
    logger.info(f"✅ 총 {len(analyzers)}개 분석기 등록 완료")
    
    # 3. 실시간 KIS API 데이터 조회 + 병합
    logger.info("\n【Step 3】실시간 시장 데이터 준비 중...")
    
    # KIS API에서 실제 데이터 조회
    real_data = get_real_market_data()
    
    # 실제 데이터 + 모의 데이터 병합
    market_data = merge_market_data(real_data)
    
    if real_data:
        logger.info("✅ 실제 시장 데이터 + 분석 데이터 준비 완료")
    else:
        logger.warning("⚠️  모의 데이터로 진행 (실제 데이터 조회 실패)")
    
    # 4. 분석 실행
    logger.info("\n【Step 4】7개 분석기 동시 분석 실행 중...")
    logger.info("-" * 80)
    
    # 먼저 각 분석기를 개별적으로 테스트
    logger.info("\n【개별 분석기 검증】")
    for analyzer in analyzers:
        try:
            # validate 확인
            is_valid = analyzer.validate(market_data)
            logger.info(f"  {analyzer.name}: validate={is_valid}")
            
            if is_valid:
                # analyze 실행
                analysis_result = analyzer.analyze(market_data)
                logger.info(f"    → analyze() 성공")
            else:
                logger.warning(f"    → validate() 실패! 필수 데이터 누락")
                
        except Exception as e:
            logger.error(f"  {analyzer.name}: {str(e)}")
    
    logger.info("-" * 80)
    
    # IntelligenceManager 실행
    logger.info("\n【IntelligenceManager 실행】")
    try:
        results = manager.run_all(market_data)
        
        # 결과 상세 확인
        logger.info(f"Success: {results.get('success')}")
        logger.info(f"Error: {results.get('error')}")
        
        if results.get("success"):
            logger.info("✅ 분석 성공!")
            individual_scores = results.get("individual_scores", {})
            logger.info(f"Individual Scores: {individual_scores}")
        else:
            logger.error("❌ 분석 실패!")
            logger.error(f"Error Details: {results.get('error')}")
            
    except Exception as e:
        logger.error(f"❌ manager.run_all() 에러: {str(e)}")
        logger.error(f"   타입: {type(e).__name__}")
        import traceback
        logger.error(traceback.format_exc())
        results = {
            "success": False,
            "error": str(e)
        }
    
    logger.info("-" * 80)
    
    # 5. 결과 분석 및 출력
    logger.info("\n【Step 5】분석 결과 상세 분석 중...")
    logger.info("=" * 80)
    
    # individual_scores를 외부에서 초기화 (에러 방지)
    individual_scores = {}
    final_score = 0
    
    if results.get("success"):
        # 개별 분석기 점수
        logger.info("\n【개별 분석기 점수】")
        individual_scores = results.get("individual_scores", {})
        
        for analyzer_name, score_data in individual_scores.items():
            if isinstance(score_data, dict):
                score = score_data.get("score", 0)
                weight = score_data.get("weight", 0)
                logger.info(
                    f"  {analyzer_name:20} : {score:6.2f}점 "
                    f"(가중치={weight:.0%})"
                )
        
        # 최종 종합 점수
        final_score = results.get("final_score", 0)
        logger.info("=" * 80)
        logger.info(f"【최종 종합 점수】: {final_score:.2f}점 (0~100)")
        logger.info("=" * 80)
        
        # 시장 심리 분석
        logger.info("\n【시장 심리 분석】")
        sentiment_analysis = analyze_sentiment(final_score)
        logger.info(f"  현재 시장 심리: {sentiment_analysis['mood']}")
        logger.info(f"  추천 전략: {sentiment_analysis['strategy']}")
        logger.info(f"  위험도: {sentiment_analysis['risk']}")
        
        # 섹터 분석
        logger.info("\n【주요 섹터 분석】")
        logger.info("  강세 섹터: ESG/2차전지, 저가 매수")
        logger.info("  약세 섹터: IT/반도체, 화학/에너지")
        logger.info("  중립 섹터: 금융, 의료/제약")
        
        # 수급 분석
        logger.info("\n【수급 심리 분석】")
        logger.info("  외국인: 8,590억 순매도 (약세 신호)")
        logger.info("  기관: 5,791억 순매수 (저가 매수)")
        logger.info("  개인: 순매수 우위 (낙관적)")
        logger.info("  신호: 하한선 지지 신호 (회복 가능성)")
        
        # 뉴스 감정
        logger.info("\n【뉴스 감정 분석】")
        logger.info("  긍정 뉴스: 5개 (27.8%)")
        logger.info("  중립 뉴스: 7개 (38.9%)")
        logger.info("  부정 뉴스: 6개 (33.3%)")
        logger.info("  감정: 약간 부정적 (약세 심리)")
        
        # 기술 신호
        logger.info("\n【기술 분석 신호】")
        logger.info("  MACD: -15 (약세 모멘텀)")
        logger.info("  RSI: 28 (과매도 - 회복 기회)")
        logger.info("  볼린저 밴드: 하단 근처 (극단적 약세)")
        logger.info("  이동평균: 약세 정렬 (5MA < 20MA < 60MA)")
        logger.info("  신호: 강한 매도 (회복 기회)")
        
        # 가치 평가
        logger.info("\n【가치 평가 분석】")
        logger.info("  PER: 12배 (시장 평균 15 < 저평가)")
        logger.info("  PBR: 1.0배 (저평가~평가)")
        logger.info("  성장률: 4% (저성장)")
        logger.info("  배당률: 3.5% (양호한 수익성)")
        logger.info("  평가: 저평가 (매수 신호)")
        
        logger.info("\n" + "=" * 80)
        logger.info("✅ 분석 완료")
        logger.info("=" * 80)
        
        return True
    else:
        logger.error("❌ 분석 결과 없음")
        return False


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)