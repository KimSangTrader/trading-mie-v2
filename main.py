"""
MIE V2.0 메인 실행 스크립트

================================================================================
【변경 이력】
================================================================================
(초기 버전 - 변경이력 없이 존재하던 상태) KOSPI 지수 단일 파이프라인으로만 동작.
IntelligenceManager에 7개 분석기(Market/Sector/MoneyFlow/Theme/News/Technical/
Valuation)를 등록하고, market_data 대부분(섹터/수급/테마/뉴스/기술 지표)을
하드코딩된 모의값으로 채운 뒤 symbol="0001" 자리표시자로 단 한 번만 분석을
실행했다. ValuationAnalyzer 입력값(per/pbr/dividend_yield 등)도 전부 모의값
(per=12.0 등)이었다 - 실제 종목 데이터를 쓰지 않았음.

【2026-08-18】종목별 루프로 확장 (Phase 5-9)
- 배경: Phase 5-7/5-8을 거치며 stock_valuation 테이블(RDS)에 KOSPI/KOSDAQ
  2,718종목의 실제 PER/PBR/배당수익률 + 시장 중앙값 대비 상대점수가 매일 쌓이게
  됐다. main.py가 아직도 종목 하나를 자리표시자로 흉내내고 있는 건 이 실데이터를
  전혀 활용하지 못하는 것이므로, 이번에 실제 종목별로 분석을 도는 구조로 바꿨다.
- 조사 결과(서브에이전트로 IntelligenceManager/CombinedAnalyzer 3종/analyzer들의
  실제 계약을 확인함):
  * IntelligenceManager.run_all()은 순수 dict-in/dict-out이라 종목이 바뀔 때마다
    새 market_data로 반복 호출해도 문제없음(상태는 last_results/last_run_time
    뿐이고, 그건 루프 안에서 매번 결과를 따로 수집하면 됨).
  * combined_analyzer.py / combined_analyzer_improved.py / advanced_combined_analyzer.py
    3개는 전부 실제로 아무 데서도(main.py 포함) 쓰이지 않는 죽은 코드였음
    (각자의 __main__ 자체 테스트와 테스트 파일의 docstring 언급 정도뿐). 이번
    작업 범위에서는 건드리지 않았다 - 삭제 여부는 별도 판단 필요(정리 과제로 남김).
  * Market/Sector/MoneyFlow/Theme/News 5개 분석기는 데이터 형태상 "시장 전체"
    단위이지 종목별로 다른 값을 줄 근거가 아직 없다(예: SectorAnalyzer는 업종
    지수 몇 개를 고정 키로 받지, 종목별 업종 강도를 계산하는 구조가 아님).
    TechnicalAnalyzer만 OHLCV를 받는 구조라 종목별로 다를 수 있지만, 종목별
    OHLCV 수집은 이번 작업 범위 밖이라 일단 이 5개+Technical은 실행마다 동일한
    "시장 공통 데이터"를 그대로 쓰고, ValuationAnalyzer만 종목별로 실데이터를
    갈아끼운다. 이건 임시방편이 아니라 Phase 5 방향 보고서의 설계 의도와도
    맞는다("KOSPI/KOSDAQ 중앙값 절대 안 섞는" 것처럼 시장 공통 요인과 종목
    고유 요인을 분리하는 것과 같은 원칙).
  * stock_valuation 테이블에 market_per/market_pbr/market_dividend_yield가
    이미 계산되어 저장돼 있으므로, 굳이 MarketValuation.calculate_medians()를
    다시 돌릴 필요 없이 그 컬럼을 그대로 읽어 쓰면 된다.
- get_real_market_data()/analyze_sentiment()는 그대로 두고, merge_market_data()
  는 "시장 공통 데이터만" 만들도록 정리(종목별 ValuationAnalyzer 자리표시자 필드
  제거) - 종목별 값은 get_latest_stock_valuations()로 DB에서 읽어와 매 루프마다
  덮어씌운다.
- 안전을 위한 기본값: valuation_pipeline.py와 동일한 관례로, 인자 없이 실행하면
  앞쪽 20종목만 처리하고, 'all' 인자를 줘야 전체(2,718종목)를 처리한다.
- 기존에 있던 "외국인 8,590억 순매도" 같은 하드코딩된 서술형 출력은 애초에
  모의 숫자를 설명하는 가짜 문장이었으므로(실제 분석 결과가 아님) 제거하고,
  실제로 분석된 종목들의 점수 요약 표(평균/최고/최저, 상위·하위 10종목)로
  교체했다.
- 이 세션은 실제 RDS에 접속해 검증할 수 없었다(클라우드 샌드박스 네트워크
  제약) - 사용자 컴퓨터에서 python main.py(시험, 20종목) 및 python main.py all
  (전체)로 라이브 검증 필요.

【2026-08-21】상시 서비스화 - 일마감 분석 스케줄러 + KISClient 토큰 재사용 (Phase 5-10)
- 배경: mie-v2.service(systemd)가 8/7부터 계속 죽어있던 게 발견됨 - 원인은
  main.py가 "1회 실행 후 종료"하는 스크립트인데 서비스는 Restart=always/
  RestartSec=10으로 설정돼 있어서, 실행이 끝날 때마다 계속 재시작하다가
  60초 안에 3번(StartLimitBurst=3) 재시작 → systemd의 start-limit-hit에
  걸려 완전히 멈춘 것이었다(사용자 확인: "이전 무중단 시스템도 마찬가지").
- 사용자 결정 사항(대화로 확정):
  * 상시 프로세스로 계속 떠있으면서(A안), 그 안에서 자체적으로 일정을
    관리하는 방식을 선택함 (systemd timer 같은 외부 스케줄러 대신).
  * 한국 주식 "일마감 분석"(전종목 스크리닝)은 평일 KST 19:00에 하루
    한 번만 실행(2026-09-14: 한국 주식시장 거래시간 변경에 따라 22:00로
    조정 - 아래 【2026-09-14】 항목 참고) - 실시간 매수/매도 자동주문
    루프(별도 프로세스, 이번
    범위 아님 - "지금은 일마감 분석을 고도화 하는 단계이니 실제 대상건의
    매입/매도는 분석작업이 완료된 이후 진행하자")와는 완전히 분리된
    별개 프로세스. 최종적으로는 두 프로세스가 하나의 "무중단 자동매매
    시스템" 안에서 각자 돌아가는 구조를 목표로 함 - 이번 세션에서는
    ①(일마감 분석)만 구현하고 ②(실시간 매매/실주문)는 건드리지 않음.
  * KIS 토큰 재발급 주기: 22시간(실제 만료 24시간보다 2시간 여유) -
    data/kis_client.py에 ensure_valid_token() 신규 추가, KISClient
    인스턴스를 프로세스 시작 시 1개만 만들어 MarketAnalyzer/
    TechnicalAnalyzer/get_real_market_data()가 공유(예전엔 이 셋이
    각자 별도 KISClient를 만들어 사이클마다 토큰을 3번씩 새로 받았음).
  * 재기동(다운타임 후) 복구 로직: data/state/main_run_state.json에
    마지막 완료 날짜를 기록해두고, (a) 오늘 아직 미완료 + 이미 목표
    시각이 지났으면 즉시 실행, (b) 어제치도 없이 하루 이상 밀렸으면 시각과
    무관하게 즉시 실행(따라잡기), (c) 오늘 이미 완료면 다음날까지 대기.
  * 주말(토/일)은 건너뜀 - KRX 공휴일까지는 아직 처리 못함(알려진 한계,
    추후 과제).
- 기존 CLI 동작은 100% 유지: 인자 없이 `python main.py` → 시험(20종목,
  1회 실행 후 종료), `python main.py all` → 전체(1회 실행 후 종료).
  신규 `python main.py serve` → 상시 서비스 모드(이번에 추가, systemd가
  이걸 실행하도록 mie-v2.service의 ExecStart를 변경해야 함).
- 이 세션은 다시 한 번 실제 RDS/KIS API로 라이브 검증할 수 없었다(클라우드
  샌드박스 네트워크 제약, 게다가 시각 의존 로직이라 사용자 컴퓨터/서버에서
  날짜를 앞뒤로 바꿔가며 시나리오별로 확인이 필요함) - 사용자 컴퓨터에서
  단위 테스트 + 서버에서 실제 배포 후 라이브 검증 필요.

【2026-08-22】TechnicalAnalyzer 실데이터 연동 - 매 종목 조용히 스킵되던 문제 수정 (Phase 5-11)
- 배경: EC2에 배포한 serve 모드를 라이브 검증하던 중(실제로는 오늘이 토요일이라
  주말 스킵 로직이 정상 동작해 대기 중이었던 것으로 확인됨 - 별도 이슈 아님),
  전체 2,718종목 규모로 `python main.py all`을 수동 실행해 확인하는 과정에서
  `technical: validate=False`가 종목 수만큼(시험 20회) 찍히는 걸 발견함.
  IntelligenceManager.run_all()이 validate 실패한 분석기를 에러 없이 조용히
  건너뛰고 나머지로만 점수를 계산하는 구조라서(success_count/fail_count는
  기록하지만 전체 success는 그대로 True), 지금까지 결과가 정상으로만 보였음 -
  실제로는 TechnicalAnalyzer(가중치 0.18)가 처음부터 한 번도 반영된 적이 없었음.
- 원인: TechnicalAnalyzer.validate()/analyze()는 closes/opens/highs/lows/volumes
  (60개 이상 캔들)를 요구하는데, build_shared_market_data()가 채우는 건
  macd_value/rsi_value/bb_upper 같은 전혀 다른 모양의 모의값이었음 - 애초에
  두 쪽이 서로 안 맞는 상태로 8/18일 종목별 루프 확장 때 그대로 넘어감.
- 조사 결과: data/kis_client.py에 개별 종목(FID_COND_MRKT_DIV_CODE="J")용
  일봉 조회 메서드가 아예 없었음 - 기존 get_daily_price()/get_daily_chart()는
  지수(KOSPI/KOSDAQ, "U") 전용이라 개별 종목 코드로는 쓸 수 없음.
- 조치: data/kis_client.py에 get_stock_daily_chart(stock_code, days=60) 신규
  추가(국내주식기간별시세 API, tr_id=FHKST03010100, 종목당 호출 1번으로 60일치
  획득). analyze_stock()이 종목별 루프 안에서 이걸 호출해 closes/opens/highs/
  lows/volumes를 채우도록 수정 - 조회 실패해도(신규상장 등) technical만
  스킵되고 나머지 6개 분석기는 그대로 진행(기존 "한 종목 실패가 전체를 막지
  않는다" 원칙 유지). rate limit은 valuation_collector.py의 기존 관례(0.2초)를
  그대로 따름.
- 영향: 종목별 루프에 API 호출이 추가되면서 전체(all) 실행 시간이 기존
  "몇 초"에서 "최소 수 분~십수 분"(2,718종목 × 0.2초 + 네트워크 왕복)으로
  늘어남 - 하루 한 번(19시) 배치라 문제는 없으나, 이전에 관찰한 "순식간에
  끝난다"는 더 이상 해당하지 않게 됨. 시험 모드(20종목)는 여전히 몇 초 수준.
- 이 세션은 이번에도 실제 KIS API로 get_stock_daily_chart()의 응답 필드명을
  검증할 수 없었다(클라우드 샌드박스 네트워크 제약) - kis_client.py 변경이력에
  적어둔 대로, 반드시 종목 1~2개 소규모로 먼저 실제 호출해 필드가 맞는지
  확인 후 시험(20종목) → 전체(all) 순서로 라이브 검증 필요.

【2026-08-23】계층형 순위(시장→Sector→Theme→종목) 배선 (Phase 5-17)
- 배경: docs/hierarchical_scoring_plan.md Phase 1~4에서 만든 계산 로직/파이프라인
  (SectorAnalyzer/ThemeAnalyzer 실계산, StockAnalyzer, hierarchical_ranker,
  price_history_pipeline, hierarchical_ranking_pipeline)이 지금까지 main.py와는
  전혀 연결되지 않은 채 SQLite 단위테스트로만 검증돼 있었다. 사용자가 "최종
  결합도 문서의 계층형 공식으로 전면 교체"를 명시적으로 결정해서(IntelligenceManager.
  run_all()의 flat 7-analyzer 가중평균을 버리는 것까지 포함) 이번에 실제 배선했다.
- 배선 방식:
  1) 종목별 루프(analyze_stock)가 TechnicalAnalyzer용으로 이미 종목마다
     kis_client.get_stock_daily_chart()를 호출하고 있었다. 이 chart 응답을
     data/price_history_collector.py의 chart_to_price_rows()로 바로 stock_price_
     history 행 형식으로 변환해 루프 밖 price_rows 리스트에 누적한다 - Sector/
     Theme/일봉 저장을 위해 API를 또 호출하지 않는다(종목당 호출 2배 방지).
  2) 루프가 끝나면 그 price_rows를 market_intelligence/collectors/
     price_history_pipeline.py의 run_full_price_history_pipeline(records=...)로
     DB(stock_price_history)에 저장한다 - 신규 records 파라미터로 collector/API를
     건너뛴다.
  3) 저장이 끝난 뒤(DB가 최신 상태가 된 뒤) run_hierarchical_ranking_pipeline()을
     price_history=None으로 호출한다 - 방금 커밋한 DB를 그대로 다시 읽게 해서,
     시험(20종목) 실행이어도 이전에 쌓인 전체 종목 히스토리가 있으면 그걸 함께
     활용하도록 했다(이번 루프에서 모은 20종목분만으로 Sector/Theme 바스켓을
     좁게 계산하는 것보다 낫다). market_regime_scores는 real_data의
     kospi_change_rate/kosdaq_change_rate(KISClient.get_kospi_kosdaq())로 계산.
     valuation_by_ticker는 Step 5에서 이미 조회해둔 stock_rows를 그대로 재사용.
  4) IntelligenceManager 등록 분석기에서 SectorAnalyzer/ThemeAnalyzer를 제거했다
     (setup_manager_and_client() 참고) - 이 두 analyzer는 이제 "종목별 market_data"
     계약이 아니라 "전체 종목 price_history+mapping" 계약으로 완전히 바뀌었는데
     (Phase 2), 옛 계약(shared_data의 IT_Semiconductor=1425 같은 고정 키)으로 계속
     등록해두면 validate()가 항상 실패해 매 종목·매 사이클 조용히 스킵되기만
     한다 - 이건 Phase 5-11에서 TechnicalAnalyzer가 겪었던 것과 정확히 같은
     종류의 버그라 반복하지 않기로 했다. 대신 이 둘은 run_hierarchical_ranking_
     pipeline() 안에서 전체 종목 단위로 딱 한 번씩만 실행된다.
  5) 결과 요약(Step 8, 신규)은 stock_hierarchical_scores에서 방금 저장한 배치를
     다시 읽어(get_latest_hierarchical_scores) 계층형 final_score 기준 상위/하위
     10종목을 보여준다. 기존 flat 요약(Step 7)은 개별 분석기 참고/디버깅용으로
     그대로 남겨뒀다(문서 9절 "여러 순위 동시 제공" 권고와 일치).
- 이 세션은 실제 RDS/KIS API에 접근할 수 없어(클라우드 샌드박스 네트워크 제약)
  이번 배선 역시 라이브 검증하지 못했다 - 사용자 컴퓨터에서 소규모(시험 20종목)
  실행으로 먼저 확인 후 전체(all)로 진행 필요. 특히 확인이 필요한 부분:
  * get_stock_daily_chart()의 dates/opens/highs/lows/closes/volumes 필드명이
    실제 응답과 맞는지(기존부터 있던 미검증 가정, Phase 5-11 참고)
  * get_kospi_kosdaq()의 kospi_change_rate/kosdaq_change_rate 필드가 실제로
    채워지는지(0이면 market_score가 항상 중립 50으로 나옴 - 에러는 아니지만
    시장 레벨 신호가 사실상 꺼진 것과 같으므로 로그로 확인 필요)
  * stock_sector_mapping/stock_theme_mapping이 비어있으면(아직 sector_theme_
    importer.py를 한 번도 안 돌렸으면) 계층형 순위 자체가 전부 빈 결과로 나옴
    (Step 8이 경고 로그만 남기고 조용히 건너뜀 - 에러 아님)

【2026-08-24】Phase 5-17 전체 종목(2,718개) 라이브 검증 완료 + Phase 5-18 착수 (수급 데이터 연동)
- 사용자가 `python main.py all`로 전체 유니버스를 실행해 확인함: 2,718종목 flat 분석
  성공, 그중 2,602종목이 계층형 순위까지 저장됨(Sector 11개/Theme 18개 집계), Step 8까지
  에러 없이 완주. Phase 5-17(main.py 실배선)은 이걸로 완전히 마무리됐다(자세한 내용은
  docs/hierarchical_scoring_plan.md Phase 5 항목 참고).
- 실행 결과 관찰(버그는 아니지만 기록해 둠): Step 8 상위/하위 10종목 표에 Sector/Theme가
  "결측"으로 나오는 비중이 눈에 띄게 높다. 원인은 데이터 누락이라기보다 선택 효과로
  보인다 - Sector/Theme가 결측인 종목은 renormalize_to_100()이 market(10%)+stock(50%)
  단 두 레벨만으로 재정규화하면서 stock_score(그 자체가 분산이 큰 값) 비중이
  50/60≈83%까지 커져, 최종 점수의 분산도 커진다. 즉 결측 종목이 상/하위 극단에 더 잘
  뜨는 구조적 경향이 있다 - 사용자에게 보고했고, 지금 당장 고칠 버그로 보지 않아 이
  세션은 손대지 않았다(재정규화 자체가 의도된 결측 처리 원칙이므로). 나중에 순위표를
  다듬을 때(예: 결측 레벨이 많은 종목은 순위 밖으로 빼거나 별도 표시) 참고할 것.
- 사용자가 "순서대로 진행하자"고 지시한 백로그의 첫 항목 착수: 종목별 외국인/기관
  순매수 데이터 연동(StockAnalyzer의 수급 25점 컴포넌트, 지금까지 결측 고정).
  data/kis_client.py.get_investor_trend() 신규 + market_intelligence/supply_demand.py
  (순수 계산기) 신규 + 아래 analyze_stock()/run_analysis_cycle() 수정으로 배선.
  종목별 API 호출이 1회(일봉) → 2회(일봉+투자자매매동향)로 늘어 전체 종목 기준
  예상 소요 시간이 약 2배가 된다(Step 6 로그 안내 문구도 같이 갱신함).
- Phase 5-18 시험(20종목)/전체(2,718종목) 라이브 검증 모두 완료(사용자 실행 로그로
  확인) - get_investor_trend()의 tr_id/필드명이 실제 KIS 응답과 맞았고, flat
  2,718/2,602종목 저장 건수가 Phase 5-17과 정확히 일치해 실패 종목이 늘지 않았다.
  "데이터 없음"/"조회 실패" 건수를 로그 파일로 별도 카운트하지는 못했지만(콘솔
  로그를 파일로 남기지 않음), 종목별 실패가 전체를 막지 않는 구조 + 저장 건수
  불변이라는 두 근거로 충분하다고 판단해 Phase 5-18을 완료 처리했다. 이걸로
  사용자가 지시한 순서의 1번(수급 데이터 연동)이 끝났다.

【2026-08-24】Phase 5-19: Sector별 밸류에이션 중앙값 계산 (백로그 2번)
- market_intelligence/analyzers/stock_analyzer.py는 애초부터 `data["sector_per_median"]`
  등이 주어지면 우선 쓰고 없으면 market_per로 자동 대체하도록 설계돼 있었다(Phase 3
  "알려진 한계 2") - 소비 측 계약은 이미 있었고, 생산 측(market_valuation.py/
  valuation_pipeline.py)이 실제 Sector 중앙값을 계산해 채워주지 않고 있었을 뿐이다.
  이번 변경은 그 생산 측만 채운다 - stock_analyzer.py는 전혀 건드리지 않았다.
- market_intelligence/market_valuation.py: calculate_medians()에 group_by 파라미터
  추가("market"→"sector"로도 그룹핑 가능, 하위 호환 유지) + 지표별 유효 표본 수
  노출(*_valid_count) + build_relative_baseline() 신규(PER/PBR/배당 각각 독립적으로
  "Sector 표본이 충분하면 Sector 중앙값, 아니면 시장 전체 중앙값" 선택).
- market_intelligence/collectors/valuation_pipeline.py: data/sector_theme_importer.
  get_latest_sector_mapping()으로 종목별 Sector를 조회해 Sector 중앙값도 함께 계산하고,
  build_relative_baseline()으로 고른 기준값을 이 파이프라인 자체의 ValuationAnalyzer
  호출에도 반영(Step 7 flat 참고 표와 Step 8 계층형이 서로 다른 기준값을 쓰는 혼란
  방지). db/models.py StockValuation에 sector/sector_per_median/sector_pbr_median/
  sector_dividend_median 4개 컬럼 신규(전부 nullable, 기존 market_per 등 컬럼 의미는
  안 바꿈).
- get_latest_stock_valuations()도 이번에 같이 수정: DB의 sector_per_median 등이 NULL이면
  결과 dict에 그 키 자체를 아예 넣지 않는다(값을 None으로 넣지 않음) - dict.get(key,
  default)는 "키가 없을 때만" default를 쓰므로, 키를 넣어버리면 표본 부족으로 정당하게
  시장 중앙값으로 대체돼야 하는 종목이 오히려 밸류에이션 기준값을 통째로 잃는 버그가
  된다(자세한 이유는 해당 함수 docstring 참고).
- ⚠️ 기존 stock_valuation 테이블이 이미 실제 RDS에 존재해서 create_tables.py
  (Base.metadata.create_all())로는 새 컬럼이 추가되지 않는다 - 1회성
  migrate_add_sector_valuation_columns.py를 신규로 만들었다(ALTER TABLE ADD COLUMN
  IF NOT EXISTS, 여러 번 실행해도 안전). **사용자 컴퓨터에서 python
  migrate_add_sector_valuation_columns.py를 먼저 실행해야** 그다음 valuation_pipeline.py
  실행 시 새 컬럼에 실제로 값이 채워진다 - 순서를 안 지키면(마이그레이션 전에
  파이프라인부터 돌리면) INSERT가 "column does not exist" 에러로 실패한다.
- 이 세션은 실제 RDS/KIS API에 접근할 수 없어 SQLite 단위테스트로만 검증했다
  (tests/test_market_valuation.py, tests/test_valuation_pipeline.py 확장). 사용자
  컴퓨터에서 확인 순서: (1) migrate_add_sector_valuation_columns.py 실행 (2) pytest
  tests/test_market_valuation.py tests/test_valuation_pipeline.py -v (3)
  valuation_pipeline.py를 한 번 돌려 stock_valuation에 sector_per_median 등이 실제로
  채워지는지 (4) python main.py(시험)로 Step 8 밸류에이션 컴포넌트가 여전히 정상
  범위인지.

【2026-09-14】일마감 분석 목표 시각 19:00 -> 22:00(KST) 변경
- 배경: 한국 주식시장 거래시간이 변경되었다는 사용자 고지에 따라, 일마감
  분석(전종목 스크리닝)을 시작하는 목표 시각을 평일 KST 19:00에서 22:00로
  조정한다. 이 시각 값(19:00, 22:00 모두)은 코드가 임의로 정한 게 아니라
  전부 사용자 지정값이다.
- 변경: _DAILY_RUN_HOUR을 19 -> 22로 변경(_DAILY_RUN_MINUTE=0은 그대로).
  _should_run_now()/run_forever() 등 이 상수를 참조하는 로직 자체는 값만
  바뀔 뿐 그대로 동작(다운타임 후 따라잡기 로직, 주말 스킵 등 변경 없음).
- ⚠️ 후속 확인 필요(이번 변경에서는 건드리지 않음): (1)
  deploy/mie-v2-sector-theme-tracker.timer(현재 22:30 UTC = 07:30 KST 실행)가
  분석 시작 시각이 늦춰진 뒤에도 분석 완료 이후 & 09:05 KST 매매집행 이전이라는
  여유를 여전히 확보하는지 재검토 필요 (2)
  mie-v2-trade-execution.service/.timer의 09:05 KST 실행 시각이 22:00 KST
  시작 기준으로도 분석이 안정적으로 먼저 끝나는지 재검토 필요(과거 완료
  소요시간은 정상 시 2시간 이내~수 시간, OOM 장애 시기엔 24시간 이상 걸린
  전례가 있어 여유가 빠듯할 수 있음).
================================================================================
"""

