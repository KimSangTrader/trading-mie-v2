# 계층형 스코어링(시장→Sector→Theme→종목) 도입 계획

작성일: 2026-08-23
근거 문서: `sector_analy_method.txt` (사용자 첨부, 이하 "방법론 문서")
결정: 최종 결합 구조를 방법론 문서의 계층형 공식으로 전면 교체 (사용자 확인 완료)

---

## 1. 요약

방법론 문서는 `시장(10%) + Sector(20%) + Theme(20%) + 종목(50%)` 4단계 가중합으로
최종 종목 점수를 계산하자고 제안한다. 이는 현재 `IntelligenceManager.run_all()`이
쓰는 flat 7-analyzer 가중평균(market 0.30 / sector 0.18 / moneyflow 0.14 /
theme 0.14 / news 0.09 / technical 0.18 / valuation 0.09)을 완전히 대체하는
구조 변경이다.

코드베이스를 확인한 결과 두 가지가 이미 준비되어 있었다.

- `SectorAnalyzer`(weight 0.18)와 `ThemeAnalyzer`(weight 0.14)가 **존재는 하지만
  완전히 mock 데이터**로 동작한다(하드코딩된 8개 Sector/6개 추상 Theme, 고정
  bull/bear 기준값).
- 종목별 실제 Sector(12종)/Theme(18종, Primary+Secondary) 매핑은
  `sector_theme_importer.py`를 통해 이미 DB(`stock_sector_mapping`,
  `stock_theme_mapping`, 2,760종목)에 들어가 있다.

즉 이번 작업은 "새 기능 추가"가 아니라, `sector_theme_importer.py`의 변경 이력
주석이 이미 예고했던 후속 작업(SectorAnalyzer/ThemeAnalyzer를 실제 데이터 기반으로
재설계)을 방법론 문서의 구체적 공식으로 채우는 것이다.

## 2. 결정적 갭: 종목별 일봉 가격/거래대금 히스토리가 DB에 없다

`db/schema.sql` 전체 11개 테이블을 확인했다. 방법론 문서의 모든 공식
(Sector/Theme의 5·20·60일 수익률, 상대강도, 상승확산도, 거래대금 증가, 종목의
기술적 점수 중 수익률/이평선/RSI/52주 고점거리)은 **종목별 일별 OHLCV 시계열**을
전제로 한다. 그런데:

- `sector_data`: Sector "지수값" 스냅샷만 있음(수익률 계산 불가, 그날그날 지수값만).
- `technical_indicators`: 컬럼에 `ticker`가 없다 — 종목별이 아니라 단일 글로벌
  스냅샷 1행 구조. 지금 `TechnicalAnalyzer`도 DB에서 안 읽고 호출부가 매번
  `closes/opens/highs/lows/volumes` 리스트를 직접 넘겨받아 계산만 한다.
- `money_flow_data`: 시장 전체 수급(외국인/기관/개인 순매수 합계)만 있고
  종목별이 아니다.
- 종목별 일봉을 저장하는 테이블 자체가 없다.

다만 완전히 맨땅은 아니다. `data/kis_client.py`에 `get_stock_daily_chart(stock_code,
days=60)`(Phase 5-11에서 이미 추가됨, API 1회 호출로 최근 60일 일봉 조회, 종목당
호출 1회)가 있어서 **원본 데이터를 가져올 방법은 이미 있다** — 저장(persist)만
안 되어 있을 뿐이다. `ValuationCollector`가 쓰는 관례(0.2초 rate limit)를 그대로
적용하면 2,760종목 전체 수집에 약 9~10분 걸린다(장마감 후 배치로 충분히 실행 가능
— 방법론 문서 8절이 그리는 그림과 정확히 일치).

**종목별 외국인/기관 순매수(수급 25점 항목)는 이 코드베이스 어디에도 조회 방법이
없다.** KIS Open API에 종목별 투자자매매동향 API가 별도로 존재하긴 하지만, 이
프로젝트에는 아직 연동되어 있지 않다. 이번 계획에서는 이를 "결측 시 제외 후
재정규화"(ValuationAnalyzer가 이미 쓰는 패턴)로 처리하고, 실제 연동은 별도
후속 작업으로 분리한다.

## 3. Phase별 계획

### Phase 1 — 종목별 일봉 히스토리 데이터 파이프라인 (선행 필수)
- `db/models.py`에 `StockPriceHistory` 추가 (ticker, market, trade_date, open/high/
  low/close/volume, PK는 (ticker, trade_date) 유니크).
- `db/schema.sql`에 매칭 `CREATE TABLE`.
- `data/price_history_collector.py`: `KISClient.get_stock_daily_chart()`를
  종목 리스트에 대해 rate-limit + checkpoint/resume하며 호출 (`ValuationCollector`
  패턴 그대로 재사용).
- `market_intelligence/collectors/price_history_pipeline.py`: 종목마스터 →
  수집 → DB upsert까지 엔드투엔드 (`valuation_pipeline.py` 패턴).
- 이 세션은 실제 KIS API/DB에 접근할 수 없으므로 필드명(`stck_bsop_date` 등)은
  기존 `get_stock_daily_chart()`가 이미 "라이브 검증 필요"로 표시해 둔 상태 그대로
  이어받는다 — 이번 Phase에서 그 가정을 새로 추가하지는 않는다.

### Phase 2 — SectorAnalyzer / ThemeAnalyzer 실계산 전환
- 입력을 "하드코딩 dict"에서 "당일 `stock_price_history` + `stock_sector_mapping`
  /`stock_theme_mapping` 최신 배치"로 교체.
- Sector 점수 = 모멘텀30(5일×0.2+20일×0.5+60일×0.3) + 상대강도25(Sector 20일수익률
  − 시장(KOSPI/KOSDAQ) 20일수익률) + 확산도20(상승종목비율) + 거래대금15(최근5일
  평균÷최근20일평균) + 추세안정성10(20일선>60일선 등).
- Theme 점수는 동일 구조 + 종목이 여러 Theme에 속할 때
  `Primary×0.70+Secondary1×0.20+Secondary2×0.10`.
