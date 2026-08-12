import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from market_intelligence.analyzers.technical_analyzer import TechnicalAnalyzer
import json

print("=" * 80)
print("TechnicalAnalyzer 통합 테스트")
print("=" * 80)

analyzer = TechnicalAnalyzer()
print("\n【Step 1】데이터 수집...")
data = analyzer.kis_client.get_daily_price("0001", days=60)

if not data or len(data.get("closes", [])) == 0:
    print("❌ 데이터 수집 실패")
    sys.exit(1)

print(f"✅ {len(data['closes'])}일치 데이터 수집 완료")

print("\n【Step 2】분석 실행 (run() 파이프라인)...")
result = analyzer.run(data)

print("\n【분석 결과】")
print(json.dumps(result, indent=2, ensure_ascii=False))

score = result.get("score", 0)
if score >= 70:
    signal = "🟢 강한 매수 신호"
elif score >= 60:
    signal = "🟢 매수 신호"
elif score >= 55:
    signal = "🟡 약한 매수 신호"
elif score >= 45:
    signal = "⚪ 중립"
elif score >= 40:
    signal = "🟡 약한 매도 신호"
elif score >= 30:
    signal = "🔴 매도 신호"
else:
    signal = "🔴 강한 매도 신호"

print(f"\n【신호】")
print(f"  점수: {score:.1f}/100")
print(f"  신호: {signal}")

print("\n" + "=" * 80)
print("✅ 테스트 완료!")
print("=" * 80)