# 【2026-08-24, Phase 5-20】NewsAnalyzer 완전 제거 - 아래 changelog 참고
from market_intelligence.analyzers.market_analyzer import MarketAnalyzer
from market_intelligence.analyzers.sector_analyzer import SectorAnalyzer
from market_intelligence.analyzers.moneyflow_analyzer import MoneyFlowAnalyzer
from market_intelligence.analyzers.theme_analyzer import ThemeAnalyzer
from market_intelligence.analyzers.technical_analyzer import TechnicalAnalyzer
from market_intelligence.analyzers.valuation_analyzer import ValuationAnalyzer
from market_intelligence.analyzers.stock_analyzer import StockAnalyzer

__all__ = [
    "MarketAnalyzer",
    "SectorAnalyzer",
    "MoneyFlowAnalyzer",
    "ThemeAnalyzer",
    "TechnicalAnalyzer",
    "ValuationAnalyzer",
    "StockAnalyzer",
]

# 【변경 이력】
# 【2026-08-24, Phase 5-20】NewsAnalyzer 제거
# - 배경: 계층형 최종 공식(market/sector/theme/stock)에는 애초에 뉴스 컴포넌트가
#   없었고(방법론 문서 기준 stock 100점 = 기술적35+수급25+밸류에이션20+
#   Sector상대강도20, StockAnalyzer 어디에도 news 참조 없음), NewsAnalyzer는
#   main.py의 flat 참고표(Step 7, 계층형과 무관)에만 쓰이고 있었다. 게다가
#   입력 자체가 전 종목·전 사이클 동일한 하드코딩 모의값(news_sentiment_score=
#   48.6 등, 실제 뉴스 API 미연동)이라, 살려둬도 종목 간 차이를 전혀 만들지
#   못하고 그냥 상수만 더하는 상태였다. 사용자가 "완전 제거"로 결정
#   (AskUserQuestion 3지선다: 제외 유지 / 자리 마련 / 완전 제거).
# - 이 파일에서 import/__all__ 제거, market_intelligence/analyzers/news_analyzer.py
#   파일 자체 삭제, main.py의 import/register_analyzer 호출/모의 데이터 블록 삭제,
#   tests/test_analyzers.py의 NewsAnalyzer 관련 테스트 삭제.
# - db/models.py의 NewsFeed 테이블(실제 뉴스 기사 원문 저장용, sentiment_score
#   컬럼 포함)은 이 analyzer와 무관한 별도 인프라라 그대로 둔다 - 나중에 진짜
#   뉴스 API를 붙일 때 그 테이블에서 읽어와 새 analyzer를 설계하면 된다.