- 기존 8개 Sector 하드코딩(`Secondary_Battery` 포함)을 실제 12개 카테고리로 교체
  (Secondary_Battery는 Sector가 아니라 Theme로 이동 — `sector_theme_importer.py`
  주석에서 이미 확인됨).

### Phase 3 — StockAnalyzer(개별 종목 100점) 신규
- 기술적 35점: 기존 `TechnicalAnalyzer` 결과를 문서 배점(단기10/중기10/거래량5/
  RSI5/추세5)으로 재매핑해 재사용.
- 수급 25점: 종목별 외국인/기관 데이터 없음 → 이번 Phase에서는 가중치를 결측
  처리하고 나머지 항목으로 재정규화(추후 API 연동 시 채움). 이 사실을 `data_quality`
  필드로 노출해 "조용히 틀린 값"을 주지 않는다 — `ValuationAnalyzer`가 쓰는
  원칙과 동일.
- 밸류에이션 20점: 기존 `ValuationAnalyzer` 재사용하되, 기준값을 "시장 전체 중앙값"
  에서 "같은 Sector 내 중앙값"으로 교체(문서 5-C절 요구사항). `market_valuation.py`
  확장 필요.
- Sector 내 상대강도 20점: 종목 20일수익률 − 소속 Sector 평균 20일수익률(Phase 1
  데이터로 계산).

### Phase 4 — 계층형 결합 + main.py 배선
- 신규 `HierarchicalCombinedAnalyzer`(가칭): `market*0.10 + sector*0.20 +
  theme*0.20 + stock*0.50`, `stock_score`는 Phase 3 내부에서 이미 100점으로 합산.
- `IntelligenceManager.run_all()`의 flat 가중평균 대신 이 결합기를 최종 경로로
  사용. 기존 flat 결과는 `individual_scores`로 계속 노출해 비교/디버깅 가능하게
  유지(문서 9절 "3개 순위 동시 제공" 권고와도 부합).
- `news_analyzer`는 문서 공식에 자리가 없다 — 최종 점수에서 제외하고, 대신
  경고/디스플레이용 보조 신호(예: 중요 공시 시 최종 순위에 배지 표시)로 격하할지
  결정 필요(사용자 확인 필요 항목으로 남김).
- `AnalysisResults` 테이블에 `sector_score_detail`, `theme_score_detail`,
  `stock_score`, `hierarchical_final_score` 등 컬럼 추가.

## 3-1. 진행 현황 (2026-08-23 세션 종료 시점)

Phase 1~4 핵심 로직을 모두 구현했다. 실제 DB/KIS API가 없는 샌드박스라 전부
SQLite 단위테스트 + 코드 리뷰로만 검증했다(이 프로젝트의 기존 관례와 동일) -
사용자 컴퓨터에서 `pytest tests/ -v` 실행 필요.

- **Phase 1 (완료)**: `db/models.py`/`db/schema.sql`에 `StockPriceHistory` 추가,
  `data/price_history_collector.py` + `market_intelligence/collectors/
  price_history_pipeline.py`.
- **Phase 2 (완료)**: `market_intelligence/price_series.py`(Sector/Theme 공용
  바스켓 스코어링 - 모멘텀/상대강도/확산도/거래대금/추세안정성 계산 + 결측 시
  재정규화), `SectorAnalyzer`/`ThemeAnalyzer` 전면 재작성(입력 계약이 완전히
  바뀜 - 하위 호환 없음, 사용자 승인된 결정).
- **Phase 3 (완료)**: `StockAnalyzer` 신규(기술적35+수급25+밸류에이션20+
  Sector상대강도20). 수급 25점은 종목별 투자자 매매동향 데이터가 없어 결측
  처리(호출부가 `supply_demand_score`를 0~100으로 미리 정규화해서 넘기면 반영,
  기본은 제외 후 재정규화). 밸류에이션은 Sector 중앙값이 없으면 시장 전체
  중앙값으로 자동 대체(Sector 중앙값 파이프라인은 미구현).
- **Phase 4 (완료)**: `market_intelligence/hierarchical_ranker.py`(최종 공식
  market*0.10+sector*0.20+theme*0.20+stock*0.50, 결측 레벨은 재정규화),
  `market_intelligence/collectors/hierarchical_ranking_pipeline.py`(DB 연결
  엔드투엔드), 신규 테이블 `stock_hierarchical_scores`(종목별 여러 행이 필요해
  `analysis_results`에 컬럼을 얹는 대신 별도 테이블로 분리 - `analysis_results`는
  timestamp UNIQUE라 구조적으로 안 맞음).

### Phase 5 — main.py 실배선 (완료, 라이브 검증 필요) [2026-08-23 세션 2]
- `run_analysis_cycle()`의 종목별 루프가 TechnicalAnalyzer용으로 이미 받던
  `kis_client.get_stock_daily_chart()` 응답을 `chart_to_price_rows()`로 변환해
  누적(`price_rows`) → 루프 종료 후 `run_full_price_history_pipeline(records=...)`로
  DB 저장(API 재호출 없음, 신규 `records` 파라미터) → 저장이 끝난 뒤(DB가 최신
  상태가 된 뒤) `run_hierarchical_ranking_pipeline(price_history=None)`으로 DB를
  다시 읽어 계층형 순위 계산 + 저장, 순서로 배선했다.
- `IntelligenceManager`에 등록하던 `SectorAnalyzer`/`ThemeAnalyzer`를 제거했다
  (`setup_manager_and_client()`, 7개→5개) - 이 둘은 이제 "종목별 market_data"가
  아니라 "전체 종목 price_history+mapping" 계약이라, 옛 계약으로 계속 등록해두면
  validate()가 매 종목·매 사이클 조용히 실패하기만 한다(Phase 5-11에서
  TechnicalAnalyzer가 겪었던 것과 같은 버그 패턴). `build_shared_market_data()`의
  옛 Sector/Theme 모의 데이터 키들은 이제 아무도 읽지 않는 죽은 데이터로 남겨뒀다
  (주석으로 표시, 삭제는 라이브 확인 후 별도 정리 과제).
  Step 7(flat 개별 분석기 결과)은 참고/디버깅용으로 남기고, 신규 Step 8이 계층형
  `final_score` 기준 상위/하위 10종목을 보여준다(문서 9절 "여러 순위 동시 제공").
