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
    한 번만 실행 - 실시간 매수/매도 자동주문 루프(별도 프로세스, 이번
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
    마지막 완료 날짜를 기록해두고, (a) 오늘 아직 미완료 + 이미 19시가
    지났으면 즉시 실행, (b) 어제치도 없이 하루 이상 밀렸으면 시각과
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

from market_intelligence.intelligence_manager import IntelligenceManager
from market_intelligence.analyzers import (
    MarketAnalyzer,
    SectorAnalyzer,
    MoneyFlowAnalyzer,
    ThemeAnalyzer,
    NewsAnalyzer,
    TechnicalAnalyzer,
    ValuationAnalyzer
)
from data.kis_client import KISClient

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

_DEFAULT_TRIAL_STOCK_COUNT = 20  # 안전을 위한 기본값(valuation_pipeline.py와 동일한 관례)

# ============ 상시 서비스 모드(serve) 설정 ============
KST = ZoneInfo("Asia/Seoul")
_DAILY_RUN_HOUR = 19    # 일마감 분석 목표 시각(KST) - 사용자 지정
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
    나머지 6개 분석기(Market/Sector/MoneyFlow/Theme/News/Technical)는 아직 종목별
    실데이터가 없으므로 시장 전체 기준의 값을 그대로 모든 종목에 공통으로 쓴다.
    """
    if real_data is None:
        logger.warning("실제 데이터 없음 - 완전 모의 데이터로 진행")
        real_data = {}

    return {
        # ============ MarketAnalyzer (실제 데이터) ============
        "kospi_index": real_data.get('kospi_index', 6258.77),
        "kosdaq_index": real_data.get('kosdaq_index', 798.81),
        "market_volume": real_data.get('market_volume', 1350000000),

        # ============ SectorAnalyzer (모의 데이터 - 아직 종목별 업종매핑 없음) ============
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

        # ============ ThemeAnalyzer (모의 데이터) ============
        "geopolitical_risk": 35,
        "ai_semiconductor": 42,
        "esg_battery": 62,
        "value_buying": 68,
        "economic_recovery": 48,
        "tech_innovation": 65,

        # ============ NewsAnalyzer (모의 데이터) ============
        "positive_news_count": 5,
        "neutral_news_count": 7,
        "negative_news_count": 6,
        "total_news_count": 18,
        "critical_disclosure_count": 0,
        "important_disclosure_count": 1,
        "minor_disclosure_count": 2,
        "news_sentiment_score": 48.6,

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
    PER/PBR/배당수익률 + 시장 중앙값을 읽어온다. valuation_pipeline.py가 이미 시장
    중앙값(market_per 등)까지 계산해서 저장해두므로 여기서 다시 계산하지 않는다.

    limit을 주면(기본 실행 시 안전을 위해 20종목만) 종목코드 순 정렬 후 앞쪽만
    가져온다 - 'all'로 실행할 때는 limit=None이라 전체를 가져온다.
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

    return [
        {
            "symbol": row.ticker,
            "market": row.market,
            "per": _f(row.per),
            "pbr": _f(row.pbr),
            "dividend_yield": _f(row.dividend_yield),
            "market_per": _f(row.market_per),
            "market_pbr": _f(row.market_pbr),
            "market_dividend_yield": _f(row.market_dividend_yield),
        }
        for row in query.all()
    ]


def analyze_stock(manager: IntelligenceManager, shared_data: Dict[str, Any],
                   stock_row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """시장 공통 데이터(shared_data)에 종목별 밸류에이션 실데이터(stock_row)를 덮어씌워
    7개 분석기를 한 번 실행한다. 실패해도 전체 루프를 막지 않도록 예외를 잡아 None을
    돌려준다(호출부에서 건너뜀)."""
    market_data = {**shared_data, **stock_row}
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


def setup_manager_and_client():
    """IntelligenceManager 초기화 + 7개 분석기 등록 + 공유 KISClient 준비.

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

    logger.info("\n【Step 2】7개 분석기 등록 중...")
    analyzers = [
        MarketAnalyzer(kis_client=kis_client),
        SectorAnalyzer(),
        MoneyFlowAnalyzer(),
        ThemeAnalyzer(),
        NewsAnalyzer(),
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

    logger.info("\n【Step 6】종목별 7개 분석기 실행 중...")
    results = []
    for stock_row in stock_rows:
        result = analyze_stock(manager, shared_data, stock_row)
        if result is not None:
            results.append(result)

    if not results:
        logger.error("❌ 분석에 성공한 종목이 하나도 없습니다.")
        return False

    # 7. 결과 요약
    logger.info("\n" + "=" * 80)
    logger.info("【Step 7】종목별 분석 결과 요약")
    logger.info("=" * 80)

    scores = [r["final_score"] for r in results]
    logger.info(f"분석 성공: {len(results)}/{len(stock_rows)}종목")
    logger.info(f"평균 점수: {sum(scores) / len(scores):.2f}점")
    logger.info(f"최고 점수: {max(scores):.2f}점 / 최저 점수: {min(scores):.2f}점")

    ranked = sorted(results, key=lambda r: r["final_score"], reverse=True)
    top_n = min(10, len(ranked))
    _print_summary_table(f"상위 {top_n}종목 (매수 후보)", ranked[:top_n])
    _print_summary_table(f"하위 {top_n}종목 (매도/회피 후보)", ranked[-top_n:][::-1])

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
    - 그 외(마지막 완료일이 어제, 오늘 몫만 밀림) -> 오늘 목표 시각(19:00
      KST)이 지났으면 실행
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

    # last_date == yesterday: 오늘 몫만 밀린 상태 - 목표 시각(19:00) 이후인지 확인
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

    평일 KST 19:00에 하루 한 번 전체 종목(all) 분석 사이클을 실행하고, 완료
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
    logger.info("🎊 MIE V2.0 - 상시 서비스 모드 시작 (일마감 분석, 평일 19:00 KST)")
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