import json
import logging
import signal
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

# 【2026-08-22 추가, Phase 5-11 라이브 검증 중 발견】stdout/stderr을 UTF-8로 강제한다.
# 이 파일과 data/kis_client.py 곳곳에서 ✅/❌/⚠️/📊 등 이모지를 print()/logger로
# 찍는데, Windows에서 콘솔에 직접 출력할 땐 문제없다가도 파이프(`| Select-String`
# 등)나 파일 리다이렉트로 연결하는 순간 파이썬이 출력 인코딩을 시스템 기본
# 코드페이지(한국어 Windows는 cp949)로 잡아버려서 "'cp949' codec can't encode
# character '✅'..." UnicodeEncodeError로 죽는다. 이게 KISClient() 생성자
# 안(__init__의 print)에서 터지면 setup_manager_and_client()의 try/except가
# 조용히 삼켜서 kis_client=None(Mock 모드)으로 빠지고, 기술지표 조회 자체가
# 시도조차 안 된 채로 "정상 종료"돼버린다 - 실제로 EC2/서버는 리눅스(기본 UTF-8)라
# 안 겪었지만, 로컬 Windows에서 로그를 파일로 남기거나 파이프로 필터링할 때마다
# 재현되므로 여기서 근본적으로 고쳐둔다. reconfigure()가 없는 아주 오래된 파이썬
# 이거나 이미 재구성 불가능한 스트림이면 조용히 무시(Linux 서버는 원래 UTF-8이라
# 이 블록이 사실상 아무 영향 없음).
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

