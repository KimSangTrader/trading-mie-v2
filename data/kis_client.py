"""
KIS API 클라이언트 (환경별 자동 선택)
한국투자증권 실시간 시장 데이터 조회
【최종 수정】샘플 코드 방식 적용 - FHPUP02120000 (지수전용 API)

================================================================================
【변경 이력】
================================================================================
【2026-08-12】최초 생성
- KIS API 클라이언트 초기화 및 토큰 관리
- KOSPI/KOSDAQ 실시간 지수 조회
- 일별 시세 데이터 (60일) 자동 수집
- FHPUP02120000 API 사용 (지수전용)
- 환경별 자동 선택 (production/development)

【2026-08-13】데이터 정렬 로직 추가 + closes 순서 보장
- 변경 사항:
  * get_daily_price() 라인 373-390 수정
  * API 응답 데이터를 그대로 저장하지 않고 날짜순 정렬
  * 오래된 날짜부터 최신 날짜 순서로 정렬
  * closes[-1]이 실제 최신 종가가 되도록 보장
  * sorted_indices를 사용한 병렬 정렬 (dates, opens, highs, lows, closes, volumes)
- 목적:
  * 5일 데이터와 60일 데이터 불일치 문제 해결
  * closes 리스트의 마지막 값이 현재가가 되도록 수정
  * 기술지표 계산의 정확도 향상
- 영향:
  * 기존 기능 100% 유지
  * 데이터 순서만 보장 추가
  * TechnicalAnalyzer에서 closes[-1]이 현재가를 올바르게 반영

【2026-08-14】Phase 5-2: 개별 종목 기본분석(PER/PBR) 조회 메서드 추가
- 변경 사항:
  * get_stock_fundamental(stock_code) 메서드 신규 추가
  * FHKST01010100(국내주식 현재가 시세) API 사용, FID_COND_MRKT_DIV_CODE="J"
  * PER, PBR, EPS, BPS 실시간 조회 (개별 종목 전용, 지수에는 사용 불가)
  * 배당수익률은 이 API에 없음 - None 반환, 호출부(ValuationAnalyzer)에서 폴백 처리
- 목적: ValuationAnalyzer Mock 데이터 → 실제 개별 종목 데이터 연동 (신뢰도 41.6% → 70%+ 목표)
- 영향: 기존 메서드(get_kospi_kosdaq, get_daily_price) 변경 없음, 100% 하위 호환

【2026-08-17】배당수익률 일괄 조회 메서드 추가 (Phase 5-8)
- 변경 사항:
  * get_dividend_rates(market, days_back=365) 메서드 신규 추가
  * "국내주식 배당률 상위"(순위분석) API 사용, tr_id: HHKDB13470100
    (KIS 공식 GitHub reference: open-trading-api/examples_llm/domestic_stock/
     dividend_rate/dividend_rate.py 참고해서 그대로 이식함)
  * get_stock_fundamental()과 달리 "종목 하나씩" 조회하는 API가 아니라 "시장
    전체 랭킹"을 한 번에 반환하는 API라서, 종목 수만큼 호출하지 않고 시장(KOSPI/
    KOSDAQ)당 1회(+페이지네이션)만 호출해서 {종목코드: 배당률} 딕셔너리로 반환
  * tr_cont 헤더가 "M"이면 다음 페이지가 더 있다는 뜻 - CTS_AREA는 그대로 두고
    tr_cont만 "N"으로 바꿔 재요청 (공식 레퍼런스와 동일한 방식, 최대 10페이지)
  * GB3="2"(현금배당) 고정 - 통상 "배당수익률"이라고 하면 현금배당 기준
- 영향: get_stock_fundamental()은 변경 없음(여전히 dividend_yield=None 반환).
  실제 배당수익률은 이 신규 메서드로 별도 조회해서 호출부(ValuationCollector)가
  종목코드 기준으로 병합한다.
- 【사용자 컴퓨터 실측(2026-08-17)】1차 시도에서 timeout=10초로 ReadTimeout 발생 →
  30초로 늘려서 재시도한 결과, 이번엔 응답은 왔지만 이 방식 자체가 부적합함이
  드러남: (a) KOSPI 20종목까지만 반환됨(랭킹 API라 상위권만 줌 - 애초에 종목
  수천 개를 커버할 수 없는 API였음), (b) divi_rate 필드가 "배당수익률(%)"이
  아니라 "액면배당률"이었음 - 삼성화재해상보험1우 실측: per_sto_divi_amt(배당금)
  =19505원, divi_rate=3901.00 → 19505/500(액면가)*100=3901.0로 정확히 일치.
  액면가는 종목마다 달라서 종목 간 상대비교에 쓸 수 없는 값이었다.
  → get_dividend_rates()는 이 버전에서 완전히 제거. 대신 사용자가 첨부한 문서
  ("한국거래소를 이용한 배당율조회와 실시간 조회 연동방법.docx") 제안대로
  KRX 정보데이터시스템(data.krx.co.kr, KIS와 무관한 별도 공개 API)에서 시장
  전체 배당수익률을 한 번에 받아오는 방식(data/krx_data.py)으로 교체함.
================================================================================
"""
import requests
import json
import os
import time
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

    # 【2026-08-21】토큰 재사용 주기 (Phase 5-9: main.py 상시루프화)
    # KIS 토큰 실제 유효기간은 24시간(86400초)이지만, main.py가 이제
    # systemd 상시 프로세스로 떠서 하루에도 여러 번(스케줄러 체크 루프)
    # KISClient 메서드를 호출하게 된다 - 매번 새로 토큰을 받으면 불필요한
    # 재발급이 반복되므로, 22시간(사용자 지정 - 실제 만료 24h보다 2h 여유)
    # 마다 한 번만 재발급하고 그 사이엔 기존 토큰을 재사용한다.
    TOKEN_REFRESH_INTERVAL_SECONDS = 22 * 60 * 60

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
        self.token_issued_at = None  # 【2026-08-21】토큰 재사용 판단용 (ensure_valid_token 참고)

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
                    self.token_issued_at = datetime.now()
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
    
    def ensure_valid_token(self) -> bool:
        """
        토큰이 아예 없으면 새로 발급받고, 있으면 마지막 발급 후
        TOKEN_REFRESH_INTERVAL_SECONDS(22시간)가 지났는지만 확인해서
        지났을 때만 재발급한다. 그 안에서는 기존 토큰을 그대로 재사용한다.

        【2026-08-21】main.py가 상시 프로세스(systemd)로 바뀌면서, 하루에도
        여러 번 이 클라이언트의 메서드가 호출된다. 기존의 "토큰이 None일
        때만 재발급" 방식은 인스턴스 하나를 계속 재사용하는 한 문제없지만,
        장시간 떠있는 프로세스에서는 22시간마다 능동적으로 갱신해줘야
        실제 만료(24시간) 전에 항상 유효한 토큰을 유지할 수 있다.
        """
        if self.access_token is None or self.token_issued_at is None:
            return self.get_access_token()

        elapsed = (datetime.now() - self.token_issued_at).total_seconds()
        if elapsed >= self.TOKEN_REFRESH_INTERVAL_SECONDS:
            print(f"\n토큰 발급 후 {elapsed / 3600:.1f}시간 경과 - 재발급합니다")
            return self.get_access_token()

        return True

    def get_kospi_kosdaq(self) -> Dict:
        """KOSPI/KOSDAQ 지수 조회 (실제 API)"""
        try:
            print("\nKOSPI/KOSDAQ 조회 중...")
            
            if not self.ensure_valid_token():
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

    def get_stock_fundamental(self, stock_code: str) -> Dict:
        """
        개별 종목 기본분석 지표 조회 (PER, PBR, EPS, BPS)
        【Phase 5-2 신규】ValuationAnalyzer 실제 데이터 연동용

        - API: 국내주식 현재가 시세 (inquire-price)
        - tr_id: FHKST01010100
        - FID_COND_MRKT_DIV_CODE: "J" (KRX 주식 - 지수와 달리 "U"가 아님)

        주의:
        - 이 API는 지수(KOSPI/KOSDAQ)가 아닌 "개별 종목"에만 사용 가능
          (지수는 PER/PBR 개념이 없음 - 구성종목 가중평균 방식은 별도 산출 필요)
        - 배당수익률(dividend_yield)은 이 API에 포함되지 않음.
          KIS "예탁원정보(배당)" API(HHKDB669102C0) 등 별도 연동이 필요하며,
          현재는 조회하지 않고 None으로 반환 (호출부에서 폴백 처리)
        """
        try:
            print(f"\n📈 종목 기본분석 지표 조회 중 ({stock_code})...")

            if not self.ensure_valid_token():
                return {}

            url = f"{self.base_url}/uapi/domestic-stock/v1/quotations/inquire-price"

            headers = {
                "authorization": f"Bearer {self.access_token}",
                "appkey": self.api_key,
                "appsecret": self.api_secret,
                "tr_id": "FHKST01010100",  # 【중요】국내주식 현재가 시세 (개별 종목 전용)
                "custtype": "P"
            }

            params = {
                "FID_COND_MRKT_DIV_CODE": "J",  # 【중요】J: 주식 (지수의 "U"와 다름)
                "FID_INPUT_ISCD": stock_code
            }

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
                return {}

            data = response.json()
            rt_cd = data.get('rt_cd', '0')

            if rt_cd != '0':
                print(f"   ❌ API 오류: {data.get('msg1', '')}")
                return {}

            output = data.get('output', {})

            def _to_float(value, default=0.0):
                try:
                    return float(value)
                except (TypeError, ValueError):
                    return default

            result = {
                "symbol": stock_code,
                "current_price": _to_float(output.get('stck_prpr')),
                "per": _to_float(output.get('per')),
                "pbr": _to_float(output.get('pbr')),
                "eps": _to_float(output.get('eps')),
                "bps": _to_float(output.get('bps')),
                # 배당수익률: inquire-price 응답에 없음 (별도 API 필요) → 폴백은 호출부 책임
                "dividend_yield": None,
                "timestamp": datetime.now().isoformat()
            }

            print(f"   ✅ PER: {result['per']:.2f} / PBR: {result['pbr']:.2f} "
                  f"/ EPS: {result['eps']:.0f} / BPS: {result['bps']:.0f}")

            return result

        except Exception as e:
            print(f"❌ 종목 기본분석 지표 조회 오류: {e}")
            import traceback
            traceback.print_exc()
            return {}

    # get_dividend_rates()는 여기 있었으나 제거됨 - 실측 결과 부적합한 API였음
    # (시장당 20종목까지만 반환하는 랭킹 API였고, 필드도 배당수익률이 아니라
    # 액면배당률이었음). 배당수익률은 이제 data/krx_data.py(KRX 정보데이터시스템,
    # KIS와 무관한 별도 공개 API)에서 조회한다. 자세한 경위는 파일 상단 변경
    # 이력의 【2026-08-17】 항목 참고.

    def get_daily_price(self, stock_code: str, days: int = 60) -> Dict:
        """
        일별 시세 데이터 조회 (과거 60일 보장)
        【샘플 코드 방식 적용】
        - FHPUP02120000 (국내업종 일자별지수 API) 사용
        - FID_INPUT_DATE_1 기준 날짜부터 과거 방향으로 ~100개 캔들 반환
        - END_DATE부터 시작해서 역순 순회
        
        【2026-08-13 수정】데이터 정렬 로직 추가
        - API 응답을 그대로 사용하지 않고 날짜순 정렬
        - closes[-1]이 최신 종가가 되도록 보장
        """
        try:
            print(f"\n📊 일별 시세 데이터 조회 중 ({stock_code}, {days}일)...")
            
            if not self.ensure_valid_token():
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
            
            # URL 설정 - 【중요】지수전용 API
            url = f"{self.base_url}/uapi/domestic-stock/v1/quotations/inquire-index-daily-price"
            
            headers = {
                "authorization": f"Bearer {self.access_token}",
                "appkey": self.api_key,
                "appsecret": self.api_secret,
                "tr_id": "FHPUP02120000",  # 【중요】국내업종 일자별지수
                "custtype": "P"
            }
            
            # 【Step 1】날짜 범위 설정
            end_date = datetime.now().strftime("%Y%m%d")
            start_date = (datetime.now() - timedelta(days=int(days * 1.5))).strftime("%Y%m%d")
            
            start = datetime.strptime(start_date, "%Y%m%d")
            end = datetime.strptime(end_date, "%Y%m%d")
            
            print(f"   조회 기간: {start_date} ~ {end_date}")
            print(f"   ────────────────────────────────────")
            
            # 【Step 2】역순 순회 (END_DATE부터 시작)
            current_date = end
            request_count = 0
            
            while current_date >= start:
                request_count += 1
                date_string = current_date.strftime("%Y%m%d")
                
                print(f"\n   【요청 #{request_count}】{date_string} 기준")
                
                # 【중요】FID_INPUT_DATE_1만 사용 (기준 날짜)
                params = {
                    "FID_COND_MRKT_DIV_CODE": "U",      # U: 업종
                    "FID_INPUT_ISCD": stock_code,
                    "FID_PERIOD_DIV_CODE": "D",         # D: 일별
                    "FID_INPUT_DATE_1": date_string     # 【중요】기준 날짜만
                }
                
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
                
                # 【중요】output2에서 데이터 추출
                output_list = data.get('output2', [])
                print(f"   📥 받은 데이터: {len(output_list)}개")
                
                if not output_list:
                    print(f"   ℹ️  데이터 없음 (기준일 이전 거래 없음)")
                    # 하루 이전으로 이동
                    current_date -= timedelta(days=1)
                    time.sleep(0.2)  # API 과도 호출 방지
                    continue
                
                # 데이터 추가
                row_dates = []
                for item in output_list:
                    date_val = item.get('stck_bsop_date', '')
                    
                    all_data['dates'].append(date_val)
                    all_data['opens'].append(float(item.get('bstp_nmix_oprc', 0)))
                    all_data['highs'].append(float(item.get('bstp_nmix_hgpr', 0)))
                    all_data['lows'].append(float(item.get('bstp_nmix_lwpr', 0)))
                    all_data['closes'].append(float(item.get('bstp_nmix_prpr', 0)))
                    all_data['volumes'].append(int(item.get('acml_vol', 0)))
                    
                    if date_val:
                        row_dates.append(date_val)
                
                print(f"   📊 누적: {len(all_data['dates'])}일 수집")
                
                # 【Step 3】가장 오래된 날짜 확인
                if row_dates:
                    # 문자열로 정렬 (YYYYMMDD 형식이므로 가능)
                    oldest_date_str = min(row_dates)
                    oldest_date = datetime.strptime(oldest_date_str, "%Y%m%d")
                    
                    print(f"   📅 이번 배치 가장 오래된 날: {oldest_date_str}")
                    
                    # 이미 시작일보다 오래된 데이터를 받았다면 종료
                    if oldest_date <= start:
                        print(f"   ✅ 목표({days}일) 도달! 종료")
                        break
                    
                    # 다음 조회는 가장 오래된 날짜 이전부터
                    current_date = oldest_date - timedelta(days=1)
                else:
                    # 데이터 없으면 하루 이전으로
                    current_date -= timedelta(days=1)
                
                # API 과도 호출 방지
                time.sleep(0.2)
                
                # 목표 개수 도달하면 종료
                if len(all_data['dates']) >= days:
                    print(f"   ✅ 목표({days}일) 도달! 종료")
                    break
                
                # 무한루프 방지 (최대 20번 요청)
                if request_count >= 20:
                    print(f"   ⚠️  최대 요청 횟수(20회) 도달")
                    break
            
            # 【Step 4】최종 데이터 트리밍 (요청한 개수만)
            if len(all_data['dates']) > days:
                all_data['dates'] = all_data['dates'][:days]
                all_data['opens'] = all_data['opens'][:days]
                all_data['highs'] = all_data['highs'][:days]
                all_data['lows'] = all_data['lows'][:days]
                all_data['closes'] = all_data['closes'][:days]
                all_data['volumes'] = all_data['volumes'][:days]
            
            # 【2026-08-13 추가】날짜순으로 정렬 (오래된 순 → 최신 순)
            # API 응답이 최신부터 오래된 순서이므로, 날짜를 기준으로 정렬하여
            # closes[-1]이 실제 최신 종가가 되도록 보장
            if len(all_data['dates']) > 0:
                sorted_indices = sorted(range(len(all_data['dates'])), 
                                       key=lambda i: all_data['dates'][i])
                
                all_data['dates'] = [all_data['dates'][i] for i in sorted_indices]
                all_data['opens'] = [all_data['opens'][i] for i in sorted_indices]
                all_data['highs'] = [all_data['highs'][i] for i in sorted_indices]
                all_data['lows'] = [all_data['lows'][i] for i in sorted_indices]
                all_data['closes'] = [all_data['closes'][i] for i in sorted_indices]
                all_data['volumes'] = [all_data['volumes'][i] for i in sorted_indices]
            
            print(f"\n   ────────────────────────────────────")
            print(f"✅ 최종 수집 완료!")
            print(f"   심볼: {stock_code}")
            if len(all_data['dates']) >= 2:
                print(f"   기간: {all_data['dates'][-1]} ~ {all_data['dates'][0]}")
            print(f"   데이터: {len(all_data['dates'])}일")
            print(f"   요청 횟수: {request_count}회")
            
            # 【Step 5】데이터 검증
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
            
            if not self.ensure_valid_token():
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
            
            if not self.ensure_valid_token():
                return {}
            
            return self.get_daily_price(stock_code, days)
                
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