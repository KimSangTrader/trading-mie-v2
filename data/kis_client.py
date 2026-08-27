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
【2026-08-24】개별 종목 투자자(외국인/기관/개인) 순매수 동향 조회 메서드 추가 (Phase 5-18)
- 배경: StockAnalyzer의 수급 25점 컴포넌트가 여태 데이터 소스가 없어 항상 결측
  처리되고 있었다(stock_analyzer.py "알려진 한계 1" 참고) - main.py의
  종목별 라이브 검증(Phase 5-17)이 끝난 뒤 사용자가 "순서대로" 지시한 백로그의
  첫 항목. get_investor_trend(stock_code) 신규 추가.
- API: 주식현재가 투자자(inquire-investor), tr_id FHKST01010900. get_stock_fundamental/
  get_stock_daily_chart와 동일하게 FID_COND_MRKT_DIV_CODE="J"(개별 종목).
  get_stock_daily_chart와 달리 날짜 범위 파라미터가 없다(KIS가 자체적으로 최근
  영업일분을 돌려주는 API) - 공식 예제(KIS GitHub, koreainvestment/open-trading-api,
  examples_llm/domestic_stock/inquire_investor/)를 이 세션에서 직접 fetch해
  tr_id/파라미터/응답 필드명(stck_bsop_date, {prsn,frgn,orgn}_ntby_qty,
  {prsn,frgn,orgn}_ntby_tr_pbmn 등)을 확인하고 그대로 이식했다 - get_dividend_rates()
  때와 같은 방식(공식 레퍼런스 이식)이지만, 이번엔 실제 응답으로 라이브 검증은
  여전히 못했다(이 세션은 KIS API에 직접 접근 불가 - 지금까지와 동일한 한계).
- 순매수 "거래대금"(_tr_pbmn) 필드는 그대로 노출하되, 이 세션은 그 단위(원/천원/
  백만원)를 검증할 방법이 없어(get_dividend_rates()에서 divi_rate 단위를 잘못
  짚었던 전례 - 【2026-08-17】항목 참고) market_intelligence 쪽 점수 계산
  (market_intelligence/supply_demand.py)은 단위가 명확한 "수량"(_ntby_qty, 주식 수)
  필드만 쓰도록 설계했다. 거래대금 필드가 필요해지면 그때 실제 응답으로 단위를
  검증하고 쓴다.
【2026-08-26】주문 실행 API 3종 추가 - place_order/get_balance/get_pending_orders
  (Phase 6-3: 실제 매매 프로그램, market_intelligence/trade_execution/의 순수
  계산기들을 KIS 주문 API와 연결하는 첫 단계)
- 배경: Phase 6-1/6-2에서 만든 entry_filter/position_sizer/pyramiding/exit_engine은
  전부 "판정"만 하는 순수 계산기였고, 실제로 KIS에 주문을 넣거나 잔고를 조회하는
  메서드가 이 파일에 전혀 없었다(__main__ 테스트가 시세 조회만 하는 것에서도
  드러남). trade_execution_pipeline.py(다음 단계)가 이 3개 메서드를 호출해서
  판정 결과를 실제 주문으로 연결한다.
