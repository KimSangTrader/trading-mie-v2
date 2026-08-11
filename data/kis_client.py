"""
KIS API 클라이언트 (환경별 자동 선택)
한국투자증권 실시간 시장 데이터 조회
"""

import requests
import json
import os
from datetime import datetime
from typing import Dict, List, Optional
from dotenv import load_dotenv

# SSL 경고 무시
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

load_dotenv()

class KISClient:
    """KIS API 클라이언트 - 환경별 자동 선택"""
    
    # 서버 URL
    DEV_BASE_URL = "https://openapivts.koreainvestment.com:29443"  # 모의투자
    PROD_BASE_URL = "https://openapi.koreainvestment.com:9443"     # 실전투자
    
    def __init__(self):
        """KIS API 클라이언트 초기화 (환경별 자동 선택)"""
        
        # 환경 설정 확인
        self.environment = os.getenv('ENVIRONMENT', 'development').lower()
        
        # 환경에 따라 키와 URL 선택
        if self.environment == 'production':
            self.api_key = os.getenv('KIS_PROD_API_KEY', '')
            self.api_secret = os.getenv('KIS_PROD_API_SECRET', '')
            self.account = os.getenv('KIS_PROD_ACCOUNT_NUMBER', '')
            self.base_url = self.PROD_BASE_URL
            env_label = "🔴 PRODUCTION (실전투자)"
        else:
            self.api_key = os.getenv('KIS_DEV_API_KEY', '')
            self.api_secret = os.getenv('KIS_DEV_API_SECRET', '')
            self.account = os.getenv('KIS_DEV_ACCOUNT_NUMBER', '')
            self.base_url = self.DEV_BASE_URL
            env_label = "🟢 DEVELOPMENT (모의투자)"
        
        # 유효성 검사
        if not self.api_key or self.api_key.startswith('your_'):
            raise ValueError(f"❌ KIS API 키를 .env에 설정하세요! (환경: {self.environment})")
        
        self.access_token = None
        self.token_expired = None
        self.last_update = None
        
        print(f"✅ KIS Client 초기화 완료")
        print(f"   환경: {env_label}")
        print(f"   서버: {self.base_url}")
        print(f"   Account: {self.account[:10]}***")
    
    def get_access_token(self) -> bool:
        """KIS API 접근 토큰 발급"""
        try:
            print("\n토큰 발급 중...")
            
            # 정확한 엔드포인트
            url = f"{self.base_url}/oauth2/tokenP"
            
            # JSON Body 형식
            headers = {
                "Content-Type": "application/json"
            }
            
            body = {
                "grant_type": "client_credentials",
                "appkey": self.api_key,
                "appsecret": self.api_secret
            }
            
            print(f"   URL: {url}")
            print(f"   Method: POST")
            
            # 요청 전송
            response = requests.post(
                url,
                headers=headers,
                json=body,
                verify=False,
                timeout=10
            )
            
            print(f"   Status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                
                # 응답에서 토큰 추출
                self.access_token = data.get('access_token')
                self.token_expired = data.get('access_token_token_expired')
                
                if self.access_token:
                    print(f"✅ 토큰 발급 완료!")
                    print(f"   유효기간: {self.token_expired}")
                    return True
                else:
                    print(f"❌ 응답에 access_token이 없습니다")
                    print(f"   응답: {json.dumps(data, indent=2, ensure_ascii=False)}")
                    return False
            else:
                error_data = response.json()
                print(f"❌ 토큰 발급 실패!")
                print(f"   상태: {response.status_code}")
                print(f"   에러: {json.dumps(error_data, indent=2, ensure_ascii=False)}")
                return False
                
        except Exception as e:
            print(f"❌ 토큰 발급 오류: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def get_kospi_kosdaq(self) -> Dict:
        """KOSPI/KOSDAQ 지수 조회 (실제 API)"""
        try:
            print("\nKOSPI/KOSDAQ 조회 중...")
            
            if not self.access_token:
                if not self.get_access_token():
                    return {}
            
            # 【정확한 엔드포인트】지수 현재가 API
            url = f"{self.base_url}/uapi/domestic-stock/v1/quotations/inquire-index-price"
            
            # 【정확한 헤더】
            headers = {
                "authorization": f"Bearer {self.access_token}",
                "appkey": self.api_key,
                "appsecret": self.api_secret,
                "tr_id": "FHPUP02100000",
                "custtype": "P"
            }
            
            # KOSPI 조회
            params_kospi = {
                "FID_COND_MRKT_DIV_CODE": "U",
                "FID_INPUT_ISCD": "0001"
            }
            
            # KOSDAQ 조회
            params_kosdaq = {
                "FID_COND_MRKT_DIV_CODE": "U",
                "FID_INPUT_ISCD": "1001"
            }
            
            # KOSPI 호출
            print("   KOSPI 조회...")
            response_kospi = requests.get(
                url,
                headers=headers,
                params=params_kospi,
                verify=False,
                timeout=10
            )
            
            kospi_data = {}
            if response_kospi.status_code == 200:
                data_kospi = response_kospi.json()
                output_kospi = data_kospi.get('output', {})
                kospi_data = {
                    "kospi_index": float(output_kospi.get('bstp_nmix_prpr', 0)),
                    "kospi_change": float(output_kospi.get('bstp_nmix_prdy_vrss', 0)),
                    "kospi_change_rate": float(output_kospi.get('bstp_nmix_prdy_ctrt', 0)),
                    "kospi_volume": int(output_kospi.get('acml_vol', 0))
                }
                print(f"   ✅ KOSPI: {kospi_data['kospi_index']}")
            else:
                print(f"   ❌ KOSPI 조회 실패: {response_kospi.status_code}")
            
            # KOSDAQ 호출
            print("   KOSDAQ 조회...")
            response_kosdaq = requests.get(
                url,
                headers=headers,
                params=params_kosdaq,
                verify=False,
                timeout=10
            )

            kosdaq_data = {}
            if response_kosdaq.status_code == 200:
                data_kosdaq = response_kosdaq.json()
                output_kosdaq = data_kosdaq.get('output', {})
                kosdaq_data = {
                    "kosdaq_index": float(output_kosdaq.get('bstp_nmix_prpr', 0)),
                    "kosdaq_change": float(output_kosdaq.get('bstp_nmix_prdy_vrss', 0)),
                    "kosdaq_change_rate": float(output_kosdaq.get('bstp_nmix_prdy_ctrt', 0)),
                    "kosdaq_volume": int(output_kosdaq.get('acml_vol', 0))
                }
                print(f"   ✅ KOSDAQ: {kosdaq_data['kosdaq_index']}")
            else:
                print(f"   ❌ KOSDAQ 조회 실패: {response_kosdaq.status_code}")
                # 디버깅 정보 출력
                print(f"   응답 헤더: {dict(response_kosdaq.headers)}")
                print(f"   응답 본문: {response_kosdaq.text[:200]}")
                print(f"   요청 URL: {response_kosdaq.url}")
                print(f"   요청 파라미터: {params_kosdaq}")
            
            # 결과 통합
            result = {
                **kospi_data,
                **kosdaq_data,
                "timestamp": datetime.now().isoformat()
            }
            
            self.last_update = datetime.now()
            return result
            
        except Exception as e:
            print(f"❌ KOSPI/KOSDAQ 조회 오류: {e}")
            import traceback
            traceback.print_exc()
            return {}
    
    def test_connection(self) -> bool:
        """API 연결 테스트"""
        try:
            print("="*60)
            print("KIS API 연결 테스트")
            print("="*60)
            
            # Step 1: 토큰 발급
            if not self.get_access_token():
                return False
            
            # Step 2: 데이터 조회
            data = self.get_kospi_kosdaq()
            
            if data:
                print("\n" + "="*60)
                print("✅ KIS API 연결 성공!")
                print("="*60)
                print(f"환경: {self.environment}")
                print(f"\n【지수 정보】")
                
                if 'kospi_index' in data:
                    print(f"KOSPI: {data['kospi_index']:.2f}")
                    print(f"  전일 대비: {data.get('kospi_change', 0):+.2f}")
                    print(f"  변화율: {data.get('kospi_change_rate', 0):+.2f}%")
                    print(f"  거래량: {data.get('kospi_volume', 0):,}")
                
                if 'kosdaq_index' in data:
                    print(f"\nKOSDAQ: {data['kosdaq_index']:.2f}")
                    print(f"  전일 대비: {data.get('kosdaq_change', 0):+.2f}")
                    print(f"  변화율: {data.get('kosdaq_change_rate', 0):+.2f}%")
                    print(f"  거래량: {data.get('kosdaq_volume', 0):,}")
                
                print(f"\n마지막 업데이트: {self.last_update}")
                return True
            else:
                print("\n❌ 데이터 조회 실패")
                return False
            
        except Exception as e:
            print(f"❌ 테스트 실패: {e}")
            import traceback
            traceback.print_exc()
            return False

if __name__ == "__main__":
    try:
        client = KISClient()
        client.test_connection()
    except ValueError as e:
        print(f"❌ 설정 오류: {e}")
    except Exception as e:
        print(f"❌ 오류: {e}")
        import traceback
        traceback.print_exc()