from market_intelligence.intelligence_manager import IntelligenceManager
from market_intelligence.analyzers import (
    MarketAnalyzer,
    MoneyFlowAnalyzer,
    TechnicalAnalyzer,
    ValuationAnalyzer
)
from data.kis_client import KISClient
# 【2026-08-23 추가, Phase 5-17】계층형 순위(시장→Sector→Theme→종목) 배선.
# SectorAnalyzer/ThemeAnalyzer는 더 이상 여기서 직접 등록/호출하지 않는다 - Phase 2에서
# "종목별 market_data" 계약을 버리고 "전체 종목 price_history+mapping" 계약으로 바뀌어서,
# run_hierarchical_ranking_pipeline() 안에서 전체 종목 단위로 한 번만 실행된다.
from data.price_history_collector import chart_to_price_rows
from market_intelligence.collectors.price_history_pipeline import run_full_price_history_pipeline
from market_intelligence.collectors.hierarchical_ranking_pipeline import run_hierarchical_ranking_pipeline
from market_intelligence.hierarchical_ranker import compute_market_regime_score
from market_intelligence.supply_demand import compute_supply_demand_score

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

_DEFAULT_TRIAL_STOCK_COUNT = 20  # 안전을 위한 기본값(valuation_pipeline.py와 동일한 관례)