- 【검증 방식】이전 항목들(get_stock_daily_chart, get_investor_trend)과 동일하게
  이 세션은 KIS API에 직접 접근할 수 없다(클라우드 샌드박스 네트워크 제약) -
  대신 이번엔 KIS 공식 GitHub(koreainvestment/open-trading-api,
  examples_llm/domestic_stock/{order_cash,inquire_balance,inquire_psbl_rvsecncl}/
  *.py)와 kis_auth.py의 _url_fetch()를 이 세션에서 직접 fetch해서, tr_id/엔드포인트
  /필수 파라미터명만큼은 "추측"이 아니라 공식 예제 코드 그대로 옮겼다. 단,
  place_order()의 tr_id(TTTC0012U 매수/TTTC0011U 매도, 모의는 앞글자만 V로
  치환)와 필수 파라미터(CANO/ACNT_PRDT_CD/PDNO/ORD_DVSN/ORD_QTY/ORD_UNPR/
  EXCG_ID_DVSN_CD)는 order_cash.py 전문을 그대로 확인했고, get_balance()의
  tr_id(TTTC8434R/VTTC8434R)와 필수 파라미터도 inquire_balance.py 전문으로
  확인했다. get_pending_orders()의 실전 tr_id(TTTC0084R)는 공식 예제로 확인했지만
  모의투자용 tr_id(VTTC0084R)는 예제 파일에 명시가 없어서, kis_auth.py의
  _url_fetch()가 실제로 쓰는 규칙("tr_id 첫 글자가 T/J/C면 모의투자 시 V로
  치환") - 이 파일 자체가 이미 검증한 T→V 치환 규칙 - 을 그대로 적용해 추정한
  것이다.
- 【검증 못 한 부분 - 반드시 라이브 확인 필요】각 API의 "응답" 필드명
  (get_balance()의 pdno/hldg_qty/pchs_avg_pric/prpr/evlu_amt/evlu_pfls_amt/
  evlu_pfls_rt/ord_psbl_qty/dnca_tot_amt/tot_evlu_amt, get_pending_orders()의
  odno/pdno 등, place_order()의 ODNO/ORD_TMD/KRX_FWDG_ORD_ORGNO)은 공식 예제
  코드가 파싱 로직 없이 pandas.DataFrame(output)으로만 넘겨서, 이 세션이 실제
  응답 JSON을 볼 방법이 없었다 - 대신 여러 독립 출처(위키독스 한국투자증권 API
  튜토리얼, mojito 래퍼 라이브러리 문서)에서 일관되게 등장하는 표준 필드명을
  썼다(get_stock_daily_chart/get_investor_trend 때와 동일한 한계 - 최초 실제
  호출에서 다르면 빈 결과가 돌아오고 로그에 원인이 남는다). get_balance()는
  검증 편의를 위해 raw_output1/raw_output2에 API 원본 응답도 그대로 넣어
  반환한다 - 필드명이 안 맞으면 이 raw 값으로 바로 확인 가능.
- 【안전장치】place_order()는 side("buy"/"sell")·order_type("market"/"limit")·
  quantity·(limit이면)price를 호출 전에 검증해서 값이 이상하면 API를 아예
  호출하지 않고 즉시 실패를 반환한다 - 이 메서드 자체는 모의/실전 어느 쪽이든
  "이 세션이 직접 호출하지 않는다"(파이프라인은 사용자 컴퓨터/EC2에서만 실행) -
  이 세션은 코드만 작성하고 실제 주문 실행은 절대 하지 않는다.
【2026-08-27】__init__에 environment 파라미터 추가 (안전 관련 발견)
- 배경: 사용자가 EC2에서 trade_execution_pipeline.py를 처음 수동 실행한 로그를
  공유했는데, 토큰 발급 URL이 `https://openapi.koreainvestment.com:9443`
  (PROD_BASE_URL - 실전투자)였다. 즉 EC2의 .env에 `ENVIRONMENT=production`이
  설정돼 있고, 지금까지의 KISClient()는 이 값을 그대로 읽으므로
  trade_execution_pipeline.py의 `KISClient()`도 자동으로 **실전투자(진짜
  돈) 계정**으로 초기화되고 있었다 - 사용자가 AskUserQuestion에서 명시적으로
  확정한 "모의투자부터 시작"과 반대 상태.
- 다행히 이번 실행에서는 실제 매수/매도 주문까지는 가지 않았다(잔고조회가
  계좌번호 형식 오류로 실패해서 available_cash가 0으로 처리돼 모든 후보가
  진입 조건 이전에 걸러짐 - 아래 항목 참고). 하지만 그 계좌번호 오류만
  아니었다면 실전 계정으로 실제 주문이 나갔을 수 있는 상황이었다.
- 원인: main.py 등 기존 시스템은 ENVIRONMENT=production을 "실전 서버의 더
  정확한 시세를 쓰겠다"는 의도로 설정해 둔 것으로 보이는데(시세 조회 API는
  계정 종류와 무관하게 안전함 - 실제 돈이 움직이지 않음), place_order()처럼
  "주문"을 내는 메서드까지 같은 환경 변수를 공유하다 보니, 시세용 설정이
  주문 실행 환경까지 그대로 따라가 버렸다.
- 조치: __init__(environment=None) 파라미터를 추가해서, 호출부가 명시적으로
  environment를 넘기면 .env의 전역 ENVIRONMENT를 무시하고 그 값을 강제할 수
  있게 했다. trade_execution_pipeline.py의 진입점(__main__)이 이제
  `MIE_TRADE_ENVIRONMENT`라는 별도 환경변수(.env의 기존 ENVIRONMENT와 완전히
  분리, 기본값 "development"=모의투자)로 KISClient를 만든다 - 자세한 내용은
  trade_execution_pipeline.py 변경이력 참고. main.py 등 기존 호출부는
  `KISClient()`를 인자 없이 그대로 쓰므로 동작 변화 없음(하위 호환).
