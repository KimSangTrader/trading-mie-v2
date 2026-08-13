from data.kis_client import KISClient

kis = KISClient()

print("=" * 80)
print("【실제 vs Mock 데이터 비교】")
print("=" * 80)

# 1단계: 실시간 KOSPI/KOSDAQ 조회
print("\n【1단계】실시간 지수 (get_kospi_kosdaq)")
kospi_kosdaq = kis.get_kospi_kosdaq()
print(f"  KOSPI: {kospi_kosdaq.get('kospi_index'):,.2f}")
print(f"  KOSDAQ: {kospi_kosdaq.get('kosdaq_index'):,.2f}")
print(f"  KOSPI 변화율: {kospi_kosdaq.get('kospi_change_rate', 0):+.2f}%")

# 2단계: 일별 데이터 조회 (60일)
print("\n【2단계】일별 데이터 (get_daily_price, 60일)")
daily_data = kis.get_daily_price("0001", days=5)
closes = daily_data.get('closes', [])
print(f"  최신 5일 종가:")
for i, close in enumerate(closes[-5:]):
    print(f"    [{i}] {close:,.2f}")

# 3단계: 변화율 계산
print("\n【3단계】변화율 계산")
if len(closes) >= 2:
    today_close = closes[-1]
    yesterday_close = closes[-2]
    change_rate = ((today_close - yesterday_close) / yesterday_close) * 100
    print(f"  어제 종가: {yesterday_close:,.2f}")
    print(f"  오늘 종가: {today_close:,.2f}")
    print(f"  변화율: {change_rate:+.2f}%")
else:
    print(f"  데이터 부족")

print("\n" + "=" * 80)
print("【결론】")
print("=" * 80)
if change_rate != 0:
    print(f"✅ 실제 데이터 연동됨! (변화율: {change_rate:+.2f}%)")
else:
    print(f"❌ Mock 데이터 사용 중 (변화율: 0.00%)")
print("=" * 80)