- **이 세션도 실제 RDS/KIS API에 접근할 수 없어 이 배선을 라이브 검증하지
  못했다** - `data/price_history_collector.py`(chart_to_price_rows)와
  `market_intelligence/collectors/price_history_pipeline.py`(records 파라미터)의
  신규/변경 부분은 SQLite/Mock 단위테스트로만 검증했다. 사용자 컴퓨터에서
  소규모(시험 20종목)로 먼저 실행해 아래를 확인 후 전체(`all`)로 진행 필요:
  1. `get_stock_daily_chart()`의 dates/opens/highs/lows/closes/volumes 필드명이
     실제 응답과 맞는지(Phase 5-11부터 이어지는 기존 미검증 가정)
  2. `get_kospi_kosdaq()`의 kospi_change_rate/kosdaq_change_rate가 실제로
     채워지는지(0이면 시장 레벨 점수가 계속 중립 50 - 에러는 아니지만 로그로 확인)
  3. `stock_sector_mapping`/`stock_theme_mapping`이 비어있으면 계층형 순위 자체가
     빈 결과(Step 8이 경고만 남기고 건너뜀 - 아직 `sector_theme_importer.py`를
     안 돌렸다면 먼저 실행 필요)
  4. Step 8 로그에 찍히는 상위/하위 종목의 market/sector/theme/stock 개별 점수가
     상식적인 범위인지(예: 전 종목 시장 급락일에 market_score가 낮게 나오는지 등)
- **실제 사용자 라이브 검증에서 발견/수정한 문제 2건 (2026-08-23, 같은 세션)**:
  1. `stock_price_history`/`stock_hierarchical_scores` 테이블이 실제 RDS에 아직
     없어서(이번 세션 신규 테이블) 처음엔 실패 - 프로젝트에 이미 있던
     `create_tables.py`(`Base.metadata.create_all()`)로 해결. 기존 테이블은
     건드리지 않고 없는 테이블만 새로 만드는 안전한 방식.
  2. `stock_hierarchical_scores` INSERT가 `psycopg2.errors.InvalidSchemaName:
     schema "np" does not exist`로 실패 - 실제 원인은 `data/technical_indicators.py`
     `calculate_rsi()`가 numpy 배열 연산 결과(`numpy.float64`)를 그대로 반환해서
     StockAnalyzer의 기술적 점수를 거쳐 stock_score/final_score까지 오염시킨
     것이었다(psycopg2가 numpy 타입을 SQL 파라미터로 못 받아 에러 메시지를
     스키마명으로 잘못 파싱해 표시됨). `calculate_rsi()`에 `float()` 캐스팅을
     추가해 근본 원인을 고치고, `hierarchical_ranking_pipeline.py`의 DB 저장
     경계에도 방어적으로 `_to_float()`를 추가했다. 이 라이브 검증이 아니었으면
     SQLite 단위테스트만으로는 절대 못 잡았을 문제(SQLite는 타입에 훨씬 관대함) -
     사용자 실제 환경에서의 단계적 검증이 왜 필요한지 보여주는 사례.
- **여전히 비어있는 부분(1-2절 갭 분석 그대로)**: 종목별 외국인/기관 순매수 API
  연동(StockAnalyzer 수급 25점, 현재 결측 처리) → **Phase 5-18 완료(2026-08-24),
  위 참고**, Sector별 PER/PBR/배당 중앙값 계산(현재는 시장 전체 중앙값으로 대체)
  → **Phase 5-19 완전히 종료(2026-08-24), 아래 참고**, news_analyzer를 최종
  계층형 공식에 어떻게 반영할지 → **Phase 5-20 완전히 종료(2026-08-24), 아래
  참고 - 사용자 결정으로 완전 제거**.

### Phase 5-17 — 전체 종목(2,718개) 라이브 검증 완료 [2026-08-24]
- 사용자가 `python main.py all`로 전체 유니버스를 실행: 2,718종목 flat 분석 성공,
  2,602종목 계층형 순위 저장(Sector 11개/Theme 18개 집계), Step 8까지 에러 없이
  완주. `_MARKET_REGIME_SPAN_PCT`도 사용자가 제공한 실제 KOSPI/KOSDAQ 6일치
  등락률로 3.0→6.0으로 재조정 완료(자세한 계산 근거는
  `market_intelligence/hierarchical_ranker.py` changelog 참고).
- 관찰(버그 아님, 기록용): Step 8 상위/하위 10종목의 Sector/Theme "결측" 비중이
  높다 - 원인은 데이터 누락이 아니라 선택 효과로 보인다(Sector/Theme가 결측인
  종목은 market+stock 두 레벨만으로 재정규화되면서 분산이 큰 stock_score 비중이
  50/60≈83%까지 커져 최종 점수 분산도 커짐 → 극단값 순위에 결측 종목이 더 잘 뜸).
  지금 당장 고칠 버그로 보지 않아 손대지 않았고, 나중에 순위표를 다듬을 때 참고.
- 이걸로 Phase 5(main.py 실배선)는 완전히 종료.

### Phase 5-18 — 종목별 외국인/기관 순매수 데이터 연동 착수 [2026-08-24]
- 사용자가 "순서대로 진행하자"고 지시한 백로그의 첫 항목. `data/kis_client.py`에
  `get_investor_trend(stock_code)` 신규(API: 주식현재가 투자자/inquire-investor,
  tr_id FHKST01010900 - KIS 공식 GitHub 예제를 이 세션이 직접 fetch해서 tr_id/
  파라미터/필드명 확인 후 이식, `get_stock_daily_chart` 때와 동일한 방식이지만
  라이브 검증은 여전히 못함).