# 【2026-08-22】종목별 일봉(OHLCV) 조회 rate limit - TechnicalAnalyzer 실데이터 연동용.
# market_intelligence/collectors/valuation_collector.py의 _DEFAULT_RATE_LIMIT_SEC와
# 동일한 기존 관례(0.2초)를 그대로 따른다.
_TECHNICAL_FETCH_RATE_LIMIT_SEC = 0.2

# ============ 상시 서비스 모드(serve) 설정 ============
KST = ZoneInfo("Asia/Seoul")
# 2026-09-14: 한국 주식시장 거래시간 변경에 따라 19:00 -> 22:00(KST)로 조정
# (사용자 고지 - 아래 changelog 【2026-09-14】 항목 참고)
_DAILY_RUN_HOUR = 22    # 일마감 분석 목표 시각(KST) - 사용자 지정
_DAILY_RUN_MINUTE = 0
_SCHEDULER_CHECK_INTERVAL_SECONDS = 60  # 상시 루프에서 "지금 실행해야 하나" 체크 주기
_STATE_FILE = Path(__file__).resolve().parent / "data" / "state" / "main_run_state.json"

_shutdown_requested = False  # SIGTERM/SIGINT 수신 시 True로 바뀜 (run_forever 참고)


def get_real_market_data(kis_client: Optional[KISClient]):
    """KIS API에서 실시간 시장 데이터 조회.

    【2026-08-21】공유 KISClient를 인자로 받도록 변경 - 예전에는 이 함수가
    매번 자기만의 KISClient()를 새로 만들어서 토큰도 매번 새로 발급받았다.
    상시 서비스 모드에서는 이게 낭비이자 KIS 토큰 재발급 정책(22시간 재사용)에도
    안 맞으므로, setup_manager_and_client()가 만든 프로세스 전역 공유 인스턴스를
    받아서 ensure_valid_token()으로 필요할 때만 재발급하도록 바꿨다.
    """
    if kis_client is None:
        logger.warning("⚠️  KISClient가 없어 실시간 데이터를 조회할 수 없습니다 (Mock 모드로 진행)")
        return None

    logger.info("\n【실시간 KIS API 데이터 조회 중...】")

    try:
        # 토큰 확보 (없으면 발급, 있으면 22시간 이내는 재사용)
        if not kis_client.ensure_valid_token():
            logger.error("KIS API 토큰 발급 실패")
            return None

        # 실시간 KOSPI/KOSDAQ 조회
        real_data = kis_client.get_kospi_kosdaq()

        if not real_data:
            logger.error("KIS API 데이터 조회 실패")
            return None

        logger.info(f"✅ KOSPI (실제): {real_data.get('kospi_index', 0):.2f}")
        logger.info(f"✅ KOSDAQ (실제): {real_data.get('kosdaq_index', 0):.2f}")

        return real_data

    except Exception as e:
        logger.error(f"KIS API 조회 오류: {e}")
        return None


