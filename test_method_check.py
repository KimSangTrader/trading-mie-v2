from data.kis_client import KISClient

print("메서드 확인 중...")

try:
    client = KISClient()
    
    if hasattr(client, 'get_daily_price'):
        print("✅ get_daily_price 메서드 존재!")
    else:
        print("❌ get_daily_price 메서드 없음!")
        print("\n현재 메서드 목록:")
        methods = [m for m in dir(client) if not m.startswith('_') and callable(getattr(client, m))]
        for m in sorted(methods):
            print(f"  - {m}")
            
except Exception as e:
    print(f"❌ 오류: {e}")
    import traceback
    traceback.print_exc()