- `market_intelligence/supply_demand.py` 신규(순수 계산기) -
  `compute_supply_demand_score(investor_trend, price_rows)`가 (외국인+기관)
  순매수 "수량"(shares, 단위 명확) 합계를 같은 기간 실제 거래량 합계에 대한
  비율로 정규화해 0~100점을 낸다. 순매수 "거래대금"(_tr_pbmn) 필드는 KIS 응답의
  실제 단위(원/천원/백만원)를 라이브 검증하지 못해 의도적으로 쓰지 않았다 -
  StockAnalyzer 클래스 docstring이 이미 경고한 "시가총액별 스케일이 다른 원시
  금액을 임의로 스케일링하지 않는다" 원칙을 따름. 스케일링 폭(±10%p)은 잠정값 -
  `_MARKET_REGIME_SPAN_PCT`처럼 사용자의 실측 데이터로 나중에 재조정 필요할 수 있음.
- `main.py`의 `analyze_stock()`/`run_analysis_cycle()`을 수정해 종목별 루프
  안에서 투자자 매매동향을 추가 조회(API 호출 종목당 1회→2회, 예상 소요시간 약
  2배) → `supply_demand_scores` dict에 누적 → 기존 `valuation_by_ticker`에
  병합해 `run_hierarchical_ranking_pipeline()`으로 전달(파이프라인 시그니처
  변경 없음, 기존 배선 재사용).
- SQLite/Mock 단위테스트로만 검증(`tests/test_supply_demand.py`, 12개) - 이 세션은
  실제 KIS API에 접근할 수 없어 `get_investor_trend()`의 실제 응답 필드명은
  아직 검증 못했다. 사용자 컴퓨터에서 `pytest tests/test_supply_demand.py -v`
  실행 후, `python main.py`(시험)로 라이브 검증 필요 - 특히 다음을 확인:
  1. `get_investor_trend()`가 빈 dict({})를 계속 돌려주지 않는지(필드명이
     실제 응답과 다르면 조용히 빈 결과만 남고 예외는 안 남음 - 로그의
     "데이터 없음"/"조회 실패" 반복 여부로 확인)
  2. Step 8 표의 종목별 점수에서 수급 컴포넌트가 실제로 반영되는지(현재는
     `_fmt()`가 market/sector/theme/종목 4개만 찍으므로, 필요하면 로그에
     `supply_demand_points`도 추가로 찍어서 확인하는 게 좋음 - 이번 세션은
     기존 Step 8 표 포맷을 바꾸지 않았음)
  3. ±10%p 스케일링 폭이 실제 순매수/거래량 비율 분포에 맞는지(전 종목이
     0점/100점 근처로 쏠리면 폭이 너무 좁은 것 - market_regime span 재조정
     때와 동일한 패턴으로 대응하면 됨)

- **실제 라이브 검증 결과 (2026-08-24, 시험 20종목)**: `python main.py`로 확인 -
  20/20종목 전부 `get_investor_trend()`가 "❌ 조회 실패"/"ℹ️ 데이터 없음" 없이
  "✅ N일 투자자 매매동향 수집 완료"로 성공(응답 건수는 30일). tr_id
  FHKST01010900/필드명(stck_bsop_date, {prsn,frgn,orgn}_ntby_qty 등)이 실제
  운영 계정 응답과 맞는다는 뜻 - 이 세션이 GitHub 공식 예제만 보고 이식한
  코드가 라이브에서 첫 시도에 그대로 동작한 드문 경우(get_stock_daily_chart/
  get_kospi_kosdaq 때는 실제로 손볼 게 있었음). Step 6 소요시간도 예상대로
  약 2배로 늘어난 것을 확인.
- **전체 종목(2,718개) 검증 결과 (2026-08-24)**: `python main.py all` 실행 -
  Step 7 flat 분석 2,718/2,718종목 성공, Step 8 계층형 순위 2,602종목 저장
  (Sector 11개/Theme 18개) - **Phase 5-17(수급 연동 전) 때와 저장 종목 수가
  정확히 일치**해서, 수급 연동 추가가 실패 종목을 늘리지 않았다는 근거가 된다.
  다만 이번엔 사용자가 콘솔 로그를 파일로 남기지 않아, Step 6의 종목별
  "❌ 조회 실패"/"ℹ️  데이터 없음" 발생 건수를 정확히 세지는 못했다(사용자가
  시간 제약을 밝혀 이 카운트는 생략하기로 판단). 종목 하나의 실패가 전체를
  막지 않는 구조(`try/except` + 결측 시 재정규화) + 저장 건수 불변이라는 두
  근거를 종합해 Phase 5-18을 완료로 처리한다. 정확한 실패/결측 건수가 필요해
  지면 다음 실행을 `python main.py all *>&1 | Tee-Object full_run.log` 식으로
  로그 파일에 남기고 `Select-String`으로 카운트하면 된다(당장 급하지 않음).
- **Phase 5-18 완전히 종료.**

### Phase 5-19 — Sector별 밸류에이션 중앙값 계산 [2026-08-24]
- 사용자가 지시한 순서의 2번째 백로그 항목. 확인해 보니 소비 측
  (`market_intelligence/analyzers/stock_analyzer.py`)은 Phase 3부터 이미
  `data["sector_per_median"]` 등이 주어지면 우선 쓰고, 없으면 `market_per`(시장
  전체 중앙값)로 자동 대체하도록 설계돼 있었다("알려진 한계 2"로 이미 문서화돼
  있었음) - 이번 작업은 그 생산 측(실제 Sector 중앙값 계산)만 채웠다.
  StockAnalyzer 코드 자체는 한 줄도 안 바꿨다.
- `market_intelligence/market_valuation.py`: `calculate_medians()`에 `group_by`
  파라미터 추가(기본 "market", "sector"로도 그룹핑 가능 - 하위 호환 유지) +
  지표별 유효 표본 수(`*_valid_count`) 노출 + `build_relative_baseline()` 신규
  (PER/PBR/배당 세 지표 각각 독립적으로 "Sector 표본이 충분하면 Sector 중앙값,
  아니면 시장 전체 중앙값"을 고름 - 표본 최소 기준은 `_MIN_SECTOR_VALID_SAMPLES=5`,
  `_MARKET_REGIME_SPAN_PCT`류와 같은 성격의 잠정값).
