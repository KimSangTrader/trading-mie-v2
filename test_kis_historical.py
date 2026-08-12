"""KIS API 일별 시세 데이터 테스트"""

from data.kis_client import KISClient

def test_historical_data():
    print("="*80)
    print("KIS API 일별 시세 데이터 테스트")
    print("="*80)
    
    client = KISClient()
    
    # 토큰 발급
    print("\n【Step 1】토큰 발급...")
    if not client.get_access_token():
        print("❌ 토큰 발급 실패")
        return
    
    # 【디버깅】KOSPI 일별 데이터 직접 조회
    print("\n【Step 2】KOSPI 일별 데이터 조회...")
    
    # kis_client 수정: 디버깅 정보 출력하도록
    kospi_data = client.get_daily_price("0001", days=60)
    
    print("\n【디버깅 정보】")
    print(f"  kospi_data 타입: {type(kospi_data)}")
    print(f"  kospi_data 키: {kospi_data.keys() if kospi_data else 'Empty'}")
    print(f"  dates 길이: {len(kospi_data.get('dates', []))}")
    print(f"  closes 길이: {len(kospi_data.get('closes', []))}")
    
    if kospi_data and len(kospi_data.get('dates', [])) > 0:
        print(f"\n✅ KOSPI 데이터:")
        print(f"   수집 기간: {kospi_data['dates'][-1]} ~ {kospi_data['dates'][0]}")
        print(f"   수집 건수: {len(kospi_data['dates'])}")
        print(f"   최근 종가: {kospi_data['closes'][0]}")
        print(f"   평균 거래량: {sum(kospi_data['volumes']) / len(kospi_data['volumes']):,.0f}")
    else:
        print(f"\n❌ 데이터 없음!")
        print(f"   kospi_data: {kospi_data}")
    
    print("\n" + "="*80)
    print("테스트 완료")
    print("="*80)

if __name__ == "__main__":
    test_historical_data()