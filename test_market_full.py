import logging
from market_intelligence.analyzers.market_analyzer import MarketAnalyzer
import json

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

analyzer = MarketAnalyzer()

data = {
    'kospi_index': 6579.04,
    'kospi_change_rate': 3.68,
    'kosdaq_index': 858.91,
    'kosdaq_change_rate': 0.12
}

print("=" * 80)
print("MarketAnalyzer 전체 파이프라인 테스트")
print("=" * 80)

print("\n【Step 1】데이터 검증")
if not analyzer.validate(data):
    print("❌ 검증 실패")
    exit(1)

print("\n【Step 2】run() 파이프라인 실행")
result = analyzer.run(data)

print("\n【Step 3】결과 분석")
print(json.dumps(result, indent=2, ensure_ascii=False))

details = result.get("details", {})
print(f"\n【시장 분석 종합】")
print(f"  점수: {result.get('score', 0):.1f}/100")
print(f"  가중치: {result.get('weight', 0):.2f}")
print(f"  시장 강도: {details.get('market_strength', 0):.1f}/100")
print(f"  시장 체제: {details.get('market_regime', 'UNKNOWN')}")
print(f"  신호 가중치: {details.get('signal_multiplier', 1.0):.2f}x")
print(f"  신호 강도: {details.get('signal_strength', '불명')}")

print("\n" + "=" * 80)
print("✅ 테스트 완료!")
print("=" * 80)