- `market_intelligence/collectors/valuation_pipeline.py`: `data/sector_theme_importer.
  get_latest_sector_mapping()`으로 종목별 Sector를 조회해 Sector 중앙값도 함께
  계산 → 종목마다 `build_relative_baseline()`으로 기준값을 골라 이 파이프라인
  자체의 `ValuationAnalyzer` 호출(→ Step 7 flat 참고 표의 `valuation_score`)에도
  반영. `sector_mapping` 파라미터로 직접 주입 가능(테스트/재사용 대비), 기본은
  최신 배치 자동 조회.
- `db/models.py`(`StockValuation`)/`db/schema.sql`에 `sector`,
  `sector_per_median`, `sector_pbr_median`, `sector_dividend_median` 4개 컬럼
  신규(전부 nullable) - 기존 `market_per` 등 컬럼 의미는 전혀 안 바꿨다(계속
  "시장 전체 중앙값"). Sector 표본이 부족하거나 Sector 미상이면 새 컬럼은
  NULL로 남는다(0이나 시장값으로 대신 채우지 않음).
- `main.py`의 `get_latest_stock_valuations()`도 같이 수정: DB의
  `sector_per_median` 등이 NULL이면 반환하는 dict에 그 **키 자체를 아예 넣지
  않는다**(값을 None으로 넣는 게 아님) - `dict.get(key, default)`는 "키가 없을
  때만" default를 쓰기 때문에, 키를 무조건 넣으면 표본 부족으로 정당하게
  시장 중앙값으로 대체돼야 하는 종목이 오히려 기준값을 통째로 잃는(None)
  버그가 된다. 이 세션에서 직접 찾아서 미리 막은 함정.
- **⚠️ 마이그레이션 필요**: `stock_valuation` 테이블이 이미 실제 RDS에 존재해서
  `create_tables.py`(`Base.metadata.create_all()`)로는 새 컬럼이 추가되지
  않는다(신규 테이블만 만들고 기존 테이블은 안 건드림 - Phase 5 라이브 검증 때도
  이미 확인된 동작). 1회성 `migrate_add_sector_valuation_columns.py`를 신규로
  만들었다(`ALTER TABLE ... ADD COLUMN IF NOT EXISTS`, 여러 번 실행해도 안전).
  **사용자 컴퓨터에서 `python migrate_add_sector_valuation_columns.py`를 먼저
  실행해야** 그다음 `valuation_pipeline.py`가 새 컬럼에 값을 저장할 수 있다 -
  순서를 안 지키면 INSERT가 "column does not exist" 에러로 실패한다.
- 이 세션은 실제 RDS/KIS API에 접근할 수 없어 SQLite/Mock 단위테스트로만
  검증했다(`tests/test_market_valuation.py` 신규 17개 + `tests/
  test_valuation_pipeline.py`/`tests/test_db_models.py` 확장). `test_market_
  valuation.py`는 DB 의존이 없어 이 세션에서 74개 전부 통과까지 직접 확인했다
  (`test_valuation_pipeline.py`/`test_db_models.py`는 sqlalchemy가 이 샌드박스에
  없어 실행은 못 했다 - 기존 관례와 동일).
  **사용자 컴퓨터에서 확인 순서**:
  1. `python migrate_add_sector_valuation_columns.py` (컬럼 추가, 1회성)
  2. `pytest tests/test_market_valuation.py tests/test_valuation_pipeline.py
     tests/test_db_models.py -v`
  3. `valuation_pipeline.py`를 한 번 돌려(전체 또는 시험) `stock_valuation`에
     `sector_per_median` 등이 실제로 채워지는지 확인
  4. `python main.py`(시험 20종목)로 Step 8 밸류에이션 컴포넌트가 여전히
     정상 범위인지 확인 → 문제 없으면 `python main.py all`로 전체 검증

- **실제 라이브 검증 결과 (2026-08-24)**:
  1. 마이그레이션 성공 - `python migrate_add_sector_valuation_columns.py`
     (첫 시도는 RDS 연결이 일시적으로 타임아웃, 재시도로 성공 - 아래
     "RDS 일시적 지연" 참고) 실행 후 4개 컬럼 실제 RDS에 추가 확인.
  2. `pytest tests/test_market_valuation.py tests/test_valuation_pipeline.py
     tests/test_db_models.py -v` - 총 33개 중 1개 실패
     (`test_sector_with_too_few_stocks_leaves_sector_columns_null` - Sector
     표본이 5개 미만인데도 `valuation_pipeline.py`가 threshold 체크 없이
     원본 Sector 중앙값을 그대로 DB에 써버리는 실제 버그를 테스트가 잡았다).
     `MarketValuation.get_reliable_sector_medians()`로 threshold 체크 로직을
     단일화(`build_relative_baseline()`과 DB 저장 경로가 같은 함수를 쓰도록)해
     수정 → 재실행 33/33 전부 통과.
  3. `python -m market_intelligence.collectors.valuation_pipeline`(시험
     20종목) 실행 중 `get_latest_sector_mapping()`에서 5분+ 원인불명 행이
     발생(Ctrl+C도 안 먹힘) - `diagnose_db_lock.py` 신규 작성(각 진단
     쿼리에 `statement_timeout=5초` 걸어서 실행)으로 `pg_locks`/
     `pg_stat_activity` 확인 결과 락/블로킹 세션 없음, CloudWatch로
     CPU 크레딧/사용률/커넥션 수도 전부 정상 확인 → 일회성 네트워크/DB
     순간 지연으로 결론(코드 버그 아님, 같은 날 있었던 마이그레이션
     타임아웃과 같은 패턴). 재시도 시 13초 만에 정상 완료(20종목 수집,
     DB 저장 20건, Sector 중앙값 6개 카테고리). 원인 확인용으로 잠깐
     추가했던 진단용 `print()` 5개는 이후 제거.
  4. `python main.py`(시험 20종목) - Step 1~8 전부 에러 없이 완료. Step
     6-2 계층형 랭킹은 전체 유니버스를 훑기 때문에, 아직 이 20종목만
     밸류에이션이 최신인 상태에서는 나머지 종목에 대해 예상대로 대량의
     "상대평가 가능한 지표 없음" 경고가 발생(설계대로 - 전체 배치를
     아직 안 돌렸으니 당연함).
  5. `python -m market_intelligence.collectors.valuation_pipeline all`
     (전체 2,718종목) - 2,718/2,718 수집 및 DB 저장 성공(경과 약 27.6분),
     Sector 중앙값 **12개 카테고리** 산출(시험 때 6개 → 표본이 늘며 증가,
     정상). 파이프라인 자체의 `ValuationAnalyzer` 계산 중 약 150개
     종목에서 "상대평가 가능한 지표 없음" 경고가 남았는데, 티커 패턴을
     보면(`0120G0`, `33626K` 등 숫자+영문 혼합) ETN/신주인수권 등
     일반 보통주가 아닌 종목으로 보이며 PER/PBR 자체가 없거나 market
     분류가 불명확한 기존 데이터 성격의 한계 - Phase 5-19가 새로 만든
     문제 아님, DB 저장 자체는 2,718건 전부 성공.
  6. `python main.py all`(전체 2,718종목, 최종 검증) - **Step 7 flat**:
     2,718/2,718종목 분석 성공, 평균 56.24점(범위 48.73~66.05). **Step 8
     계층형**: 2,603종목 순위 저장(Sector 11개/Theme 18개), 평균
     45.44점(범위 10.87~89.04, 시험 때보다 분산이 커짐 - 전체 유니버스가
     실제 Sector 밸류에이션 기준값을 갖게 되며 종목 간 차이가 더 잘
     드러난 것으로 해석). Step 6-2에서 남은 "상대평가 가능한 지표 없음"
     경고는 위 5번의 ~150개 예외 종목 수준으로 줄어듦(이전 트라이얼
     때의 "나머지 2,698종목 전부" 대량 경고와 대조) - Phase 5-19가
     의도한 대로 동작함을 확인. 에러 없이 "✅ 분석 사이클 완료".
  - **관찰(버그 아님, Phase 5-17에서 이미 문서화된 것과 같은 현상)**:
    Step 8 상위/하위 10종목 표에 "Sector= 결측"이 자주 보이는데, 이는
    이 Phase의 `sector_per_median`(밸류에이션 기준값) 컬럼과는 다른
    개념 - SectorAnalyzer가 쓰는 Sector "그룹 소속" 자체가 없는
    종목이라는 뜻이다(11개 Sector 그룹 중 어디에도 안 걸리는 종목).
    Phase 5-17 라이브 검증 때 이미 "선택 효과"(Sector/Theme 결측 종목은
    분산이 큰 stock_score 비중이 커져 극단값 순위에 더 잘 뜬다)로
    설명된 것과 동일 현상 - Phase 5-19와 무관, 지금 손대지 않음.
