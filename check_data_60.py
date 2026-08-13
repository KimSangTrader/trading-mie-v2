from data.kis_client import KISClient

kis = KISClient()

print('=' * 80)
print('【0001 데이터 비교 (5일 vs 60일)】')
print('=' * 80)

# 5일 데이터
data_5 = kis.get_daily_price('0001', days=5)
closes_5 = data_5.get('closes', [])

print(f'\n【5일 데이터】')
print(f'  데이터 포인트: {len(closes_5)}')
if closes_5:
    print(f'  최신: {closes_5[-1]:,.2f}')
    print(f'  가장 오래된: {closes_5[0]:,.2f}')
    print(f'  최고: {max(closes_5):,.2f}')
    print(f'  최저: {min(closes_5):,.2f}')

# 60일 데이터
data_60 = kis.get_daily_price('0001', days=60)
closes_60 = data_60.get('closes', [])

print(f'\n【60일 데이터】')
print(f'  데이터 포인트: {len(closes_60)}')
if closes_60:
    print(f'  최신: {closes_60[-1]:,.2f}')
    print(f'  가장 오래된: {closes_60[0]:,.2f}')
    print(f'  최고: {max(closes_60):,.2f}')
    print(f'  최저: {min(closes_60):,.2f}')

print(f'\n【실시간 KOSPI】')
kospi = kis.get_kospi_kosdaq()
print(f'  현재 KOSPI: {kospi.get("kospi_index"):,.2f}')

print('\n' + '=' * 80)
if closes_60 and closes_60[-1] != closes_5[-1]:
    print('⚠️ 경고: 5일과 60일 데이터의 최신값이 다릅니다!')
    print(f'  5일 최신: {closes_5[-1]:,.2f}')
    print(f'  60일 최신: {closes_60[-1]:,.2f}')
    print(f'  차이: {abs(closes_60[-1] - closes_5[-1]):,.2f}')