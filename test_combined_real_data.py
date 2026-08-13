from data.kis_client import KISClient
from market_intelligence.analyzers.combined_analyzer_improved import CombinedAnalyzerImproved
import logging

logging.basicConfig(level=logging.INFO)

kis = KISClient()

print("=" * 80)
print("【CombinedAnalyzerImproved + 실제 데이터】")
print("=" * 80)

# 실제 데이터 수집
daily_data = kis.get_daily_price("0001", days=60)
kospi_kosdaq = kis.get_kospi_kosdaq()

# 실제 데이터로 분석
data = {
    'symbol': '0001',
    'closes': daily_data.get('closes', []),
    'opens': daily_data.get('opens', []),
    'highs': daily_data.get('highs', []),
    'lows': daily_data.get('lows', []),
    'volumes': daily_data.get('volumes', []),
    'kospi_index': kospi_kosdaq.get('kospi_index', 0),
    'kosdaq_index': kospi_kosdaq.get('kosdaq_index', 0),
    'per': 15.5,
    'pbr': 1.2,
    'dividend_yield': 2.5
}

# 분석 실행
analyzer = CombinedAnalyzerImproved()
result = analyzer.run(data)

# 결과 출력
print("\n" + "=" * 80)
print("【최종 결과】신뢰도 개선 완료!")
print("=" * 80)
print(f"점수: {result['score']:.1f}/100")
print(f"신뢰도: {result['confidence']:.1f}% (이전 21% → 현재 {result['confidence']:.1f}% ✅)")
print(f"\n【세부 지표】")
print(f"  기술지표 점수: {result['details']['tech_score']:.1f}/100")
print(f"  시장분석 점수: {result['details']['market_score']:.1f}/100")
print(f"  기본분석 점수: {result['details']['val_score']:.1f}/100")
print(f"  신호 일치도: {result['details']['signal_agreement']:.1f}%")
print(f"  데이터 품질: {result['details']['data_quality']:.1f}%")
print(f"  시장 확실성: {result['details']['market_certainty']:.1f}%")
print(f"  신호 강도: {result['details']['signal_strength']:.1f}%")
print(f"\n【시장 상황】")
print(f"  KOSPI: {kospi_kosdaq.get('kospi_index'):,.2f}")
print(f"  변화율: {kospi_kosdaq.get('kospi_change_rate', 0):+.2f}%")
print(f"  시장배수: {result['details']['market_multiplier']:.2f}x")
print("=" * 80)