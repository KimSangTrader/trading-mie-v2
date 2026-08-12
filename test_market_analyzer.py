import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from market_intelligence.analyzers.market_analyzer import MarketAnalyzer
from data.kis_client import KISClient  # ← 직접 import 추가
import json

print("=" * 80)
print("MarketAnalyzer 테스트 (Phase 2)")
print("=" * 80)

analyzer = MarketAnalyzer()

# kis_client 직접 초기화 (만약을 위해)
if not hasattr(analyzer, 'kis_client'):
    print("⚠️ kis_client 재초기화...")
    analyzer.kis_client = KISClient()

print("\n【Step 1】시장 데이터 수집...")
market_data = analyzer.kis_client.get_kospi_kosdaq()

if not market_data:
    print("❌ 데이터 수집 실패")
    sys.exit(1)

print(f"✅ 시장 데이터 수집 완료")
print(f"   KOSPI: {market_data.get('kospi_index', 0):.0f} ({market_data.get('kospi_change_rate', 0):+.2f}%)")
print(f"   KOSDAQ: {market_data.get('kosdaq_index', 0):.0f} ({market_data.get('kosdaq_change_rate', 0):+.2f}%)")

print("\n【Step 2】시장 분석 실행 (run() 파이프라인)...")
result = analyzer.run(market_data)

print("\n【분석 결과】")
print(json.dumps(result, indent=2, ensure_ascii=False))

details = result.get("details", {})
market_regime = details.get("market_regime", "UNKNOWN")
signal_multiplier = details.get("signal_multiplier", 1.0)
signal_strength = details.get("signal_strength", "불명")
market_strength = details.get("market_strength", 0)

print(f"\n【시장 분석 종합】")
print(f"  시장 강도: {market_strength:.1f}/100")
print(f"  시장 체제: {market_regime}")
print(f"  신호 가중치: {signal_multiplier:.2f}x")
print(f"  신호 강도: {signal_strength}")

print("\n" + "=" * 80)
print("✅ 테스트 완료!")
print("=" * 80)