- **Phase 5-19 완전히 종료.**

### Phase 5-20 — news_analyzer의 최종 공식 내 처리 방식 결정 [2026-08-24]
- 사용자가 지시한 순서의 3번째(마지막) 백로그 항목. `market_intelligence/
  analyzers/news_analyzer.py`(`NewsAnalyzer`)를 확인한 결과 두 가지가
  드러났다.
  1. 계층형 최종 공식(`StockAnalyzer`, 시장10%/Sector20%/Theme20%/종목50%)에는
     애초에 뉴스 컴포넌트가 없다 - 방법론 문서의 종목 100점 배점(기술적35+
     수급25+밸류에이션20+Sector상대강도20)에 뉴스 자리가 없고, `stock_analyzer.py`
     코드에도 news 관련 참조가 전혀 없다. `NewsAnalyzer`는 `main.py`의 flat
     7→5→4개 analyzer 등록(Step 7 "참고용" 표, 계층형과 무관)에만 쓰이고 있었다.
  2. `NewsAnalyzer`에 들어가는 입력이 `main.py`의 `build_shared_market_data()`에
     하드코딩된 **전 종목·전 사이클 동일한 모의값**이었다(`news_sentiment_score:
     48.6` 등, 실제 뉴스 API 미연동) - 즉 살려둬도 종목 간 차이를 전혀 만들지
     못하고 모든 종목에 똑같은 상수만 더하는 상태였다. 이 프로젝트가 지켜온
     "결측 시 재정규화, 절대 임의값으로 채우지 않는다" 원칙과 충돌하는
     지점이라 이 세션이 임의로 결정하지 않고 AskUserQuestion으로 3개 선택지
     (① flat 참고표에만 유지 ② stock 100점에 자리 마련 ③ 완전 제거)를 제시,
     **사용자가 "③ 완전 제거"로 결정**.
- 구현: `market_intelligence/analyzers/news_analyzer.py` 파일 삭제,
  `market_intelligence/analyzers/__init__.py`의 import/`__all__`에서 제거,
  `main.py`에서 import/`setup_manager_and_client()`의 `register_analyzer`
  호출/`build_shared_market_data()`의 뉴스 모의 데이터 8개 키 전부 삭제
  (flat analyzer 등록 수 5→4, weight 합 안내 로그도 갱신), `tests/
  test_analyzers.py`에서 `TestNewsAnalyzer` 클래스 및 `TestAllAnalyzers`의
  참조/weight 합 갱신(1.12→1.03).
- `db/models.py`의 `NewsFeed` 테이블(실제 뉴스 기사 원문 저장용,
  `sentiment_score` 컬럼 포함)은 `NewsAnalyzer`와 무관한 별도 인프라라 그대로
  두었다 - 나중에 진짜 뉴스 API를 연동할 때 그 테이블에서 읽어와 새 analyzer를
  설계하면 된다.
- 검증(1차, 세션 내): `tests/test_analyzers.py` 전체(10개, `TestNewsAnalyzer`
  제거 후) + 기존 74개(`test_market_valuation.py` 등) 합쳐 그대로 전부 통과
  확인(sqlalchemy 불필요한 파일들만 - 기존 관례와 동일, `test_valuation_
  pipeline.py`/`test_db_models.py`는 여전히 사용자 환경 실행 필요). `main.py`
  자체는 sqlalchemy 의존 때문에 이 세션에서 임포트까지는 못 했고 `ast.parse`로
  문법만 확인.
