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
    force_refresh: bool = False,
    rate_limit_sec: float = 0.2,
    checkpoint_every: int = 50,
    progress_callback: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    KOSPI/KOSDAQ 종목 → PER/PBR 수집 → 시장별 중앙값 → 종목별 상대평가 →
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

    Returns:
        {"total": 처리한 종목 수, "saved": DB에 저장한 행 수, "market_medians": {...}}
        stock_list와 stock_master.get_stock_list() 결과가 모두 비어 있으면
        {"total": 0, "saved": 0} (market_medians 없음, DB 접근도 하지 않음)
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

    from market_intelligence.market_valuation import MarketValuation
    from market_intelligence.analyzers.valuation_analyzer import ValuationAnalyzer
    from db.models import StockValuation

    records = collector.get_or_collect(
        stock_list,
        force_refresh=force_refresh,
        rate_limit_sec=rate_limit_sec,
        checkpoint_every=checkpoint_every,
        progress_callback=progress_callback,
    )

    medians = MarketValuation.calculate_medians(records)
    analyzer = ValuationAnalyzer()
    batch_timestamp = datetime.now(timezone.utc)

    saved = 0
    for record in records:
        market = record.get("market")
        baseline = MarketValuation.get_market_baseline(medians, market)
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

        session.add(StockValuation(
            timestamp=batch_timestamp,
            ticker=record.get("symbol"),
            market=market,
            per=record.get("per"),
            pbr=record.get("pbr"),
            dividend_yield=record.get("dividend_yield"),
            market_per=baseline.get("market_per"),
            market_pbr=baseline.get("market_pbr"),
            market_dividend_yield=baseline.get("market_dividend_yield"),
            per_relative_score=details.get("per_relative_score"),
            pbr_relative_score=details.get("pbr_relative_score"),
            dividend_relative_score=details.get("dividend_relative_score"),
            valuation_score=result.get("score"),
            data_quality=details.get("data_quality"),
            data_source=details.get("data_source"),
        ))
        saved += 1

    session.commit()
    logger.info(f"✅ 밸류에이션 파이프라인 완료: {len(records)}종목 수집, {saved}건 DB 저장")
    return {"total": len(records), "saved": saved, "market_medians": medians}


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
