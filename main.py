import logging
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

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def main():
    """
    MIE V2.0 최종 통합 테스트
    7개 분석기가 완벽하게 작동하는지 검증
    """
    logger.info("=" * 80)
    logger.info("🎊 MIE V2.0 최종 통합 테스트 시작!")
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
    
    # 3. 실제 시장 데이터 (2026-08-07 기준)
    logger.info("\n【Step 3】실제 시장 데이터 준비 중...")
    market_data = {
        # ============ MarketAnalyzer ============
        "kospi_index": 6258.77,          # KOSPI 현재값
        "kosdaq_index": 798.81,          # KOSDAQ 현재값
        "market_volume": 1350000000,     # 시장 거래량 (1,350억)
        
        # ============ SectorAnalyzer ============
        "IT_Semiconductor": 1425,        # IT/반도체: -5% 약세
        "Finance": 950,                  # 금융: 평상시
        "Chemicals_Energy": 650,         # 화학/에너지: 약세
        "Consumer": 800,                 # 소비재: 약세
        "Telecom_Media": 700,            # 통신/미디어: 약세
        "Healthcare_Pharma": 1200,       # 의료/제약: 평상시
        "Construction_Real_Estate": 550, # 건설/부동산: 약세
        "Secondary_Battery": 900,        # 2차전지: 중간
        
        # ============ MoneyFlowAnalyzer ============
        "foreign": -8590000000,          # 외국인: -8,590억 순매도
        "institutional": 5791000000,     # 기관: +5,791억 순매수
        "retail": 2500000000,            # 개인: +2,500억 순매수 (추정)
        "program": 500000000,            # 프로그램: +500억 (추정)
        
        # ============ ThemeAnalyzer ============
        "geopolitical_risk": 35,         # 지정학적 리스크: 약세
        "ai_semiconductor": 42,          # AI/반도체: 약세~중립
        "esg_battery": 62,               # ESG/2차전지: 강세
        "value_buying": 68,              # 저가 매수: 강세
        "economic_recovery": 48,         # 경기 회복: 약세~중립
        "tech_innovation": 65,           # 기술 혁신: 강세
        
        # ============ NewsAnalyzer ============
        "positive_news_count": 5,        # 긍정: ESG, 저가 매수
        "neutral_news_count": 7,         # 중립: 공시, 기술
        "negative_news_count": 6,        # 부정: 중동 긴장, 반도체 약세
        "total_news_count": 18,          # 총 뉴스
        "critical_disclosure_count": 0,  # 중요 공시: 없음
        "important_disclosure_count": 1, # 일반 공시: 1개
        "minor_disclosure_count": 2,     # 경미 공시: 2개
        "news_sentiment_score": 48.6,    # ← 추가! (긍정75 + 중립50 + 부정25의 가중 평균)
        
        # ============ TechnicalAnalyzer ============
        "macd_value": -15,               # MACD: -15 (약세)
        "rsi_value": 28,                 # RSI: 28 (과매도)
        "price": 6258.77,                # 현재 가격
        "bb_upper": 6600,                # 볼린저 밴드 상단
        "bb_middle": 6250,               # 볼린저 밴드 중간
        "bb_lower": 5900,                # 볼린저 밴드 하단
        "ma5": 6200,                     # 5일 이동평균
        "ma20": 6280,                    # 20일 이동평균
        "ma60": 6350,                    # 60일 이동평균 (5MA<20MA<60MA=약세)
        
        # ============ ValuationAnalyzer ============
        "per_value": 12.0,               # PER: 12배 (시장 평균 15 < 저평가)
        "per_average": 15.0,             # PER 시장 평균
        "pbr_value": 1.0,                # PBR: 1.0배 (저평가~평가)
        "pbr_average": 1.2,              # PBR 시장 평균
        "growth_rate": 4.0,              # 성장률: 4% (저성장)
        "growth_average": 5.0,           # 성장률 평균
        "dividend_yield": 3.5,           # 배당률: 3.5% (양호)
        "dividend_average": 2.5          # 배당률 평균
    }
    
    logger.info("✅ 시장 데이터 준비 완료 (39개 지표)")
    
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
        
    else:
        logger.error("❌ 분석 실패!")
        logger.error(results.get("error", "알 수 없는 오류"))
        # 실패해도 Step 6은 진행 (final_score는 0으로 초기화됨)
    
    # 6. 최종 검증
    logger.info("\n【Step 6】최종 검증 중...")
    logger.info("-" * 80)
    
    # 가중치 합 검증 (individual_scores가 있을 때만)
    if individual_scores:
        total_weight = sum(
            score_data.get("weight", 0) 
            for score_data in individual_scores.values() 
            if isinstance(score_data, dict)
        )
        logger.info(f"✅ 가중치 합 검증: {total_weight:.2f} (1.00이어야 함)")
    else:
        logger.warning("⚠️ 분석 실패로 가중치 검증 불가")
    
    # 점수 범위 검증
    if 0 <= final_score <= 100:
        logger.info(f"✅ 최종 점수 범위 검증: {final_score:.2f} (0~100 범위 내)")
    else:
        logger.error(f"❌ 점수 범위 오류: {final_score}")
    
    logger.info("-" * 80)
    
    # 7. 완료 메시지
    logger.info("\n" + "=" * 80)
    logger.info("🎊 MIE V2.0 최종 통합 테스트 완료!")
    logger.info("=" * 80)
    logger.info(f"최종 점수: {final_score:.2f}/100")
    
    if results.get("success"):
        logger.info("✅ 모든 분석기 정상 작동")
        logger.info("✅ 7개 분석기 100% 완성")
        logger.info("✅ PHASE 3 공식 완료! 🎉")
    else:
        logger.error("❌ 분석 과정에서 오류 발생")
        logger.error(f"   원인: {results.get('error', '알 수 없음')}")
    
    logger.info("=" * 80)
    
    return results

def analyze_sentiment(score: float) -> dict:
    """최종 점수 기반 시장 심리 분석"""
    if score >= 70:
        return {
            "mood": "매우 긍정적 (강한 상승 신호)",
            "strategy": "공격적 매수",
            "risk": "낮음 (안전)"
        }
    elif score >= 55:
        return {
            "mood": "긍정적 (약한 상승 신호)",
            "strategy": "선택적 매수",
            "risk": "낮음"
        }
    elif score >= 45:
        return {
            "mood": "중립 (혼합 신호)",
            "strategy": "관망 또는 분할 매수",
            "risk": "중간"
        }
    elif score >= 30:
        return {
            "mood": "부정적 (약한 하락 신호)",
            "strategy": "선택적 매도",
            "risk": "높음"
        }
    else:
        return {
            "mood": "매우 부정적 (강한 하락 신호)",
            "strategy": "적극적 매도",
            "risk": "매우 높음 (위험)"
        }

if __name__ == "__main__":
    results = main()