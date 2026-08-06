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
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main():
    """메인 함수 - MIE V2.0 통합 테스트"""
    logger.info("Starting MIE V2.0 Integration Test...")
    
    # 1. IntelligenceManager 초기화
    manager = IntelligenceManager()
    
    # 2. 분석기 등록
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
    
    logger.info(f"✅ Registered {len(manager.list_analyzers())} analyzers")
    logger.info(f"   Analyzers: {', '.join(manager.list_analyzers())}")
    
    # 3. 테스트 데이터 (각 분석기의 요구사항을 만족)
    test_data = {
        # MarketAnalyzer
        "kospi_index": 2500,
        "kosdaq_index": 850,
        "market_volume": 1000000000,
        
        # SectorAnalyzer
        "sector_list": ["IT", "Finance", "Manufacturing"],
        "sector_performance": [0.8, 0.6, 0.7],
        
        # MoneyFlowAnalyzer
        "foreign_buy": 50000000,
        "institutional_buy": 30000000,
        "program_buy": 20000000,
        "pension_buy": 15000000,
        
        # ThemeAnalyzer
        "theme_list": ["AI", "EV", "Semiconductor"],
        "theme_strength": 0.75,
        
        # NewsAnalyzer
        "news_sentiment": 0.65,
        "disclosure_count": 5,
        
        # TechnicalAnalyzer
        "price": 50000,
        "volume": 1000000,
        "macd": {"value": 100, "signal": 80},
        "rsi": 65,
        "bollinger": {"upper": 52000, "lower": 48000},
        
        # ValuationAnalyzer
        "pe_ratio": 15.5,
        "pb_ratio": 1.2,
        "earnings_growth": 0.12
    }
    
    # 4. 분석 실행
    logger.info("\n🔍 Running analysis...")
    results = manager.run_all(test_data)
    
    # 5. 결과 출력
    logger.info("\n" + "="*50)
    logger.info("📊 ANALYSIS RESULTS")
    logger.info("="*50)
    
    logger.info(f"Final Score: {results['final_score']}")
    logger.info(f"Success Count: {results['success_count']}/{results['total_analyzers']}")
    logger.info(f"Fail Count: {results['fail_count']}")
    logger.info(f"Timestamp: {results['timestamp']}")
    
    logger.info("\n📈 By Analyzer:")
    for analyzer_result in results['by_analyzer']:
        status = "✅" if analyzer_result['success'] else "❌"
        logger.info(f"  {status} {analyzer_result['analyzer'].upper()}: {analyzer_result['score']:.2f} (weight: {analyzer_result['weight']})")
    
    # 6. 요약
    summary = manager.get_summary()
    logger.info("\n📋 Summary:")
    logger.info(f"  Final Score: {summary['final_score']}")
    logger.info(f"  Analyzers Run: {summary['analyzers_run']}")
    logger.info(f"  Analyzed At: {summary['analyzed_at']}")
    
    logger.info("\n" + "="*50)
    logger.info("✅ MIE V2.0 Integration Test Complete!")
    logger.info("="*50)
    
    return results


if __name__ == "__main__":
    main()