import logging
from market_intelligence.analyzers.market_analyzer import MarketAnalyzer

# 로깅 설정
logging.basicConfig(
    level=logging.DEBUG,
    format='%(name)s - %(levelname)s - %(message)s'
)

analyzer = MarketAnalyzer()

data = {
    'kospi_index': 6579.04,
    'kospi_change_rate': 3.68,
    'kosdaq_index': 858.91,
    'kosdaq_change_rate': 0.12
}

print("【검증 시도】")
try:
    result = analyzer.validate(data)
    print(f"검증 결과: {result}")
except Exception as e:
    print(f"Exception: {e}")
    import traceback
    traceback.print_exc()