def build_shared_market_data(real_data: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    모든 종목이 공통으로 사용하는 "시장 전체" 데이터를 만든다.

    【2026-08-18】과거 merge_market_data()에서 ValuationAnalyzer용 종목 자리표시자
    필드(symbol/per/pbr/dividend_yield 등)를 제거했다 - 이제 그 필드들은 종목별로
    get_latest_stock_valuations()가 DB에서 읽어와 analyze_stock()에서 덮어쓴다.
    나머지 분석기(Market/Sector/MoneyFlow/Theme/Technical)는 아직 종목별 실데이터가
    없으므로 시장 전체 기준의 값을 그대로 모든 종목에 공통으로 쓴다.
    【2026-08-24, Phase 5-20】NewsAnalyzer 완전 제거 - 더 이상 이 함수가 뉴스 모의
    데이터를 만들지 않는다(아래 changelog 참고).
    """
    if real_data is None:
        logger.warning("실제 데이터 없음 - 완전 모의 데이터로 진행")
        real_data = {}

    return {
        # ============ MarketAnalyzer (실제 데이터) ============
        "kospi_index": real_data.get('kospi_index', 6258.77),
        "kosdaq_index": real_data.get('kosdaq_index', 798.81),
        "market_volume": real_data.get('market_volume', 1350000000),

        # ============ (구)SectorAnalyzer 모의 데이터 - Phase 5-17부터 사용 안 함 ============
        # 【2026-08-23 주석 추가, Phase 5-17】SectorAnalyzer가 더 이상 여기 등록되지
        # 않으므로(setup_manager_and_client() 참고) 이 8개 키는 이제 아무도 읽지 않는
        # 죽은 데이터다. 실제 Sector 점수는 run_hierarchical_ranking_pipeline() 안에서
        # 실제 가격 히스토리+매핑으로 계산된다. 삭제 대신 남겨둔 이유: 다른 곳에서 우연히
        # 이 키를 참조하는 코드가 있을 가능성을 이번 세션에서 전부 확인하지 못했다(라이브
        # 검증 불가) - 안전하게 삭제해도 되는지는 실제 환경에서 확인 후 별도 정리 과제로.
        "IT_Semiconductor": 1425,
        "Finance": 950,
        "Chemicals_Energy": 650,
        "Consumer": 800,
        "Telecom_Media": 700,
        "Healthcare_Pharma": 1200,
        "Construction_Real_Estate": 550,
        "Secondary_Battery": 900,

        # ============ MoneyFlowAnalyzer (모의 데이터) ============
        "foreign": -8590000000,
        "institutional": 5791000000,
        "retail": 2500000000,
        "program": 500000000,

        # ============ (구)ThemeAnalyzer 모의 데이터 - Phase 5-17부터 사용 안 함 ============
        # 위 Sector 항목과 동일한 이유로 남겨둠 - ThemeAnalyzer도 더 이상 여기 등록되지
        # 않는다. 실제 Theme 점수는 run_hierarchical_ranking_pipeline() 안에서 계산된다.
        "geopolitical_risk": 35,
        "ai_semiconductor": 42,
        "esg_battery": 62,
        "value_buying": 68,
        "economic_recovery": 48,
        "tech_innovation": 65,

        # ============ (구)NewsAnalyzer 모의 데이터 - Phase 5-20부터 사용 안 함 ============
        # NewsAnalyzer 완전 제거(위 changelog 참고) - 이 항목들은 그 analyzer 전용
        # 입력이었고, 다른 analyzer는 참조하지 않는다.

        # ============ TechnicalAnalyzer (모의 데이터 - 아직 종목별 OHLCV 없음) ============
        "macd_value": -15,
        "rsi_value": 28,
        "price": real_data.get('kospi_index', 6258.77),
        "bb_upper": 6600,
        "bb_middle": 6250,
        "bb_lower": 5900,
        "ma5": 6200,
        "ma20": 6280,
        "ma60": 6350,
    }


def get_latest_stock_valuations(session, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """stock_valuation 테이블에서 가장 최근 배치(timestamp가 가장 큰 회차)의 종목별
    PER/PBR/배당수익률 + 시장/Sector 중앙값을 읽어온다. valuation_pipeline.py가 이미
    시장 중앙값(market_per 등)과 Sector 중앙값(sector_per_median 등, Phase 5-19)까지
    계산해서 저장해두므로 여기서 다시 계산하지 않는다.

    limit을 주면(기본 실행 시 안전을 위해 20종목만) 종목코드 순 정렬 후 앞쪽만
    가져온다 - 'all'로 실행할 때는 limit=None이라 전체를 가져온다.

    【2026-08-24, Phase 5-19】sector_per_median/sector_pbr_median/sector_dividend_median은
    DB 값이 None일 때 결과 dict에 키 자체를 아예 넣지 않는다(값을 None으로 넣는 게
    아니라 키를 뺀다) - StockAnalyzer가 `data.get("sector_per_median",
    data.get("market_per"))`로 fallback하는데, dict.get(key, default)는 "키가 아예
    없을 때만" default를 쓰고 "키가 있는데 값이 None"이면 그대로 None을 반환한다.
    여기서 키를 무조건 넣어버리면 Sector 표본이 부족해서 정당하게 시장 중앙값으로
    대체돼야 하는 종목이 오히려 밸류에이션 기준값을 통째로 잃는(None) 버그가 된다.
    """
    from sqlalchemy import func
    from db.models import StockValuation

    latest_ts = session.query(func.max(StockValuation.timestamp)).scalar()
    if latest_ts is None:
        logger.warning("⚠️  stock_valuation 테이블에 데이터가 없습니다 - "
                        "먼저 valuation_pipeline.py를 실행해 데이터를 쌓아주세요.")
        return []

    query = (
        session.query(StockValuation)
        .filter(StockValuation.timestamp == latest_ts)
        .order_by(StockValuation.ticker)
    )
    if limit:
        query = query.limit(limit)

    def _f(value):
        return float(value) if value is not None else None

    results = []
    for row in query.all():
        entry = {
            "symbol": row.ticker,
            "market": row.market,
            "per": _f(row.per),
            "pbr": _f(row.pbr),
            "dividend_yield": _f(row.dividend_yield),
            "market_per": _f(row.market_per),
            "market_pbr": _f(row.market_pbr),
            "market_dividend_yield": _f(row.market_dividend_yield),
        }
        # sector 자체는 참고용으로 항상 넣어도 안전(StockAnalyzer가 fallback 판단에
        # 쓰는 키가 아님) - 아래 3개 median만 None이면 키를 뺀다.
        if row.sector is not None:
            entry["sector"] = row.sector
        if row.sector_per_median is not None:
            entry["sector_per_median"] = _f(row.sector_per_median)
        if row.sector_pbr_median is not None:
            entry["sector_pbr_median"] = _f(row.sector_pbr_median)
        if row.sector_dividend_median is not None:
            entry["sector_dividend_median"] = _f(row.sector_dividend_median)
        results.append(entry)

    return results


def get_latest_hierarchical_scores(session, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """stock_hierarchical_scores 테이블에서 가장 최근 배치(timestamp가 가장 큰 회차)의
    종목별 계층형 순위를 읽어온다.

    【2026-08-23 신규, Phase 5-17】run_hierarchical_ranking_pipeline()은 저장만 하고
    종목별 결과 리스트를 돌려주지 않으므로(총계 dict만 반환), 요약 표 출력용으로
    방금 저장한 배치를 다시 읽어오는 용도 - get_latest_stock_valuations()와 동일한
    "최신 배치를 max(timestamp)로 읽어온다" 관례를 그대로 따른다. final_score가
    None인 행(모든 레벨이 결측인 극단적 경우)은 제외한다."""
    from sqlalchemy import func
    from db.models import StockHierarchicalScore

    latest_ts = session.query(func.max(StockHierarchicalScore.timestamp)).scalar()
    if latest_ts is None:
        return []

    query = (
        session.query(StockHierarchicalScore)
        .filter(StockHierarchicalScore.timestamp == latest_ts)
        .filter(StockHierarchicalScore.final_score.isnot(None))
        .order_by(StockHierarchicalScore.final_score.desc())
    )
    if limit:
        query = query.limit(limit)

    def _f(value):
        return float(value) if value is not None else None

    return [
        {
            "symbol": row.ticker,
            "market": row.market,
            "sector": row.sector,
            "primary_theme": row.primary_theme,
            "market_score": _f(row.market_score),
            "sector_score": _f(row.sector_score),
            "theme_score": _f(row.theme_score),
            "stock_score": _f(row.stock_score),
            "final_score": _f(row.final_score),
            "sector_rank": row.sector_rank,
            "theme_rank": row.theme_rank,
            "overall_rank": row.overall_rank,
        }
        for row in query.all()
    ]


def analyze_stock(manager: IntelligenceManager, shared_data: Dict[str, Any],
                   stock_row: Dict[str, Any],
                   kis_client: Optional[KISClient] = None,
                   price_rows_sink: Optional[List[Dict[str, Any]]] = None,
                   supply_demand_sink: Optional[Dict[str, float]] = None) -> Optional[Dict[str, Any]]:
    """시장 공통 데이터(shared_data)에 종목별 밸류에이션 실데이터(stock_row)를 덮어씌워
    4개 분석기를 한 번 실행한다(개수는 Phase 5-17에서 7→5, Phase 5-20에서 5→4로
    줄었다 - setup_manager_and_client() 참고). 실패해도 전체 루프를 막지 않도록
    예외를 잡아 None을 돌려준다(호출부에서 건너뜀).

    【2026-08-22 수정, Phase 5-11】TechnicalAnalyzer가 여태 매 종목·매 사이클
    validate() 실패로 조용히 스킵되고 있던 문제(가중치 18% 미반영)를 발견해서 -
    kis_client.get_stock_daily_chart()로 종목별 실제 60일 일봉(OHLCV)을 조회해
    closes/opens/highs/lows/volumes를 채운다. 조회 실패(네트워크 오류, 상장 60일
    미만 신규종목 등)해도 이 함수 자체는 계속 진행 - 그 경우 technical만 여전히
    validate() 실패로 스킵되고 나머지 분석기는 정상 진행된다(에러로 전체 종목을
    막지 않음, 기존 원칙과 동일). kis_client가 없으면(Mock 모드) 기존처럼 스킵.

    【2026-08-23 추가, Phase 5-17】price_rows_sink를 넘기면, 위에서 이미 받은 chart
    응답을 stock_price_history 저장용 행으로 변환해 그 리스트에 추가한다(API를
    또 호출하지 않음 - data/price_history_collector.py의 chart_to_price_rows()
    재사용). TechnicalAnalyzer는 60일 미만이면 통째로 쓰지 않지만(위 market_data
    갱신 조건), Sector/Theme 바스켓 계산은 부분 데이터도 쓸 수 있으므로
    (market_intelligence/price_series.py의 compute_ticker_metrics 참고) chart가
    비어있지만 않으면 길이와 무관하게 저장한다.

    【2026-08-24 추가, Phase 5-18】supply_demand_sink를 넘기면, kis_client.
    get_investor_trend()로 이 종목의 외국인/기관 순매수 동향을 추가 조회해서
    (API 호출 1회 더 - rate limit도 한 번 더 sleep), market_intelligence.
    supply_demand.compute_supply_demand_score()로 0~100 점수를 만들어
    {symbol: score} 형태로 그 dict에 채운다. StockAnalyzer 자체는 이 함수가
    아니라 run_hierarchical_ranking_pipeline() 호출 시 valuation_by_ticker를
    통해 이 점수를 받는다(run_analysis_cycle() 참고) - analyze_stock()은
    5개 flat 분석기만 실행하고 StockAnalyzer/계층형 결합은 그 이후 별도
    단계이기 때문. investor_trend 조회 실패(빈 dict)나 점수 계산 불가(None)여도
    이 함수 자체나 flat 분석은 막지 않는다(기존 원칙과 동일)."""
    market_data = {**shared_data, **stock_row}
    symbol = stock_row.get("symbol")

    if kis_client is not None:
        chart = kis_client.get_stock_daily_chart(symbol, days=60)
        if chart and len(chart.get("closes", [])) >= 60:
            market_data.update({
                "closes": chart["closes"],
                "opens": chart["opens"],
                "highs": chart["highs"],
                "lows": chart["lows"],
                "volumes": chart["volumes"],
            })
        symbol_price_rows = (
            chart_to_price_rows(symbol, stock_row.get("market"), chart) if chart else []
        )
        if price_rows_sink is not None and symbol_price_rows:
            price_rows_sink.extend(symbol_price_rows)
        # KIS API 호출 간격 제한 (기존 관례 0.2초 - valuation_collector.py와 동일)
        time.sleep(_TECHNICAL_FETCH_RATE_LIMIT_SEC)

        if supply_demand_sink is not None:
            investor_trend = kis_client.get_investor_trend(symbol)
            supply_demand_score = compute_supply_demand_score(investor_trend, symbol_price_rows)
            if supply_demand_score is not None:
                supply_demand_sink[symbol] = supply_demand_score
            time.sleep(_TECHNICAL_FETCH_RATE_LIMIT_SEC)

    try:
        results = manager.run_all(market_data)
    except Exception as e:
        logger.error(f"  {stock_row.get('symbol')} 분석 중 오류 - {e}")
        return None

    if not results.get("success"):
        logger.warning(f"  {stock_row.get('symbol')} 분석 실패 - {results.get('error')}")
        return None

    return {
        "symbol": stock_row.get("symbol"),
        "market": stock_row.get("market"),
        "final_score": results.get("final_score", 0),
        "individual_scores": results.get("individual_scores", {}),
    }


def analyze_sentiment(score):
    """점수에 따른 시장 심리 분석"""
    if score >= 70:
        return {"mood": "🟢 강한 매수 신호", "strategy": "적극적 매수", "risk": "낮음"}
    elif score >= 60:
        return {"mood": "🟢 매수 신호", "strategy": "점진적 매수", "risk": "낮음~중간"}
    elif score >= 50:
        return {"mood": "🟡 중립", "strategy": "관망 또는 분할 매수", "risk": "중간"}
    elif score >= 40:
        return {"mood": "🔴 매도 신호", "strategy": "점진적 매도", "risk": "중간~높음"}
    else:
        return {"mood": "🔴 강한 매도 신호", "strategy": "적극적 매도", "risk": "높음"}


def _print_summary_table(title: str, rows: List[Dict[str, Any]]):
    logger.info(f"\n【{title}】")
    for r in rows:
        sentiment = analyze_sentiment(r["final_score"])
        logger.info(f"  {r['symbol']:8} {r['market']:6} 점수={r['final_score']:6.2f}  {sentiment['mood']}")


def _fmt(value: Optional[float]) -> str:
    """None(결측 레벨)을 로그에서 깨지지 않게 표시 - 계층형 결과는 market/sector/
    theme 중 일부가 종목에 따라 결측일 수 있다(예: Theme 매핑이 없는 종목)."""
    return f"{value:5.1f}" if value is not None else "  결측"


def _print_hierarchical_table(title: str, rows: List[Dict[str, Any]]):
    """계층형 순위(시장→Sector→Theme→종목) 결과 표 - Step 8 전용 (Phase 5-17 신규)."""
    logger.info(f"\n【{title}】")
    for r in rows:
        sentiment = analyze_sentiment(r["final_score"])
        logger.info(
            f"  {r['symbol']:8} {(r['market'] or '-'):6} 최종={r['final_score']:6.2f}  "
            f"(시장={_fmt(r['market_score'])} Sector={_fmt(r['sector_score'])} "
            f"Theme={_fmt(r['theme_score'])} 종목={_fmt(r['stock_score'])})  {sentiment['mood']}"
        )


def setup_manager_and_client():
    """IntelligenceManager 초기화 + 4개 분석기 등록(Phase 5-17에서 7→5, Phase 5-20에서
    5→4 - Sector/Theme는 계층형 순위 파이프라인 안에서 별도 실행, News는 완전 제거)
    + 공유 KISClient 준비.

    프로세스 시작 시 **한 번만** 호출한다 - 매 사이클 반복하면 KISClient가
    계속 새로 생겨서 토큰도 매번 새로 발급되어 버린다(22시간 재사용 정책과
    어긋남). 반환한 manager/kis_client를 run_analysis_cycle()에 그대로
    넘겨서 재사용한다.
    """
    logger.info("\n【Step 1】IntelligenceManager 초기화 중...")
    manager = IntelligenceManager()
    logger.info("✅ IntelligenceManager 준비 완료")

    # 공유 KISClient - 실패(API 키 미설정 등)해도 None으로 두고 계속 진행
    # (MarketAnalyzer/TechnicalAnalyzer가 각자 Mock 모드로 폴백함)
    kis_client = None
    try:
        kis_client = KISClient()
    except Exception as e:
        logger.warning(f"⚠️  공유 KISClient 초기화 실패 - Mock 모드로 진행: {e}")

    # 【2026-08-23 수정, Phase 5-17】SectorAnalyzer/ThemeAnalyzer 제거 - 이 둘은 이제
    # 종목별 market_data가 아니라 전체 종목 price_history+mapping을 요구하는 배치성
    # analyzer라(Phase 2), 옛 계약대로 여기 등록해두면 validate()가 매 종목·매 사이클
    # 조용히 실패하기만 한다(Phase 5-11에서 TechnicalAnalyzer가 겪었던 것과 같은 버그
    # 패턴 - 반복하지 않기로 함). 계층형 순위 계산 안에서 전체 종목 단위로 한 번만 실행됨.
    # 【2026-08-24 수정, Phase 5-20】NewsAnalyzer 제거 - 계층형 최종 공식(StockAnalyzer)
    # 에는 애초에 뉴스 컴포넌트가 없었고, 이 flat 등록은 Step 7 참고표에만 쓰였는데
    # 입력 자체가 전 종목·전 사이클 동일한 하드코딩 모의값이라 종목 간 차이를 전혀
    # 만들지 못했다(사용자 결정 - docs/hierarchical_scoring_plan.md Phase 5-20 참고).
    logger.info("\n【Step 2】4개 분석기 등록 중 (Sector/Theme는 계층형 순위 파이프라인에서 별도 실행)...")
    analyzers = [
        MarketAnalyzer(kis_client=kis_client),
        MoneyFlowAnalyzer(),
        TechnicalAnalyzer(kis_client=kis_client),
        ValuationAnalyzer()
    ]

    for analyzer in analyzers:
        manager.register_analyzer(analyzer)
        logger.info(f"✅ {analyzer.name} 등록 완료 (weight={analyzer.weight})")

    logger.info(f"✅ 총 {len(analyzers)}개 분석기 등록 완료")

    return manager, analyzers, kis_client


def run_analysis_cycle(manager: IntelligenceManager, analyzers: List[Any],
                        kis_client: Optional[KISClient], limit: Optional[int]) -> bool:
    """분석 1회 사이클 (예전 main()의 Step 3~7에 해당).

    setup_manager_and_client()가 만든 manager/analyzers/kis_client를 그대로
    받아서 재사용한다 - 이 함수 자체는 상태를 만들지 않으므로 하루에 한 번이든
    반복 호출이든 안전하다.
    """
    logger.info("=" * 80)
    logger.info(f"🎊 MIE V2.0 - 종목별 분석 사이클 시작! ({datetime.now(KST).strftime('%Y-%m-%d %H:%M:%S')} KST)")
    logger.info("=" * 80)

    # 3. 시장 공통 데이터 준비 (실시간 KIS API + 모의 데이터)
    logger.info("\n【Step 3】시장 공통 데이터 준비 중...")
    real_data = get_real_market_data(kis_client)
    shared_data = build_shared_market_data(real_data)
    if real_data:
        logger.info("✅ 실제 시장 데이터 + 분석 데이터 준비 완료")
    else:
        logger.warning("⚠️  모의 데이터로 진행 (실제 데이터 조회 실패)")

    # 4. 분석기 배선 sanity check (종목 루프 전에 한 번만 - 루프마다 반복하면 너무 장황함)
    # 【2026-08-22 주석 추가】technical은 여기서 항상 validate=False로 나오는 게 정상이다 -
    # closes/opens/highs/lows/volumes는 종목별 실제 데이터(analyze_stock 내부에서
    # kis_client.get_stock_daily_chart()로 조회)라서 시장 공통 데이터(shared_data)만
    # 가지고 하는 이 배선 점검 단계에는 애초에 없다. 실제 검증은 Step 6 종목별 루프에서
    # 이루어진다.
    logger.info("\n【Step 4】분석기 배선 확인 (시장 공통 데이터만으로 1회 점검)...")
    for analyzer in analyzers:
        try:
            is_valid = analyzer.validate(shared_data)
            logger.info(f"  {analyzer.name}: validate={is_valid}")
        except Exception as e:
            logger.error(f"  {analyzer.name}: {str(e)}")

    # 5. 종목별 분석 루프
    logger.info("\n【Step 5】종목별 밸류에이션 데이터 조회 중...")
    if limit:
        logger.warning(f"⚠️  시험 실행: 앞쪽 {limit}종목만 분석합니다 (전체는 'all' 인자로 실행)")

    from config.database import SessionLocal
    session = SessionLocal()
    try:
        stock_rows = get_latest_stock_valuations(session, limit=limit)
    finally:
        session.close()

    if not stock_rows:
        logger.error("❌ 분석할 종목 데이터가 없습니다 - 먼저 valuation_pipeline.py를 실행해주세요.")
        return False

    logger.info(f"✅ {len(stock_rows)}종목 조회 완료 - 종목별 분석 시작")

    logger.info("\n【Step 6】종목별 4개 분석기 실행 중...")
    if kis_client is not None:
        # 【2026-08-24 갱신, Phase 5-18】종목당 API 호출이 일봉 1회 → 일봉+투자자매매동향
        # 2회로 늘어 rate limit sleep도 2번(총 약 2 * _TECHNICAL_FETCH_RATE_LIMIT_SEC) -
        # 예상 소요 시간 안내도 그에 맞춰 갱신.
        _calls_per_stock = 2
        logger.info(
            f"   ⏱️  종목별 실제 일봉(OHLCV)+투자자 매매동향 조회 포함 - 종목당 약 "
            f"{_TECHNICAL_FETCH_RATE_LIMIT_SEC * _calls_per_stock:.1f}초+ 소요 (전체 {len(stock_rows)}종목 기준 "
            f"최소 {len(stock_rows) * _TECHNICAL_FETCH_RATE_LIMIT_SEC * _calls_per_stock / 60:.1f}분 이상 예상)"
        )
    results = []
    # 【2026-08-23 추가, Phase 5-17】루프 안에서 이미 조회한 chart 응답을 stock_price_
    # history 저장용으로 누적한다 - Step 6-1에서 API를 또 호출하지 않고 그대로 쓴다.
    price_rows: List[Dict[str, Any]] = []
    # 【2026-08-24 추가, Phase 5-18】{symbol: 수급 0~100점수} - Step 6-2에서
    # valuation_by_ticker에 병합해 StockAnalyzer의 supply_demand_score로 흘려보낸다.
    supply_demand_scores: Dict[str, float] = {}
    for idx, stock_row in enumerate(stock_rows, start=1):
        result = analyze_stock(
            manager, shared_data, stock_row, kis_client,
            price_rows_sink=price_rows, supply_demand_sink=supply_demand_scores,
        )
        if result is not None:
            results.append(result)
        if kis_client is not None and idx % 100 == 0:
            logger.info(f"   ... {idx}/{len(stock_rows)}종목 처리 중")

    if not results:
        logger.error("❌ 분석에 성공한 종목이 하나도 없습니다.")
        return False

    # 6-1/6-2. 일봉 히스토리 DB 저장 + 계층형 순위(시장→Sector→Theme→종목) 계산
    # 【2026-08-23 신규, Phase 5-17】일봉 저장을 먼저 커밋해야 계층형 파이프라인이
    # price_history=None(DB에서 직접 읽기)으로 방금 저장한 데이터까지 포함해서 읽는다 -
    # 순서를 바꾸면 이번 사이클에서 막 갱신된 데이터가 계층형 계산에서 빠질 수 있다.
    logger.info("\n【Step 6-1】일봉 히스토리 DB 저장 중...")
    if price_rows:
        ph_session = SessionLocal()
        try:
            ph_result = run_full_price_history_pipeline(ph_session, records=price_rows)
            logger.info(
                f"✅ 일봉 히스토리 저장: {ph_result['total_symbols']}종목, "
                f"{ph_result['rows_fetched']}행 중 신규 {ph_result['rows_saved']}행"
            )
        except Exception as e:
            logger.error(f"⚠️  일봉 히스토리 저장 실패(계층형 순위는 계속 진행) - {e}")
        finally:
            ph_session.close()
    else:
        logger.warning(
            "⚠️  수집된 일봉 데이터가 없어 히스토리 저장을 건너뜁니다 "
            "(kis_client 없음 또는 전 종목 조회 실패)"
        )

    logger.info("\n【Step 6-2】계층형 순위(시장→Sector→Theme→종목) 계산 중...")
    market_regime_scores = {
        "KOSPI": compute_market_regime_score((real_data or {}).get("kospi_change_rate")),
        "KOSDAQ": compute_market_regime_score((real_data or {}).get("kosdaq_change_rate")),
    }
    valuation_by_ticker = {row["symbol"]: row for row in stock_rows}
    # 【2026-08-24 추가, Phase 5-18】종목별 수급 점수를 밸류에이션 dict에 얹어서
    # run_hierarchical_ranking_pipeline()의 기존 valuation_by_ticker 인자(그대로
    # StockAnalyzer 입력 dict로 병합됨 - hierarchical_ranking_pipeline.py 참고)를
    # 통해 흘려보낸다 - 새 파라미터를 추가하지 않고 기존 배선을 재사용.
    for symbol, score in supply_demand_scores.items():
        if symbol in valuation_by_ticker:
            valuation_by_ticker[symbol]["supply_demand_score"] = score
    hr_session = SessionLocal()
    try:
        hr_result = run_hierarchical_ranking_pipeline(
            hr_session,
            market_regime_scores=market_regime_scores,
            valuation_by_ticker=valuation_by_ticker,
        )
        logger.info(
            f"✅ 계층형 순위 완료: {hr_result['total']}종목 저장 "
            f"(Sector {hr_result.get('sector_count', 0)}개, Theme {hr_result.get('theme_count', 0)}개)"
        )
    except Exception as e:
        # 【2026-09-05 수정, 심각한 버그】원래 이 except가 에러만 로그로 남기고
        # return을 안 해서, 계층형 순위 계산이 매번 실패해도 run_analysis_cycle()이
        # 끝까지 진행해 결국 True를 반환했다 - run_forever()는 이 True만 보고
        # "✅ 일마감 분석 완료 및 기록"으로 main_run_state.json에 성공을 남겼다.
        # 그 결과 stock_hierarchical_scores(계층형 랭킹, trade_execution_pipeline.py가
        # 신규진입 후보로 쓰는 바로 그 테이블)가 갱신 안 되는데도 아무도(로그도,
        # 완료 기록도) 실패를 알아채지 못하는 상태가 지속될 수 있었다 - 실제로 이
        # 버그가 원인인지는 아직 라이브로 재현 못했지만(같은 세션에서 발견한 별개
        # 문제 - main.py 자체가 8/22 커밋 이후로 EC2에 배포조차 안 되고 있었음 -
        # 진짜 원인일 가능성이 더 높음), 이 함수의 계약("계층형 순위까지 성공해야
        # True")을 지키려면 어느 경우든 이 return은 반드시 있어야 한다.
        logger.error(f"❌ 계층형 순위 계산 실패 - {e}")
        return False
    finally:
        hr_session.close()

    # 7. 결과 요약 (flat 개별 분석기 - 참고/디버깅용, Phase 5-17부터는 최종 결정 기준이 아님)
    logger.info("\n" + "=" * 80)
    logger.info("【Step 7】종목별 flat 개별 분석기 결과 요약 (참고용 - 최종 순위는 Step 8)")
    logger.info("=" * 80)

    scores = [r["final_score"] for r in results]
    logger.info(f"분석 성공: {len(results)}/{len(stock_rows)}종목")
    logger.info(f"평균 점수: {sum(scores) / len(scores):.2f}점")
    logger.info(f"최고 점수: {max(scores):.2f}점 / 최저 점수: {min(scores):.2f}점")

    ranked = sorted(results, key=lambda r: r["final_score"], reverse=True)
    top_n = min(10, len(ranked))
    _print_summary_table(f"상위 {top_n}종목 (flat 참고용)", ranked[:top_n])
    _print_summary_table(f"하위 {top_n}종목 (flat 참고용)", ranked[-top_n:][::-1])

    # 8. 계층형 순위 결과 요약 (신규, Phase 5-17 - 최종 매수/매도 판단 기준)
    logger.info("\n" + "=" * 80)
    logger.info("【Step 8】계층형 순위(시장→Sector→Theme→종목) 결과 요약")
    logger.info("=" * 80)

    summary_session = SessionLocal()
    try:
        hierarchical_rows = get_latest_hierarchical_scores(summary_session)
    finally:
        summary_session.close()

    if hierarchical_rows:
        h_scores = [r["final_score"] for r in hierarchical_rows]
        logger.info(f"계층형 순위 산출: {len(hierarchical_rows)}종목")
        logger.info(f"평균 점수: {sum(h_scores) / len(h_scores):.2f}점")
        logger.info(f"최고 점수: {max(h_scores):.2f}점 / 최저 점수: {min(h_scores):.2f}점")
        h_top_n = min(10, len(hierarchical_rows))
        _print_hierarchical_table(f"상위 {h_top_n}종목 (계층형 매수 후보)", hierarchical_rows[:h_top_n])
        _print_hierarchical_table(f"하위 {h_top_n}종목 (계층형 매도/회피 후보)", hierarchical_rows[-h_top_n:][::-1])
    else:
        logger.warning(
            "⚠️  계층형 순위 결과가 없습니다 - stock_sector_mapping/stock_theme_mapping이 "
            "비어있거나(sector_theme_importer.py 미실행) 일봉 히스토리가 부족할 수 있습니다"
        )

    logger.info("\n" + "=" * 80)
    logger.info("✅ 분석 사이클 완료")
    logger.info("=" * 80)

    return True


def main():
    """수동 1회 실행 진입점 (기존 CLI 관례 그대로 유지).

    인자 없이 `python main.py` -> 시험(앞쪽 20종목), `python main.py all`
    -> 전체 종목, 1회 실행 후 종료. 상시 서비스 모드는 run_forever() 참고
    (systemd/mie-v2.service가 `python main.py serve`로 그쪽을 실행한다).
    """
    manager, analyzers, kis_client = setup_manager_and_client()

    full_run = len(sys.argv) > 1 and sys.argv[1] == "all"
    limit = None if full_run else _DEFAULT_TRIAL_STOCK_COUNT

    return run_analysis_cycle(manager, analyzers, kis_client, limit)


# ============ 상시 서비스 모드 (serve) ============

def _load_run_state() -> Dict[str, Any]:
    """data/state/main_run_state.json에서 마지막 완료 날짜를 읽는다.
    파일이 없거나(최초 실행) 손상됐으면 빈 dict를 돌려준다."""
    if not _STATE_FILE.exists():
        return {}
    try:
        return json.loads(_STATE_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning(f"⚠️  실행 상태 파일 읽기 실패({e}) - 처음 실행하는 것으로 간주합니다")
        return {}


def _save_run_state(completed_date: str) -> None:
    """분석 사이클이 성공적으로 끝난 뒤 완료 날짜를 기록한다."""
    _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "last_completed_date": completed_date,
        "last_completed_at": datetime.now(KST).isoformat(),
    }
    _STATE_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _should_run_now(state: Dict[str, Any], now_kst: datetime) -> bool:
    """일마감 분석을 지금 실행해야 하는지 판단한다.

    - 주말(토/일)은 건너뛴다 (KRX 휴장 - 공휴일은 아직 처리 못함, 알려진 한계)
    - 마지막 완료 기록이 아예 없으면(최초 실행) -> 즉시 실행
    - 마지막 완료일이 오늘이면 -> 이미 끝났으니 대기
    - 마지막 완료일이 어제보다도 이전이면(하루 이상 밀림) -> 목표 시각과
      무관하게 즉시 실행 (다운타임 복구/따라잡기)
    - 그 외(마지막 완료일이 어제, 오늘 몫만 밀림) -> 오늘 목표 시각(22:00
      KST, 2026-09-14부터 - 이전엔 19:00)이 지났으면 실행
    """
    if now_kst.weekday() >= 5:  # 5=토요일, 6=일요일
        return False

    last_completed_date = state.get("last_completed_date")
    today_str = now_kst.strftime("%Y-%m-%d")

    if last_completed_date is None:
        return True  # 최초 실행 - 바로 진행

    if last_completed_date == today_str:
        return False  # 오늘 이미 완료

    try:
        last_date = datetime.strptime(last_completed_date, "%Y-%m-%d").date()
    except ValueError:
        last_date = None

    yesterday = (now_kst - timedelta(days=1)).date()

    if last_date is None or last_date < yesterday:
        # 이틀 이상 밀렸거나(다운타임이 길었음) 날짜 파싱 실패 - 즉시 따라잡기
        logger.warning(
            f"⚠️  마지막 완료일({last_completed_date})이 오래되어 목표 시각과 무관하게 "
            f"즉시 분석을 진행합니다"
        )
        return True

    # last_date == yesterday: 오늘 몫만 밀린 상태 - 목표 시각(22:00) 이후인지 확인
    target = now_kst.replace(hour=_DAILY_RUN_HOUR, minute=_DAILY_RUN_MINUTE, second=0, microsecond=0)
    return now_kst >= target


def _handle_shutdown_signal(signum, frame):
    """SIGTERM(systemd stop/restart)/SIGINT(Ctrl+C) 수신 시 다음 체크 지점에서
    루프를 빠져나가도록 플래그만 세운다 - 분석 사이클 도중이면 그 사이클은
    끝까지 마치고 나서 종료한다(중간에 죽여서 DB에 반쪽짜리 결과를 남기지 않기 위함)."""
    global _shutdown_requested
    logger.info(f"\n종료 신호 수신(signal={signum}) - 현재 체크 지점 이후 안전하게 종료합니다")
    _shutdown_requested = True


def run_forever():
    """상시 서비스 모드 - systemd(mie-v2.service, ExecStart를 `python main.py serve`로
    변경 필요)가 이 함수를 실행한다.

    평일 KST 22:00(2026-09-14부터 - 이전엔 19:00)에 하루 한 번 전체 종목(all) 분석 사이클을 실행하고, 완료
    시각을 data/state/main_run_state.json에 기록한다. 그 외 시간에는 프로세스가
    종료하지 않고 60초 간격으로 "지금 실행해야 하나"만 체크하며 대기한다
    (_should_run_now 참고 - 다운타임 후 재기동 시 따라잡기 로직 포함).

    한 사이클이 예외로 실패해도 프로세스 전체는 죽지 않는다 - 완료 기록을
    남기지 않은 채 다음 체크 때 다시 시도한다.
    """
    global _shutdown_requested
    signal.signal(signal.SIGTERM, _handle_shutdown_signal)
    signal.signal(signal.SIGINT, _handle_shutdown_signal)

    logger.info("=" * 80)
    logger.info("🎊 MIE V2.0 - 상시 서비스 모드 시작 (일마감 분석, 평일 22:00 KST)")
    logger.info("=" * 80)

    manager, analyzers, kis_client = setup_manager_and_client()

    while not _shutdown_requested:
        now_kst = datetime.now(KST)
        state = _load_run_state()

        if _should_run_now(state, now_kst):
            try:
                success = run_analysis_cycle(manager, analyzers, kis_client, limit=None)
                if success:
                    _save_run_state(now_kst.strftime("%Y-%m-%d"))
                    logger.info(f"✅ 일마감 분석 완료 및 기록 - {now_kst.strftime('%Y-%m-%d')}")
                else:
                    logger.error("❌ 분석 사이클이 실패로 종료됨 - 완료 기록 안 함 (다음 체크에 재시도)")
            except Exception as e:
                logger.error(f"❌ 분석 사이클 중 처리되지 않은 예외 발생 - {e}")
                import traceback
                logger.error(traceback.format_exc())
                logger.error("완료 기록을 남기지 않고 계속 대기합니다 (다음 체크에 재시도)")

        # 1초 단위로 쪼개서 대기 - 종료 신호가 오면 최대 1초 안에 반응하기 위함
        for _ in range(_SCHEDULER_CHECK_INTERVAL_SECONDS):
            if _shutdown_requested:
                break
            time.sleep(1)

    logger.info("👋 상시 서비스 모드 정상 종료")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "serve":
        # 상시 서비스 모드 - systemd(mie-v2.service)가 이걸로 실행하도록
        # ExecStart를 `python main.py serve`로 바꿔야 한다.
        run_forever()
        sys.exit(0)
    else:
        # 기존 CLI 관례 그대로: 인자 없으면 시험(20종목), 'all'이면 전체 - 1회 실행 후 종료
        success = main()
        sys.exit(0 if success else 1)
