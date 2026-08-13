from data.kis_client import KISClient

kis = KISClient()

print('=' * 80)
print('【0001 데이터 확인】')
print('=' * 80)

# 0001 데이터 조회
data = kis.get_daily_price('0001', days=5)

print(f'\n심볼: 0001')
print(f'데이터 포인트: {len(data.get("closes", []))}')
print(f'최근 5개 종가:')
closes = data.get('closes', [])
for i, close in enumerate(closes[-5:]):
    print(f'  [{i}] {close:,.2f}')

print(f'\n현재가 (closes[-1]): {closes[-1]:,.2f}')
print(f'고가: {max(data.get("highs", [])):,.2f}')
print(f'저가: {min(data.get("lows", [])):,.2f}')

print('\n' + '=' * 80)
print('【비교】')
print('=' * 80)

# KOSPI와 비교
kospi = kis.get_kospi_kosdaq()
print(f'KOSPI 지수: {kospi.get("kospi_index"):,.2f}')
print(f'KOSDAQ 지수: {kospi.get("kosdaq_index"):,.2f}')

print('\n주의: 0001이 KOSPI 지수인지 특정 종목인지 확인 필요')