================================================================================
"""
import requests
import json
import os
import sys
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dotenv import load_dotenv

# SSL 경고 무시
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

load_dotenv()

# 【2026-08-22 추가, Phase 5-11 라이브 검증 중 발견】이 파일 곳곳의 print()가
# ✅/❌/⚠️/📊 이모지를 찍는데, Windows에서 출력이 파이프/파일로 리다이렉트되면
# 파이썬이 시스템 기본 코드페이지(cp949)를 써서 UnicodeEncodeError로 죽는 문제가
# 있었다 - main.py에도 동일하게 넣었지만(그쪽이 진입점이라 프로세스 전체를
# 커버함), 이 파일을 단독 실행(`python data/kis_client.py`)하거나 `python -c`로
# 이 모듈만 따로 쓸 때도 안전하도록 여기도 넣어둔다. 리눅스(EC2)는 기본 UTF-8이라
# 이 블록이 사실상 아무 영향 없다.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

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

    def __init__(self, environment: Optional[str] = None):
        """KIS API 클라이언트 초기화 (환경별 자동 선택)

        Args:
            environment: "production" | "development" 중 하나를 명시적으로 넘기면
                .env의 ENVIRONMENT 변수를 무시하고 이 값을 그대로 쓴다. None(기본값,
                기존 모든 호출부의 동작 그대로 유지)이면 지금까지처럼 .env의
                ENVIRONMENT를 읽는다. 【2026-08-27 추가, Phase 6-3 라이브 검증 중
                발견】trade_execution_pipeline.py처럼 "이 클라이언트는 반드시
                모의투자여야 한다"는 요구가 있는 호출부가, main.py 등 나머지
                시스템이 시세 수집용으로 쓰는 전역 ENVIRONMENT(실전 서버 - 시세
                품질을 위해 의도적으로 그렇게 설정돼 있음, PROD 계정에도 시세
                조회는 안전함)에 실수로 얽혀 들어가지 않게 하려고 추가했다.
                자세한 경위는 파일 상단 변경이력 【2026-08-27】참고.
        """

        # 환경 설정 확인
        self.environment = (environment or os.getenv('ENVIRONMENT', 'development')).lower()
        
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

    def get_stock_daily_chart(self, stock_code: str, days: int = 60) -> Dict:
        """
        개별 종목 일봉(OHLCV) 조회 - TechnicalAnalyzer 실데이터 연동용
        【2026-08-22 신규, Phase 5-11】

        - 배경: TechnicalAnalyzer.validate()는 closes/opens/highs/lows/volumes
          (60개 이상 캔들)를 요구하는데, 이 파일에는 그걸 "개별 종목" 코드로
          조회하는 메서드가 전혀 없었다. 기존 get_daily_price()/get_daily_chart()는
          FID_COND_MRKT_DIV_CODE="U"(업종/지수 전용) + tr_id=FHPUP02120000이라
          KOSPI/KOSDAQ 지수 코드("0001"/"1001")에만 쓸 수 있고 개별 종목 코드로는
          쓸 수 없다(파일 맨 아래 __main__ 테스트도 "0001"로 호출하는 것 참고).
          get_stock_fundamental()과 같은 계열(FID_COND_MRKT_DIV_CODE="J")로
          새로 만들었다.
        - API: 국내주식기간별시세(일/주/월/년) (inquire-daily-itemchartprice)
        - tr_id: FHKST03010100
        - 지수 조회(get_daily_price)와 달리 날짜 범위를 한 번에 요청하는 API라서,
          하루씩 반복 조회할 필요 없이 종목 1개당 API 호출 1번이면 충분하다
          (응답이 최대 100건까지 한 번에 옴 - get_daily_price의 while 루프 방식과 다름).
        - 종목별 호출 시 rate limit은 호출부(main.py)가 기존 관례(0.2초 -
          market_intelligence/collectors/valuation_collector.py의
          _DEFAULT_RATE_LIMIT_SEC)를 따라 책임진다 - 이 메서드 자체는 호출 1번만.
        - 【주의】이 세션은 실제 KIS API로 응답 필드명을 검증할 수 없었다(클라우드
          샌드박스 네트워크 제약). 아래 필드명(stck_bsop_date/stck_oprc/stck_hgpr/
          stck_lwpr/stck_clpr/acml_vol)은 KIS Open API 공식 문서 관례를 따라
          작성했으나, get_stock_fundamental() 때도 그랬듯 실제 응답과 다를 수
          있으니 반드시 종목 1~2개로 먼저 실제 호출해 필드가 맞는지 확인 필요
          (사용자 컴퓨터/서버에서 라이브 검증 - 이 세션은 할 수 없음).
        """
        try:
            print(f"\n📊 개별 종목 일봉 데이터 조회 중 ({stock_code}, {days}일)...")

            if not self.ensure_valid_token():
                return {}

            url = f"{self.base_url}/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice"

            headers = {
                "authorization": f"Bearer {self.access_token}",
                "appkey": self.api_key,
                "appsecret": self.api_secret,
                "tr_id": "FHKST03010100",  # 【중요】국내주식기간별시세(일/주/월/년) - 개별 종목 전용
                "custtype": "P"
            }

            # days*1.6일 전부터 오늘까지 - 주말/공휴일 제외하고 실거래일 기준
            # days개를 확보하기 위한 여유(get_daily_price와 동일한 관례)
            end_date = datetime.now().strftime("%Y%m%d")
            start_date = (datetime.now() - timedelta(days=int(days * 1.6))).strftime("%Y%m%d")

            params = {
                "FID_COND_MRKT_DIV_CODE": "J",  # 【중요】J: 주식 (지수의 "U"와 다름)
                "FID_INPUT_ISCD": stock_code,
                "FID_INPUT_DATE_1": start_date,
                "FID_INPUT_DATE_2": end_date,
                "FID_PERIOD_DIV_CODE": "D",      # 일봉
                "FID_ORG_ADJ_PRC": "0"           # 수정주가 반영
            }

            response = requests.get(
                url,
                headers=headers,
                params=params,
                verify=False,
                timeout=10
            )

            if response.status_code != 200:
                print(f"   ❌ 조회 실패! {stock_code} - {response.status_code}")
                return {}

            data = response.json()
            rt_cd = data.get('rt_cd', '0')
            if rt_cd != '0':
                print(f"   ❌ API 오류 ({stock_code}): {data.get('msg1', '')}")
                return {}

            output_list = data.get('output2', [])
            if not output_list:
                print(f"   ℹ️  데이터 없음 ({stock_code})")
                return {}

            rows = []
            for item in output_list:
                date_val = item.get('stck_bsop_date', '')
                if not date_val:
                    continue
                rows.append({
                    "date": date_val,
                    "open": float(item.get('stck_oprc', 0)),
                    "high": float(item.get('stck_hgpr', 0)),
                    "low": float(item.get('stck_lwpr', 0)),
                    "close": float(item.get('stck_clpr', 0)),
                    "volume": int(item.get('acml_vol', 0)),
                })

            # 날짜순(오래된 -> 최신) 정렬 - closes[-1]이 최신 종가가 되도록 보장
            # (get_daily_price와 동일한 관례)
            rows.sort(key=lambda r: r["date"])

            result = {
                "symbol": stock_code,
                "dates": [r["date"] for r in rows],
                "opens": [r["open"] for r in rows],
                "highs": [r["high"] for r in rows],
                "lows": [r["low"] for r in rows],
                "closes": [r["close"] for r in rows],
                "volumes": [r["volume"] for r in rows],
            }

            print(f"   ✅ {stock_code}: {len(rows)}일 데이터 수집 완료")
            return result

        except Exception as e:
            print(f"❌ 개별 종목 일봉 조회 오류 ({stock_code}): {e}")
            return {}

    def get_investor_trend(self, stock_code: str) -> Dict:
        """
        개별 종목 투자자별(외국인/기관/개인) 순매수 동향 조회 - StockAnalyzer 수급 25점
        연동용 【2026-08-24 신규, Phase 5-18】

        - API: 주식현재가 투자자(inquire-investor), tr_id FHKST01010900. 파일 상단
          변경이력 【2026-08-24】참고 - KIS 공식 GitHub 예제를 이 세션에서 직접
          fetch해서 확인한 필드명을 그대로 썼다. get_stock_daily_chart()와 달리
          날짜 범위를 넘기지 않는다(KIS가 최근 영업일분을 자체적으로 돌려줌).
        - 반환 단위: *_net_qty는 "주식 수"(부호 있음, 순매수 시 양수) - 단위가
          명확해서 market_intelligence/supply_demand.py가 이 필드만 쓴다.
          *_net_value("거래대금")는 참고용으로만 노출 - 단위(원/천원/백만원)를
          이 세션이 검증하지 못했으니 실제로 쓰기 전에 반드시 라이브 확인 필요.
        - 【주의】get_stock_daily_chart() 때와 동일하게, 이 세션은 실제 KIS API로
          응답 필드명을 검증할 수 없었다(클라우드 샌드박스 네트워크 제약) - 최초
          라이브 호출에서 필드명이 다르면(예: 필드가 output이 아니라 output1 등)
          빈 dict({})를 돌려주고 로그에 원인이 남으므로, main.py 실행 로그에서
          "데이터 없음"/"조회 실패"가 전종목에서 반복되면 이 메서드부터 의심할 것.
        """
        try:
            print(f"\n📊 개별 종목 투자자 매매동향 조회 중 ({stock_code})...")

            if not self.ensure_valid_token():
                return {}

            url = f"{self.base_url}/uapi/domestic-stock/v1/quotations/inquire-investor"

            headers = {
                "authorization": f"Bearer {self.access_token}",
                "appkey": self.api_key,
                "appsecret": self.api_secret,
                "tr_id": "FHKST01010900",  # 주식현재가 투자자
                "custtype": "P"
            }

            params = {
                "FID_COND_MRKT_DIV_CODE": "J",  # 【중요】J: 주식 (지수 전용 "U"와 다름)
                "FID_INPUT_ISCD": stock_code,
            }

            response = requests.get(
                url,
                headers=headers,
                params=params,
                verify=False,
                timeout=10
            )

            if response.status_code != 200:
                print(f"   ❌ 조회 실패! {stock_code} - {response.status_code}")
                return {}

            data = response.json()
            rt_cd = data.get('rt_cd', '0')
            if rt_cd != '0':
                print(f"   ❌ API 오류 ({stock_code}): {data.get('msg1', '')}")
                return {}

            output_list = data.get('output', [])
            if not output_list:
                print(f"   ℹ️  데이터 없음 ({stock_code})")
                return {}

            def _int_or_none(item, key):
                raw = item.get(key)
                if raw in (None, ''):
                    return None
                try:
                    return int(raw)
                except (TypeError, ValueError):
                    return None

            rows = []
            for item in output_list:
                date_val = item.get('stck_bsop_date', '')
                if not date_val:
                    continue
                rows.append({
                    "date": date_val,
                    "foreign_net_qty": _int_or_none(item, "frgn_ntby_qty"),
                    "institution_net_qty": _int_or_none(item, "orgn_ntby_qty"),
                    "individual_net_qty": _int_or_none(item, "prsn_ntby_qty"),
                    "foreign_net_value": _int_or_none(item, "frgn_ntby_tr_pbmn"),
                    "institution_net_value": _int_or_none(item, "orgn_ntby_tr_pbmn"),
                    "individual_net_value": _int_or_none(item, "prsn_ntby_tr_pbmn"),
                })

            # 날짜순(오래된 -> 최신) 정렬 - get_stock_daily_chart()와 동일한 관례
            rows.sort(key=lambda r: r["date"])

            result = {
                "symbol": stock_code,
                "dates": [r["date"] for r in rows],
                "foreign_net_qty": [r["foreign_net_qty"] for r in rows],
                "institution_net_qty": [r["institution_net_qty"] for r in rows],
                "individual_net_qty": [r["individual_net_qty"] for r in rows],
                "foreign_net_value": [r["foreign_net_value"] for r in rows],
                "institution_net_value": [r["institution_net_value"] for r in rows],
                "individual_net_value": [r["individual_net_value"] for r in rows],
            }

            print(f"   ✅ {stock_code}: {len(rows)}일 투자자 매매동향 수집 완료")
            return result

        except Exception as e:
            print(f"❌ 개별 종목 투자자 매매동향 조회 오류 ({stock_code}): {e}")
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

    def _split_account(self):
        """self.account("XXXXXXXX-XX" 또는 구분자 없는 10자리)를 KIS 주문/조회 API가
        요구하는 CANO(종합계좌번호 8자리)/ACNT_PRDT_CD(계좌상품코드 2자리)로 분리한다.

        형식이 둘 다 아니면(길이가 안 맞으면) 추측하지 않고 예외를 던진다 -
        잘못 분리된 계좌번호로 주문을 넣는 것보다 아예 실패하는 게 안전하다."""
        account = (self.account or "").strip()
        if "-" in account:
            cano, acnt_prdt_cd = account.split("-", 1)
        elif len(account) >= 10:
            cano, acnt_prdt_cd = account[:8], account[8:10]
        else:
            raise ValueError(
                f"계좌번호를 CANO(8자리)/ACNT_PRDT_CD(2자리)로 분리할 수 없습니다 "
                f"(길이={len(account)}, .env의 KIS_{'PROD' if self.environment=='production' else 'DEV'}_ACCOUNT_NUMBER 확인 필요)"
            )
        return cano, acnt_prdt_cd

    def place_order(
        self,
        stock_code: str,
        side: str,
        quantity: int,
        price: Optional[float] = None,
        order_type: str = "market",
    ) -> Dict:
        """
        국내주식 현금주문(매수/매도) - Phase 6-3 신규.

        - API: 주식주문(현금)(order-cash), tr_id 실전 TTTC0012U(매수)/TTTC0011U(매도),
          모의 VTTC0012U(매수)/VTTC0011U(매도) - KIS 공식 GitHub 예제(order_cash.py)를
          이 세션에서 직접 fetch해 확인한 그대로. 파일 상단 변경이력 【2026-08-26】참고.
        - order_type="market"(시장가, 기본값)이면 ORD_DVSN="01"/ORD_UNPR="0"이고 price는
          무시된다. order_type="limit"(지정가)이면 ORD_DVSN="00"이고 price가 필수다.
          "완전 자동" 매매 결정(AskUserQuestion에서 사용자가 확정)이라 즉시 체결을
          우선하는 시장가를 기본값으로 뒀다 - 지정가가 필요하면 order_type="limit"로
          호출.

        Args:
            stock_code: 종목코드(6자리)
            side: "buy"(매수) | "sell"(매도)
            quantity: 주문 수량(1주 이상)
            price: 지정가 주문 시 1주당 가격(원). 시장가면 무시.
            order_type: "market"(시장가, 기본) | "limit"(지정가)

        Returns:
            성공 시 {"success": True, "order_no": "0000041289"(ODNO), "order_time": "091359"(ORD_TMD),
            "org_no": "91252"(KRX_FWDG_ORD_ORGNO), "message": ..., "raw": output}
            실패 시(검증 실패/API 오류/예외) {"success": False, "message": "...", "raw": ...(있으면)}
            - 이 메서드는 절대 예외를 밖으로 던지지 않는다(호출부인 파이프라인이
            매번 try/except를 감쌀 필요 없이 success 플래그만 보면 되도록).
        """
        try:
            if side not in ("buy", "sell"):
                return {"success": False, "message": f"side는 'buy' 또는 'sell'이어야 합니다(받은 값: {side!r})"}
            if order_type not in ("market", "limit"):
                return {"success": False, "message": f"order_type은 'market' 또는 'limit'이어야 합니다(받은 값: {order_type!r})"}
            if quantity is None or quantity <= 0:
                return {"success": False, "message": f"quantity는 1 이상이어야 합니다(받은 값: {quantity!r})"}
            if order_type == "limit" and (price is None or price <= 0):
                return {"success": False, "message": "지정가(limit) 주문은 price가 필요합니다(1 이상)"}
            if not stock_code:
                return {"success": False, "message": "stock_code가 비어 있습니다"}

            if not self.ensure_valid_token():
                return {"success": False, "message": "KIS 토큰 발급 실패"}

            cano, acnt_prdt_cd = self._split_account()

            if self.environment == "production":
                tr_id = "TTTC0012U" if side == "buy" else "TTTC0011U"
            else:
                tr_id = "VTTC0012U" if side == "buy" else "VTTC0011U"

            ord_dvsn = "01" if order_type == "market" else "00"
            ord_unpr = "0" if order_type == "market" else str(int(price))

            url = f"{self.base_url}/uapi/domestic-stock/v1/trading/order-cash"
            headers = {
                "authorization": f"Bearer {self.access_token}",
                "appkey": self.api_key,
                "appsecret": self.api_secret,
                "tr_id": tr_id,
                "custtype": "P",
            }
            body = {
                "CANO": cano,
                "ACNT_PRDT_CD": acnt_prdt_cd,
                "PDNO": stock_code,
                "ORD_DVSN": ord_dvsn,
                "ORD_QTY": str(int(quantity)),
                "ORD_UNPR": ord_unpr,
                "EXCG_ID_DVSN_CD": "KRX",
            }

            side_label = "매수" if side == "buy" else "매도"
            print(f"\n📝 주문 실행 ({side_label}, {order_type}): {stock_code} {quantity}주"
                  f"{f' @ {price}원' if order_type == 'limit' else ''}")

            response = requests.post(url, headers=headers, json=body, verify=False, timeout=10)
            data = response.json()
            rt_cd = data.get("rt_cd", "1")

            if response.status_code == 200 and rt_cd == "0":
                output = data.get("output", {})
                result = {
                    "success": True,
                    "order_no": output.get("ODNO"),
                    "order_time": output.get("ORD_TMD"),
                    "org_no": output.get("KRX_FWDG_ORD_ORGNO"),
                    "message": data.get("msg1", ""),
                    "raw": output,
                }
                print(f"   ✅ 주문 접수 완료 - 주문번호: {result['order_no']}")
                return result
            else:
                message = data.get("msg1", f"HTTP {response.status_code}")
                print(f"   ❌ 주문 실패: {message}")
                return {"success": False, "message": message, "raw": data}

        except Exception as e:
            print(f"❌ 주문 실행 오류: {e}")
            import traceback
            traceback.print_exc()
            return {"success": False, "message": str(e)}

    def get_balance(self) -> Dict:
        """
        계좌 잔고조회(보유종목 + 예수금) - Phase 6-3 신규.

        - API: 주식잔고조회(inquire-balance), tr_id 실전 TTTC8434R / 모의 VTTC8434R -
          KIS 공식 GitHub 예제(inquire_balance.py)를 그대로 확인. INQR_DVSN="02"(종목별),
          UNPR_DVSN="01", FUND_STTL_ICLD_YN="N", FNCG_AMT_AUTO_RDPT_YN="N",
          PRCS_DVSN="01"(당일 매매 포함 조회)로 고정 - 예제의 필수 파라미터 이름은
          맞지만 이 세션이 실제로 어떤 조합이 "정상 동작"인지 확인 못 했다(공식
          예제도 호출부가 값을 넘기게만 돼 있고 권장값을 명시하지 않음) - 실전 첫
          호출에서 빈 결과가 나오면 이 값들부터 의심할 것.
        - 페이지네이션(50건/20건 초과 시 연속조회)은 아직 구현 안 함 - 700만원
          계좌 + 최대 7종목(TradingConfig.max_positions) 설계라 한 번의 호출로
          충분할 것으로 보이지만, 보유 종목이 늘어나면 다음 단계에서 추가 필요.
        - 【응답 필드명 미검증 - 반드시 라이브 확인】파일 상단 변경이력 【2026-08-26】
          참고. 그래서 raw_output1/raw_output2에 API 원본 응답을 그대로 포함해
          반환한다.

        Returns:
            {"positions": [{"ticker":, "name":, "quantity":, "orderable_quantity":,
              "average_price":, "current_price":, "evaluation_amount":,
              "profit_loss_amount":, "profit_loss_rate":}, ...]  (quantity<=0인 행은
              "당일 전량매도" 잔재이므로 제외),
             "cash": {"cash_balance":(예수금총금액), "total_evaluation_amount":(총평가금액)},
             "raw_output1": [...], "raw_output2": [...]}
            실패 시 {}
        """
        try:
            if not self.ensure_valid_token():
                return {}

            cano, acnt_prdt_cd = self._split_account()
            tr_id = "TTTC8434R" if self.environment == "production" else "VTTC8434R"

            url = f"{self.base_url}/uapi/domestic-stock/v1/trading/inquire-balance"
            headers = {
                "authorization": f"Bearer {self.access_token}",
                "appkey": self.api_key,
                "appsecret": self.api_secret,
                "tr_id": tr_id,
                "custtype": "P",
            }
            params = {
                "CANO": cano,
                "ACNT_PRDT_CD": acnt_prdt_cd,
                "AFHR_FLPR_YN": "N",
                "OFL_YN": "",
                "INQR_DVSN": "02",
                "UNPR_DVSN": "01",
                "FUND_STTL_ICLD_YN": "N",
                "FNCG_AMT_AUTO_RDPT_YN": "N",
                "PRCS_DVSN": "01",
                "CTX_AREA_FK100": "",
                "CTX_AREA_NK100": "",
            }

            print("\n💰 계좌 잔고조회 중...")
            response = requests.get(url, headers=headers, params=params, verify=False, timeout=10)

            if response.status_code != 200:
                print(f"   ❌ 조회 실패! {response.status_code}")
                return {}

            data = response.json()
            if data.get("rt_cd", "1") != "0":
                print(f"   ❌ API 오류: {data.get('msg1', '')}")
                return {}

            output1 = data.get("output1", []) or []
            output2 = data.get("output2", [{}]) or [{}]

            def _f(value, default=0.0):
                try:
                    return float(value)
                except (TypeError, ValueError):
                    return default

            def _i(value, default=0):
                try:
                    return int(value)
                except (TypeError, ValueError):
                    return default

            positions = []
            for item in output1:
                qty = _i(item.get("hldg_qty"))
                if qty <= 0:
                    continue
                positions.append({
                    "ticker": item.get("pdno"),
                    "name": item.get("prdt_name"),
                    "quantity": qty,
                    "orderable_quantity": _i(item.get("ord_psbl_qty")),
                    "average_price": _f(item.get("pchs_avg_pric")),
                    "current_price": _f(item.get("prpr")),
                    "evaluation_amount": _f(item.get("evlu_amt")),
                    "profit_loss_amount": _f(item.get("evlu_pfls_amt")),
                    "profit_loss_rate": _f(item.get("evlu_pfls_rt")),
                })

            summary = output2[0] if output2 else {}
            cash = {
                "cash_balance": _f(summary.get("dnca_tot_amt")),
                "total_evaluation_amount": _f(summary.get("tot_evlu_amt")),
            }

            print(f"   ✅ 보유 {len(positions)}종목, 예수금 {cash['cash_balance']:,.0f}원")
            return {"positions": positions, "cash": cash, "raw_output1": output1, "raw_output2": output2}

        except Exception as e:
            print(f"❌ 잔고조회 오류: {e}")
            import traceback
            traceback.print_exc()
            return {}

    def get_pending_orders(self) -> List[Dict]:
        """
        정정취소가능주문조회(미체결/취소가능 주문 목록) - Phase 6-3 신규.

        - API: inquire-psbl-rvsecncl, tr_id 실전 TTTC0084R - KIS 공식 GitHub 예제로
          확인. 모의투자 tr_id(VTTC0084R)는 예제에 명시가 없어서, kis_auth.py의
          _url_fetch()가 실제로 쓰는 "tr_id 첫 글자 T/J/C를 모의투자 시 V로 치환"
          규칙을 그대로 적용해 추정했다(place_order/get_balance는 공식 예제로
          모의 tr_id까지 직접 확인됨 - 이 메서드만 추정 - 파일 상단 변경이력
          【2026-08-26】참고). INQR_DVSN_1="0"(주문 전체), INQR_DVSN_2="0"(전체,
          매도/매수 구분 없음)으로 고정.
        - 【응답 필드명 미검증】get_balance()와 동일한 한계 - 각 항목의 "raw"에
          API 원본을 그대로 포함해 반환한다.

        Returns:
            [{"order_no":(odno), "ticker":(pdno), "raw": {...API 원본...}}, ...]
            실패 시 빈 리스트.
        """
        try:
            if not self.ensure_valid_token():
                return []

            cano, acnt_prdt_cd = self._split_account()
            tr_id = "TTTC0084R" if self.environment == "production" else "VTTC0084R"

            url = f"{self.base_url}/uapi/domestic-stock/v1/trading/inquire-psbl-rvsecncl"
            headers = {
                "authorization": f"Bearer {self.access_token}",
                "appkey": self.api_key,
                "appsecret": self.api_secret,
                "tr_id": tr_id,
                "custtype": "P",
            }
            params = {
                "CANO": cano,
                "ACNT_PRDT_CD": acnt_prdt_cd,
                "INQR_DVSN_1": "0",
                "INQR_DVSN_2": "0",
                "CTX_AREA_FK100": "",
                "CTX_AREA_NK100": "",
            }

            print("\n📋 미체결(정정취소가능) 주문 조회 중...")
            response = requests.get(url, headers=headers, params=params, verify=False, timeout=10)

            if response.status_code != 200:
                print(f"   ❌ 조회 실패! {response.status_code}")
                return []

            data = response.json()
            if data.get("rt_cd", "1") != "0":
                print(f"   ❌ API 오류: {data.get('msg1', '')}")
                return []

            output = data.get("output", []) or []
            orders = [{"order_no": item.get("odno"), "ticker": item.get("pdno"), "raw": item} for item in output]
            print(f"   ✅ 미체결 주문 {len(orders)}건")
            return orders

        except Exception as e:
            print(f"❌ 미체결 주문 조회 오류: {e}")
            import traceback
            traceback.print_exc()
            return []

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