- **검증(2차, 실제 라이브 - 완료)**: 사용자 컴퓨터에서 아래 두 단계 모두
  성공 확인.
  1. `pytest tests/test_analyzers.py -v` → **10 passed, 1 warning
     (0.40s)**. 경고는 `.pytest_cache` 디렉토리 관련 무해한
     `PytestCacheWarning`(`[WinError 183]`)으로 이번 변경과 무관.
  2. `python main.py`(시험, 20종목) → Step 2 로그에 "4개 분석기 등록 중
     (Sector/Theme는 계층형 순위 파이프라인에서 별도 실행)..."으로 정확히
     4개(market 0.30/moneyflow 0.14/technical 0.18/valuation 0.09) 등록
     확인, Step 6 "종목별 4개 분석기 실행 중" 및 종목별 `Running 4
     analyzers...` 로그로 뉴스 없이 4개만 도는 것 확인. Step 7(flat 참고표)
     20/20 성공, 평균 57.13점(범위 47.85~63.57) - weight 합이 1.12→1.03으로
     바뀐 데 따른 자연스러운 수치 변화(버그 아님). Step 8(계층형) 2,603종목
     평균 46.05점(범위 21.00~77.87), 에러 0건, "✅ 분석 사이클 완료"로 정상
     종료. NewsAnalyzer 제거 후에도 Step 6/Step 7이 에러 없이 4개
     분석기로 정상 완주함을 확인.
- **Phase 5-20 완전히 종료 - 이걸로 사용자가 지시한 3개 백로그 항목
  (수급 연동/Sector 중앙값/뉴스 처리 방식) 전부 완료, 전부 라이브 검증까지
  끝남.**

### Phase 5-21 — 밸류에이션/배당 수집을 EC2로 이관 (무중단화) [2026-08-24]
- 배경: EC2 서버(`journalctl`/`data/krx/{incoming,latest,archive}` 확인 결과)에서
  `main.py serve`(일마감 분석, 평일 19:00 KST)는 정상적으로 상시 동작 중이었으나,
  그 분석이 읽는 `stock_valuation` DB 테이블을 채우는 `market_intelligence/
  collectors/valuation_pipeline.py`(PER/PBR은 KIS API, 배당수익률은
  `data/krx_importer.py`가 처리한 KRX CSV)는 지금까지 **사용자 컴퓨터에서
  수동 실행**해온 완전히 별개의 배치였다. EC2의 `data/krx/incoming|latest|
  archive`가 전부 `.gitkeep`만 있는 빈 상태였던 것으로 확인 - EC2 자체는 이
  수집 파이프라인을 단 한 번도 실행한 적이 없었다. 즉 "일마감 분석"만
  무중단이었고, 그 원재료 수집은 사용자 컴퓨터가 켜져 있어야만 돌아가는
  구조였다. 사용자가 이 수집 단계도 EC2로 이관하는 작업을 명시적으로
  지시함.
- 구현(`deploy/` 디렉토리에 기존 `mie-v2.service` 패턴을 따라 4개 신규 유닛
  파일 추가, 전부 systemd oneshot service + timer 쌍):
  1. `mie-v2-krx-import.service`/`.timer` - `python -m data.krx_importer`를
     평일 15분 간격으로 실행(`incoming/`이 비어있으면 즉시 종료되는 가벼운
     스캔이라 부담 없음). 사람이 KRX 사이트에서 CSV를 다운로드해 EC2의
     `data/krx/incoming/`에 올리기만 하면(다운로드 자체는 KRX 안티봇 조치로
     여전히 자동화 불가 - Phase 5-8 결정 그대로 유지) 최대 15분 안에 자동으로
     검증·반영됨.
  2. `mie-v2-valuation.service`/`.timer` - `python -m market_intelligence.
     collectors.valuation_pipeline all`을 평일 18:00 KST에 1회 실행(전종목
     실측 소요시간 약 27~28분, Phase 5-19 라이브 검증 기준). `main.py serve`의
     19:00 KST 일마감 분석보다 1시간 앞서 끝나도록 여유를 둠.
  3. 타임존: 서버의 시스템 타임존이 UTC인지 KST인지 이 세션에서 확인할 방법이
     없어(SSH/AWS API 접근 불가), 서버 기본 타임존과 무관하게 항상 KST로
     평가되도록 `OnCalendar=... Asia/Seoul` 문법(systemd 239+)을 명시적으로
     사용함 - 요일(월~금) 판정도 이 타임존 기준으로 맞아야 하므로 필수.
  4. `TimeoutStartSec=3600`(valuation 서비스) - 전종목 수집이 30분 내외
     걸리므로 systemd 기본 타임아웃보다 넉넉하게 잡음.
- **아직 EC2에 설치되지 않음 - 다음 단계로 사용자가 EC2에서 직접 1회 실행
  필요**(이 세션은 SSH/AWS API 접근이 없어 대신 실행할 수 없음):
  ```
  cd /opt/mie-v2
  sudo cp deploy/mie-v2-krx-import.service deploy/mie-v2-krx-import.timer \
          deploy/mie-v2-valuation.service deploy/mie-v2-valuation.timer \
          /etc/systemd/system/
  sudo systemctl daemon-reload
  sudo systemctl enable --now mie-v2-krx-import.timer
  sudo systemctl enable --now mie-v2-valuation.timer
  systemctl list-timers | grep mie-v2
  ```
  (`deploy.sh`가 git으로 관리되지 않고 EC2에만 존재해서 배포 자동화에 이
  유닛 파일들을 자동 반영하도록 편입할지는 별도 판단 필요 - 일단은 위 1회
  설치로 충분하고, 이후 재배포(`deploy.sh`)는 기존 `mie-v2.service`만
  건드리므로 이 신규 타이머들에는 영향 없음.)
- 검증 필요(사용자 컴퓨터에서 진행 불가 - 반드시 EC2 서버에서): 위 설치
  명령 실행 후 (1) `systemctl list-timers`로 다음 실행 예정 시각이 KST
  기준으로 맞는지 확인, (2) 다음 KRX CSV를 실제로 `incoming/`에 올려서
  15분 이내 `latest/`에 반영되는지 확인(`/var/log/mie-v2/krx_import.log`),
  (3) 18:00 KST 이후 `/var/log/mie-v2/valuation.log`에서 전종목 수집이
  정상 완료됐는지, RDS `stock_valuation` 테이블의 배당수익률 컬럼이 그날
  갱신됐는지 확인.
