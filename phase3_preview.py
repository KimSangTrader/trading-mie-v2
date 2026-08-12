from market_intelligence.analyzers.technical_analyzer import TechnicalAnalyzer
from market_intelligence.analyzers.market_analyzer import MarketAnalyzer
import json

# Mock 데이터
technical_data = {
    'symbol': '0001',
    'dates': ['20260812'] * 60,
    'opens': [7500] * 60,
    'highs': [7600] * 60,
    'lows': [7400] * 60,
    'closes': [7516.04] + [7510] * 59,
    'volumes': [458190] * 60
}

market_data = {
    'kospi_index': 6579.04,
    'kospi_change_rate': 3.68,
    'kosdaq_index': 858.91,
    'kosdaq_change_rate': 0.12
}

# Step 1: 기술지표 분석
tech_analyzer = TechnicalAnalyzer()
tech_result = tech_analyzer.run(technical_data)
tech_score = tech_result.get('score', 0)

# Step 2: 시장 분석
market_analyzer = MarketAnalyzer()
market_result = market_analyzer.run(market_data)
market_multiplier = market_result.get('details', {}).get('signal_multiplier', 1.0)

# Step 3: 통합 신호
combined_score = tech_score * market_multiplier

print('=' * 80)
print('Phase 3: 통합 파이프라인 프리뷰')
print('=' * 80)
print(f'\n【기술지표】')
print(f'  점수: {tech_score:.1f}/100')
signal_tech = '매수' if tech_score > 60 else '중립' if tech_score > 40 else '매도'
print(f'  신호: {signal_tech}')

print(f'\n【시장 필터】')
print(f'  강도: {market_result.get("score", 0):.1f}/100')
print(f'  체제: {market_result.get("details", {}).get("market_regime", "N/A")}')
print(f'  배수: {market_multiplier:.2f}x')

print(f'\n【통합 신호】')
print(f'  {tech_score:.1f} × {market_multiplier:.2f} = {combined_score:.1f}/100')
if combined_score > 70:
    signal = '강한 매수'
elif combined_score > 60:
    signal = '매수'
elif combined_score > 40:
    signal = '중립'
else:
    signal = '약한 매도'
print(f'  최종 신호: {signal}')

print('\n' + '=' * 80)
