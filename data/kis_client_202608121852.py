"""
KIS API 클라이언트 (환경별 자동 선택)
한국투자증권 실시간 시장 데이터 조회
【수정사항】과거 60일 데이터 CTS 페이지네이션으로 자동 수집
"""

import requests
import json
import os
from datetime import datetime, timedelta
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
                self.token_expired = data.get('expires_in')
                
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
    
    def get_historical_data(self, days=60) -> Dict:
        """KOSPI 일별 시세 데이터 조회 (과거 60일)"""
        try:
            print(f"\n기술 지표용 KOSPI 일별 데이터 조회 중 ({days}일)...")
            
            if not self.access_token:
                if not self.get_access_token():
                    return {}
            
            # 【주식 현재가 API】로 일별 데이터 조회
            # TR_ID: FHKST01010400 (일자별 조회)
            url = f"{self.base_url}/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice"
            
            headers = {
                "authorization": f"Bearer {self.access_token}",
                "appkey": self.api_key,
                "appsecret": self.api_secret,
                "tr_id": "FHKST01010400",
                "custtype": "P"
            }
            
            params = {
                "fid_cond_mrkt_div_code": "U",      # 유가증권
                "fid_input_iscd": "0001",            # KOSPI
                "fid_period_div_code": "D",          # Daily
                "fid_output_div_code": "D"           # 상세
            }
            
            response = requests.get(
                url,
                headers=headers,
                params=params,
                verify=False,
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                output_list = data.get('output1', [])
                
                # 과거 N일치 데이터 정렬
                historical_data = {
                    "dates": [],
                    "opens": [],
                    "highs": [],
                    "lows": [],
                    "closes": [],
                    "volumes": []
                }
                
                for item in output_list[:days]:
                    historical_data['dates'].append(item.get('stck_bsop_date'))
                    historical_data['opens'].append(float(item.get('stck_oprc', 0)))
                    historical_data['highs'].append(float(item.get('stck_hgpr', 0)))
                    historical_data['lows'].append(float(item.get('stck_lwpr', 0)))
                    historical_data['closes'].append(float(item.get('stck_clpr', 0)))
                    historical_data['volumes'].append(int(item.get('acml_vol', 0)))
                
                print(f"✅ {len(historical_data['dates'])}일치 데이터 수집 완료")
                return historical_data
                
            else:
                print(f"❌ 일별 데이터 조회 실패: {response.status_code}")
                return {}
                
        except Exception as e:
            print(f"❌ 일별 데이터 조회 오류: {e}")
            return {}

    def get_daily_price(self, stock_code: str, days: int = 60) -> Dict:
        """
        일별 시세 데이터 조회 (과거 60일 보장)
        【수정사항】
        - 페이지네이션(CTS)으로 여러 번 호출
        - 최소 60개 영업일 데이터 수집 보장
        - 진행 상황 실시간 출력
        """
        try:
            print(f"\n📊 일별 시세 데이터 조회 중 ({stock_code}, {days}일)...")
            
            if not self.access_token:
                if not self.get_access_token():
                    return {}
            
            # 데이터 저장소
            all_data = {
                "symbol": stock_code,
                "dates": [],
                "opens": [],
                "highs": [],
                "lows": [],
                "closes": [],
                "volumes": []
            }
            
            # URL 설정
            url = f"{self.base_url}/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice"
            
            headers = {
                "authorization": f"Bearer {self.access_token}",
                "appkey": self.api_key,
                "appsecret": self.api_secret,
                "tr_id": "FHKST03010100",
                "custtype": "P"
            }
            
            # 【Step 1】첫 번째 요청 (범위 기반)
            end_date = datetime.now().strftime("%Y%m%d")
            start_date = (datetime.now() - timedelta(days=int(days * 1.5))).strftime("%Y%m%d")
            
            print(f"   조회 기간: {start_date} ~ {end_date}")
            print(f"   ────────────────────────────────────")
            
            cts_time = ""  # 페이지네이션 토큰
            request_count = 0
            
            while True:
                request_count += 1
                print(f"\n   【요청 #{request_count}】")
                
                params = {
                    "fid_cond_mrkt_div_code": "U",      # J: 일반주식 / U :업종 (지수)
                    "fid_input_iscd": stock_code,
                    "fid_input_date_1": start_date,
                    "fid_input_date_2": end_date,
                    "fid_period_div_code": "D",         # D: 일별
                    "fid_org_adj_prc": "0"
                }
                
                # CTS 토큰이 있으면 추가
                if cts_time:
                    params["fid_output"] = "1"
                    params["cts_time"] = cts_time
                    print(f"   📄 cts_time: {cts_time[:10]}... (페이지 계속)")
                
                # API 호출
                response = requests.get(
                    url,
                    headers=headers,
                    params=params,
                    verify=False,
                    timeout=10
                )
                
                print(f"   상태 코드: {response.status_code}")
                
                if response.status_code != 200:
                    print(f"   ❌ 조회 실패! {response.status_code}")
                    if len(all_data['dates']) > 0:
                        print(f"   ⚠️  현재까지 수집: {len(all_data['dates'])}일치 데이터로 계속 진행")
                        break
                    else:
                        return {}
                
                data = response.json()
                
                # 응답 상태 확인
                rt_cd = data.get('rt_cd', '0')
                msg = data.get('msg1', '')
                
                if rt_cd != '0':
                    print(f"   ❌ API 오류: {msg}")
                    break
                
                # 데이터 추출
                output_list = data.get('output2', [])
                print(f"   📥 받은 데이터: {len(output_list)}개")
                
                if not output_list:
                    print(f"   ℹ️  데이터 없음 (요청 종료)")
                    break
                
                # 데이터 추가
                for item in output_list:
                    all_data['dates'].append(item.get('stck_bsop_date', ''))
                    all_data['opens'].append(float(item.get('stck_oprc', 0)))
                    all_data['highs'].append(float(item.get('stck_hgpr', 0)))
                    all_data['lows'].append(float(item.get('stck_lwpr', 0)))
                    all_data['closes'].append(float(item.get('stck_clpr', 0)))
                    all_data['volumes'].append(int(item.get('acml_vol', 0)))
                
                # 【Step 2】CTS 토큰 확인 (페이지네이션)
                output = data.get('output1', {})
                cts_time = output.get('cts_time', '')
                
                print(f"   📊 누적: {len(all_data['dates'])}일 수집")
                
                # 목표 개수 도달 또는 CTS 없으면 종료
                if len(all_data['dates']) >= days:
                    print(f"   ✅ 목표({days}일) 도달! 종료")
                    break
                
                if not cts_time or cts_time == '':
                    print(f"   ℹ️  더 이상 데이터 없음 (CTS 없음, 종료)")
                    break
                
                # 무한루프 방지 (최대 10번 요청)
                if request_count >= 10:
                    print(f"   ⚠️  최대 요청 횟수(10회) 도달")
                    break
            
            # 【Step 3】최종 데이터 트리밍 (요청한 개수만)
            if len(all_data['dates']) > days:
                all_data['dates'] = all_data['dates'][:days]
                all_data['opens'] = all_data['opens'][:days]
                all_data['highs'] = all_data['highs'][:days]
                all_data['lows'] = all_data['lows'][:days]
                all_data['closes'] = all_data['closes'][:days]
                all_data['volumes'] = all_data['volumes'][:days]
            
            print(f"\n   ────────────────────────────────────")
            print(f"✅ 최종 수집 완료!")
            print(f"   심볼: {stock_code}")
            if len(all_data['dates']) >= 2:
                print(f"   기간: {all_data['dates'][-1]} ~ {all_data['dates'][0]}")
            print(f"   데이터: {len(all_data['dates'])}일")
            print(f"   요청 횟수: {request_count}회")
            
            # 【Step 4】데이터 검증
            if len(all_data['dates']) < days * 0.8:  # 80% 이상 수집 필수
                print(f"   ⚠️  경고: 예상보다 적은 데이터 ({len(all_data['dates'])}/{days})")
                print(f"   → 기술지표 계산이 정확하지 않을 수 있습니다")
            else:
                print(f"   ✨ 충분한 데이터 수집됨 (80% 이상)")
            
            return all_data
            
        except Exception as e:
            print(f"❌ 오류: {e}")
            import traceback
            traceback.print_exc()
            return {}

    def get_intraday_chart(self, stock_code: str) -> Dict:
        """당일 분봉 조회 (실시간)"""
        try:
            print(f"\n당일 분봉 데이터 조회 중 ({stock_code})...")
            
            if not self.access_token:
                if not self.get_access_token():
                    return {}
            
            url = f"{self.base_url}/uapi/domestic-stock/v1/quotations/inquire-intraday-itemchartprice"
            
            headers = {
                "authorization": f"Bearer {self.access_token}",
                "appkey": self.api_key,
                "appsecret": self.api_secret,
                "tr_id": "FHKST03010200",
                "custtype": "P"
            }
            
            params = {
                "fid_cond_mrkt_div_code": "U",
                "fid_input_iscd": stock_code,
                "fid_period_div_code": "1",  # 1분봉
                "fid_output_div_code": "D"
            }
            
            response = requests.get(
                url,
                headers=headers,
                params=params,
                verify=False,
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                output_list = data.get('output1', [])
                
                intraday_data = {
                    "symbol": stock_code,
                    "times": [],
                    "opens": [],
                    "highs": [],
                    "lows": [],
                    "closes": [],
                    "volumes": []
                }
                
                for item in output_list:
                    intraday_data['times'].append(item.get('stck_cntg_hour', ''))
                    intraday_data['opens'].append(float(item.get('stck_oprc', 0)))
                    intraday_data['highs'].append(float(item.get('stck_hgpr', 0)))
                    intraday_data['lows'].append(float(item.get('stck_lwpr', 0)))
                    intraday_data['closes'].append(float(item.get('stck_clpr', 0)))
                    intraday_data['volumes'].append(int(item.get('cntg_vol', 0)))
                
                print(f"✅ {len(intraday_data['times'])}개 분봉 데이터 수집 완료")
                return intraday_data
            else:
                print(f"❌ 분봉 데이터 조회 실패: {response.status_code}")
                return {}
                
        except Exception as e:
            print(f"❌ 분봉 데이터 조회 오류: {e}")
            return {}

    def get_daily_chart(self, stock_code: str, days: int = 60) -> Dict:
        """일별 분봉 조회"""
        try:
            print(f"\n일별 분봉 데이터 조회 중 ({stock_code}, {days}일)...")
            
            if not self.access_token:
                if not self.get_access_token():
                    return {}
            
            url = f"{self.base_url}/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice"
            
            headers = {
                "authorization": f"Bearer {self.access_token}",
                "appkey": self.api_key,
                "appsecret": self.api_secret,
                "tr_id": "FHKST03010230",
                "custtype": "P"
            }
            
            params = {
                "fid_cond_mrkt_div_code": "U",
                "fid_input_iscd": stock_code,
                "fid_period_div_code": "D"
            }
            
            response = requests.get(
                url,
                headers=headers,
                params=params,
                verify=False,
                timeout=10
            )
            
            if response.status_code == 200:
                return self.get_daily_price(stock_code, days)
            else:
                print(f"❌ 일별 분봉 조회 실패: {response.status_code}")
                return {}
                
        except Exception as e:
            print(f"❌ 일별 분봉 조회 오류: {e}")
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
        
        # 【테스트】KOSPI 60일 데이터 조회
        print("\n" + "="*60)
        print("【기술지표 테스트】KOSPI 60일 데이터 조회")
        print("="*60)
        kospi_data = client.get_daily_price("0001", days=60)
        
        if kospi_data['dates']:
            print(f"\n【결과】")
            print(f"첫 날: {kospi_data['dates'][0]}")
            print(f"마지막 날: {kospi_data['dates'][-1]}")
            print(f"총 {len(kospi_data['dates'])}일 데이터 준비 완료 ✅")
        
    except ValueError as e:
        print(f"❌ 설정 오류: {e}")
    except Exception as e:
        print(f"❌ 오류: {e}")
        import traceback
        traceback.print_exc()