- **검증 완료(2026-08-24, 사용자 EC2에서 직접)**: 설치 명령 실행 →
  `mie-v2-krx-import.timer`/`mie-v2-valuation.timer` 둘 다 enable 성공,
  `systemctl list-timers`로 다음 실행 예정 시각이 KST 기준(각각 15분 후,
  익일 18:00)으로 정확히 나오는 것 확인 - 서버 시스템 타임존이 실제로
  UTC임에도 `Asia/Seoul` 명시 덕에 KST로 정확히 스케줄링됨을 확인. 15분 뒤
  krx-import 타이머가 실행되어 `/var/log/mie-v2/krx_import.log`에
  "incoming/ 폴더에 처리할 CSV가 없습니다"가 에러 없이 찍힘(당시 incoming/이
  실제로 비어있었으므로 정상 동작).
- **Phase 5-21 완전히 종료(설치·기본 동작 검증까지 끝남). 실제 CSV
  임포트/밸류에이션 수집 성공 여부는 Phase 5-22(아래) 이후 실데이터로 다시
  확인.**

### Phase 5-22 — 로컬(Windows) → EC2 CSV 자동 전송 (scp 자동화) [2026-08-24]
- 배경: Phase 5-21 검증 중 사용자가 KRX CSV를 `C:\Projects\trading-mie-v2\
  data\krx\incoming`(Windows 로컬 저장소 폴더)에 넣었는데 EC2가 못 찾는
  문제가 발생. 원인은 EC2와 Windows가 완전히 별개의 파일시스템이라는 것 -
  `git push`는 소스 코드만 옮기고 데이터 파일(`data/krx/`)은 안 옮기므로,
  CSV를 실제로 importer가 도는 EC2의 `/opt/mie-v2/data/krx/incoming/`에
  직접 갖다 놔야 한다. 예전(Phase 5-8)엔 사람이 수동 실행하는 컴퓨터가
  Windows였으니 문제가 없었지만, Phase 5-21로 importer가 EC2로 옮겨가면서
  "다운로드한 파일을 EC2까지 옮기는" 한 단계가 새로 필요해짐. 사용자가
  "로컬 PC에 미리 넣어두면 자동으로 EC2까지 가져가서 쓰게" 자동화를 요청.
- 설계: KRX 사이트에서의 다운로드 자체는 여전히 사람이 해야 한다(안티봇
  조치로 자동화 불가 - Phase 5-8 결정 그대로 유지). 그 다음 "로컬 →
  EC2 전송"만 자동화한다.
  1. `scripts/windows/sync_krx_to_ec2.ps1` - 로컬 `data/krx/incoming/`에서
     파일명에 kospi/kosdaq이 들어간 `.csv` 중 최종 수정 후 30초 이상 지난
     파일(다운로드 도중인 파일을 잘못 집지 않기 위한 안전장치)을 찾아
     `scp`로 EC2의 `/opt/mie-v2/data/krx/incoming/`에 전송하고, 성공한
     파일은 로컬 `data/krx/incoming/_sent/`로 옮겨 중복 전송을 막는다.
     실패하면 파일을 그대로 둬서 다음 실행 때 재시도된다. 모든 시도를
     `logs/krx_sync.log`에 기록.
  2. `scripts/windows/register_krx_sync_task.ps1` - 위 스크립트를 Windows
     작업 스케줄러에 평일 15:00~20:00, 10분 간격 반복 작업으로 1회 등록하는
     헬퍼(관리자 권한 PowerShell에서 1회 실행). EC2의
     `mie-v2-valuation.timer`(18:00 KST)보다 여유있게 앞뒤로 걸치는 창.
  3. `sync_krx_to_ec2.ps1` 상단의 `Ec2Host`/`SshKeyPath`는 자리표시자
     (`REPLACE_ME`)로 커밋함 - 사용자 개인 SSH 키 경로/EC2 주소는 이
     세션이 알 수 없고 민감정보라 실제 값은 사용자가 직접 채워 넣어야 함.
- **한계(사용자에게 명시적으로 안내 필요)**: 이 자동화는 EC2의 systemd
  타이머와 달리 **Windows PC가 그 시간대에 켜져 있고 로그온돼 있어야만**
  동작한다. 다만 KRX 다운로드 자체가 애초에 사람이 그 시간대에 PC를 쓰고
  있어야 하는 작업이라, 이 제약이 워크플로에 새로운 제약을 추가하는 건
  아니다 - 단지 "옮긴 뒤 수동으로 scp 명령 치기"를 없애주는 정도.
- 검증 필요(이 세션은 사용자 컴퓨터에서 실행할 수 없음 - SSH 키 등록,
  Windows PowerShell 실행 정책 등 사용자 환경 의존): (1)
  `sync_krx_to_ec2.ps1` 상단 설정값을 실제 값으로 채운 뒤 CSV 1개로 수동
  실행(`powershell -File sync_krx_to_ec2.ps1`)해서 EC2로 정상 전송되고
  `_sent/`로 이동하는지, (2) `register_krx_sync_task.ps1`로 작업 스케줄러
  등록 후 `Start-ScheduledTask`로 1회 강제 실행해 같은 결과가 나오는지,
  (3) EC2 쪽 `mie-v2-krx-import.timer`가 15분 내에 `krx_import.log`에
  실제 반영 로그를 남기는지.
- **Phase 5-22 구현 완료, 사용자 환경 설정 및 라이브 검증 대기 중.**

## 4. 리스크 / 미확정 사항
- Sector별 PER 중앙값 계산 → **Phase 5-19 완전히 종료(2026-08-24)** -
  마이그레이션/단위테스트/시험(20종목)/전체(2,718종목) 라이브 검증까지
  전부 완료. 위 "실제 라이브 검증 결과" 참고.
- 이 세션은 실제 PostgreSQL/KIS API에 접근할 수 없어 모든 신규 코드는 SQLite
  단위테스트 + 코드 리뷰로만 검증되고, 라이브 검증은 사용자 환경에서 필요
  (기존 관례와 동일).
