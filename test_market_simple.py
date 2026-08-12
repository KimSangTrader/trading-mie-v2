from market_intelligence.analyzers.market_analyzer import MarketAnalyzer

analyzer = MarketAnalyzer()

data = {
    'kospi_index': 6579.04,
    'kospi_change_rate': 3.68,
    'kosdaq_index': 858.91,
    'kosdaq_change_rate': 0.12
}

result = analyzer.run(data)
details = result.get('details', {})

print('시장 강도:', details.get('market_strength', 0))
print('시장 체제:', details.get('market_regime', 'UNKNOWN'))
print('신호 가중치:', details.get('signal_multiplier', 1.0))
print('신호 강도:', details.get('signal_strength', '불명'))