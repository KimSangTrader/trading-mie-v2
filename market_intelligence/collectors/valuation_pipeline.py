"""
ValuationPipeline - 종목마스터→PER/PBR수집→시장중앙값→상대평가→DB저장 엔드투엔드 (Phase 5-7)

================================================================================
【변경 이력】
================================================================================
【2026-08-16】최초 생성
- 배경: data/stock_master.py(종목마스터), valuation_collector.py(PER/PBR 수집),
  market_valuation.py(시장 중앙값), valuation_analyzer.py(종목별 상대평가), 그리고
  db/models.py의 StockValuation 테이블까지는 각각 개별적으로 만들고 검증했지만,
  이 다섯 조각을 실제로 이어서 "수집한 데이터를 DB에 저장"까지 하는 코드는
  아직 없었다. 이 모듈이 그 이어붙이는 역할을 한다.
- 흐름: StockMaster.get_stock_list() → ValuationCollector.get_or_collect() →
  MarketValuation.calculate_medians()로 시장(KOSPI/KOSDAQ)별 중앙값 계산 →
  종목마다 ValuationAnalyzer.run()으로 상대점수 산출 → StockValuation 행으로
  변환해 세션에 add → 한 번에 commit.
- 한 번의 파이프라인 실행(배치)에 포함된 모든 행은 동일한 timestamp를 공유한다
  (sector_data와 같은 패턴 - "이 시각의 전체 스냅샷"을 timestamp 하나로 조회할
  수 있어야 하므로, 각 행이 SQLAlchemy 기본값으로 개별적으로 시각을 받지 않고
  파이프라인 시작 시점에 한 번만 계산한 값을 명시적으로 넣는다).
- DB 세션(session)과 커밋 시점은 호출부 책임으로 남겨둔다 (테스트에서 SQLite
  in-memory 세션을 주입할 수 있어야 하고, 실패 시 롤백 정책도 호출부가 정할 문제).
- 이 세션은 sqlalchemy가 설치되어 있지 않아(PyPI 네트워크 차단) 직접 실행 검증을
  못 했다. tests/test_valuation_pipeline.py를 사용자 컴퓨터에서 실행해 확인 필요.

【2026-08-24】Phase 5-19: Sector별 밸류에이션 중앙값 반영
- data/sector_theme_importer.py의 get_latest_sector_mapping()으로 최신 종목별
  Sector 매핑을 읽어와(파라미터로 직접 넘길 수도 있음 - 테스트/재사용 대비)
  각 레코드에 "sector"를 붙인 뒤, market 중앙값과 별개로 Sector별 중앙값도
  MarketValuation.calculate_medians(group_by="sector")로 계산한다.
- 종목별 기준값은 MarketValuation.build_relative_baseline()으로 결정한다 -
  PER/PBR/배당 세 지표 각각 독립적으로 "Sector 표본이 충분하면 Sector 중앙값,
  아니면 시장 전체 중앙값"을 고른다(자세한 원칙은 market_valuation.py 참고).
  이렇게 고른 기준값을 이 파이프라인 자체의 ValuationAnalyzer.run() 호출에도
  그대로 써서, 이 테이블(stock_valuation)에 저장되는 valuation_score/
  per_relative_score 등도 처음부터 Sector 우선 기준으로 계산된다(Step 7 flat
  참고 표와 Step 8 계층형 StockAnalyzer가 서로 다른 기준값을 쓰는 혼란 방지).
- StockValuation 신규 컬럼(sector/sector_per_median/sector_pbr_median/
  sector_dividend_median)에는 실제 계산된 Sector 중앙값만 저장한다 - 표본
  부족/Sector 미상으로 대체된 경우는 NULL로 남긴다(0이나 시장값을 대신 채우지
  않음 - main.py의 get_latest_stock_valuations()가 이 NULL 여부로 StockAnalyzer의
  자동 fallback을 그대로 살려서 넘긴다).

【2026-08-24】임시 진단용 print() 5개 제거
- 배경: 라이브 검증(20종목 시험) 중 get_latest_sector_mapping() 호출이 5분+
  원인불명으로 멈추는 현상이 있어, 각 단계 진입/완료 시점을 눈으로 보려고
  "🔧 [진단] ..." print()를 5곳(함수 진입, stock_list 확보 후, collector 준비
  후, sector_mapping 조회 후, collect() 완료 후)에 임시로 추가했었다.
- diagnose_db_lock.py(pg_locks/pg_stat_activity 점검, 0.1초 내 전부 정상 응답)와
  CloudWatch(CPU 크레딧/사용률/커넥션 수 모두 정상)로 DB 락/과부하 가능성을
  배제했고, 재시도 시 13초 만에 정상 완료되어 일회성 네트워크/DB 순간 지연으로
  결론지었다(코드 버그 아님 - 같은 날 발생한 ALTER TABLE 타임아웃과 같은 패턴).
  원인이 코드가 아닌 것으로 확인되어 진단용 print() 5개를 전부 제거한다
  (운영 로직 변경 없음).
================================================================================
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def run_full_valuation_pipeline(
    session,
    stock_list: Optional[List[Dict[str, Any]]] = None,
    stock_master: Optional[Any] = None,
    collector: Optional[Any] = None,
    sector_mapping: Optional[List[Dict[str, Any]]] = None,
    force_refresh: bool = False,
    rate_limit_sec: float = 0.2,
    checkpoint_every: int = 50,
    progress_callback: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    KOSPI/KOSDAQ 종목 → PER/PBR 수집 → 시장별/Sector별 중앙값 → 종목별 상대평가 →
    DB(stock_valuation 테이블)에 저장까지 한 번에 수행한다.

    Args:
        session: SQLAlchemy Session. 이 함수 안에서 add()와 commit()까지 하지만,
            세션 생성/종료(close)는 호출부 책임이다.
        stock_list: 직접 넘기면 이 목록만 처리한다(테스트, 부분 실행용).
            None이면 stock_master.get_stock_list(market="ALL", common_stock_only=True)로
            KOSPI/KOSDAQ 전체 보통주를 가져온다.
        stock_master / collector: 테스트에서 Mock으로 교체하기 위한 주입 지점.
            None이면 각각 StockMaster(), ValuationCollector()를 새로 만든다
            (collector는 실제 KISClient를 필요로 하므로, 이 지연 임포트는
            테스트가 KIS 인증 없이도 MockValuationCollector만으로 돌 수 있게 해준다).
        sector_mapping: 종목별 Sector 매핑(get_latest_sector_mapping()과 동일한
            [{"ticker":, "sector":, ...}] 형식). None이면 이 세션으로
            data/sector_theme_importer.get_latest_sector_mapping()을 호출해 최신
            배치를 읽는다. 매핑이 비어 있으면(아직 sector_theme_importer.py를
            안 돌렸으면) Sector 중앙값 없이 전부 시장 전체 중앙값으로 대체된다
            (기존 동작과 동일 - 하위 호환).

    Returns:
        {"total": 처리한 종목 수, "saved": DB에 저장한 행 수,
         "market_medians": {...}, "sector_medians": {...}}
        stock_list와 stock_master.get_stock_list() 결과가 모두 비어 있으면
        {"total": 0, "saved": 0} (medians 없음, DB 접근도 하지 않음)
    """
    if stock_list is None:
        if stock_master is None:
            from data.stock_master import StockMaster
            stock_master = StockMaster()
        stock_list = stock_master.get_stock_list(market="ALL", common_stock_only=True)

    if not stock_list:
        logger.warning("⚠️  처리할 종목이 없습니다 (빈 stock_list) - 파이프라인 중단")
        return {"total": 0, "saved": 0}

    if collector is None:
        from market_intelligence.collectors.valuation_collector import ValuationCollector
        collector = ValuationCollector()

    if sector_mapping is None:
        from data.sector_theme_importer import get_latest_sector_mapping
        sector_mapping = get_latest_sector_mapping(session)

    from market_intelligence.market_valuation import MarketValuation
    from market_intelligence.analyzers.valuation_analyzer import ValuationAnalyzer
    from db.models import StockValuation

    sector_by_ticker = {
        row["ticker"]: row["sector"] for row in sector_mapping if row.get("sector")
    }
    if not sector_by_ticker:
        logger.info("ℹ️  Sector 매핑이 비어 있습니다 - 이번 배치는 전부 시장 전체 "
                     "중앙값으로 계산됩니다 (sector_theme_importer.py 실행 여부 확인)")

    records = collector.get_or_collect(
        stock_list,
        force_refresh=force_refresh,
        rate_limit_sec=rate_limit_sec,
        checkpoint_every=checkpoint_every,
        progress_callback=progress_callback,
    )

    for record in records:
        record["sector"] = sector_by_ticker.get(record.get("symbol"))

    market_medians = MarketValuation.calculate_medians(records, group_by="market")
    sector_records = [r for r in records if r.get("sector")]
    sector_medians = MarketValuation.calculate_medians(sector_records, group_by="sector")

    analyzer = ValuationAnalyzer()
    batch_timestamp = datetime.now(timezone.utc)

    saved = 0
    for record in records:
        market = record.get("market")
        sector = record.get("sector")
        baseline, _baseline_source = MarketValuation.build_relative_baseline(
            sector_medians, market_medians, sector, market
        )
        analyzer_input = {
            "symbol": record.get("symbol"),
            "market": market,
            "per": record.get("per"),
            "pbr": record.get("pbr"),
            "dividend_yield": record.get("dividend_yield"),
            **baseline,
        }
        result = analyzer.run(analyzer_input)
        details = result.get("details", {})

        # 【2026-08-24 수정, 이 세션이 단위테스트로 직접 잡은 버그】처음엔 여기서
        # sector_medians[sector]의 원값(raw)을 그대로 저장했었다 - 표본이 1~2개뿐인
        # Sector도 "중앙값"은 계산되기 때문에(그냥 그 종목 자신의 값과 다름없는데도)
        # 신뢰 가능한 값처럼 DB에 저장돼버리는 문제가 있었다. build_relative_baseline()
        # 안에서만 표본 수 임계값을 체크하고 DB 저장 시점엔 체크를 빼먹은 것 - 반드시
        # get_reliable_sector_medians()를 거쳐서, 표본 부족/Sector 미상인 지표는
        # NULL로 남긴다(market_valuation.py 변경이력 참고).
        reliable_sector = MarketValuation.get_reliable_sector_medians(sector_medians, sector)

        session.add(StockValuation(
            timestamp=batch_timestamp,
            ticker=record.get("symbol"),
            market=market,
            per=record.get("per"),
            pbr=record.get("pbr"),
            dividend_yield=record.get("dividend_yield"),
            market_per=MarketValuation.get_market_baseline(market_medians, market).get("market_per"),
            market_pbr=MarketValuation.get_market_baseline(market_medians, market).get("market_pbr"),
            market_dividend_yield=MarketValuation.get_market_baseline(market_medians, market).get(
                "market_dividend_yield"
            ),
            sector=sector,
            sector_per_median=reliable_sector.get("per_median"),
            sector_pbr_median=reliable_sector.get("pbr_median"),
            sector_dividend_median=reliable_sector.get("dividend_median"),
            per_relative_score=details.get("per_relative_score"),
            pbr_relative_score=details.get("pbr_relative_score"),
            dividend_relative_score=details.get("dividend_relative_score"),
            valuation_score=result.get("score"),
            data_quality=details.get("data_quality"),
            data_source=details.get("data_source"),
        ))
        saved += 1

    session.commit()
    logger.info(f"✅ 밸류에이션 파이프라인 완료: {len(records)}종목 수집, {saved}건 DB 저장 "
                f"(Sector 중앙값 {len(sector_medians)}개 카테고리)")
    return {
        "total": len(records),
        "saved": saved,
        "market_medians": market_medians,
        "sector_medians": sector_medians,
    }


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")

    from data.stock_master import StockMaster
    from config.database import SessionLocal

    # 【안전을 위한 기본값】 전체가 아니라 앞쪽 일부만. 전체는 'all' 인자로 실행.
    full_run = len(sys.argv) > 1 and sys.argv[1] == "all"

    master = StockMaster()
    all_stocks = master.get_stock_list(market="ALL", common_stock_only=True)
    target_stocks = all_stocks if full_run else all_stocks[:20]
    if not full_run:
        print(f"⚠️  시험 실행: 앞쪽 {len(target_stocks)}종목만 수집+저장합니다 (전체는 'all' 인자로 실행)")

    session = SessionLocal()
    try:
        result = run_full_valuation_pipeline(session, stock_list=target_stocks, force_refresh=True)
        print(f"\n수집 {result['total']}종목, DB 저장 {result['saved']}건")
        for market, stats in result.get("market_medians", {}).items():
            print(f"  {market}: PER중앙값={stats['per_median']}, PBR중앙값={stats['pbr_median']}, "
                  f"배당중앙값={stats['dividend_median']}, 표본={stats['sample_size']}종목")
    finally:
        session.close()
