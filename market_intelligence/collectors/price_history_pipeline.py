"""
PriceHistoryPipeline - 종목마스터→일봉 히스토리 수집→DB 저장 엔드투엔드 (Phase 5-13)

================================================================================
【변경 이력】
================================================================================
【2026-08-23】최초 생성
- 배경: docs/hierarchical_scoring_plan.md Phase 1. data/price_history_collector.py
  (PriceHistoryCollector)까지는 "가져오기"만 하고 DB에는 넣지 않는다 - 이 모듈이
  valuation_pipeline.py와 동일한 역할(마스터→수집→DB 저장)로 이어붙인다.
- stock_valuation/stock_sector_mapping과 달리 stock_price_history는 "배치마다
  통째로 새 timestamp로 insert"하는 스냅샷 패턴이 아니라 (ticker, trade_date)로
  유일해야 하는 누적 사실 테이블이다(db/models.py StockPriceHistory 문서 참고).
  그래서 이 파이프라인은 매 실행마다 대상 종목들의 기존 (ticker, trade_date)
  집합을 먼저 조회해 이미 있는 거래일은 건너뛰고, 새로 생긴 거래일만 insert한다
  (재실행해도 중복 행이 쌓이지 않음 - UNIQUE 제약을 믿고 그냥 insert해서 예외로
  걸러내는 대신, 미리 걸러서 조용히 건너뛰는 쪽을 택함 - 세션 하나에서
  대량 rollback을 유발하지 않기 위함).
- DB 세션(session)과 커밋 시점은 호출부 책임으로 남겨둔다(valuation_pipeline.py와
  동일한 원칙 - 테스트에서 SQLite in-memory 세션을 주입할 수 있어야 함).
- 이 세션은 sqlalchemy 실행/실제 RDS 접근이 불가능해 SQLite 단위테스트로만
  검증했다(기존 관례와 동일 - tests/test_price_history_pipeline.py 참고).
【2026-08-23】records 파라미터 추가 (Phase 5-17: main.py 배선)
- 배경: main.py의 종목별 루프가 TechnicalAnalyzer용으로 이미 종목마다
  get_stock_daily_chart()를 호출해 chart를 받고 있다. 이 파이프라인이 collector로
  또 API를 호출하면 종목당 호출이 2배가 된다. records를 직접 넘기면 collector
  호출(및 그 안의 API 수집)을 건너뛰고, 이미 모아둔 행을 그대로 DB 중복 제거+저장
  로직에만 태운다 - collector/API를 아예 몰라도 되므로 테스트에서도 그대로 쓸 수
  있다(Mock collector를 안 만들어도 됨).
================================================================================
"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def run_full_price_history_pipeline(
    session,
    stock_list: Optional[List[Dict[str, Any]]] = None,
    stock_master: Optional[Any] = None,
    collector: Optional[Any] = None,
    days: int = 60,
    force_refresh: bool = False,
    rate_limit_sec: float = 0.2,
    checkpoint_every: int = 50,
    progress_callback: Optional[Any] = None,
    records: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    KOSPI/KOSDAQ 종목 → 일봉 히스토리 수집 → 신규 (ticker, trade_date)만 DB
    (stock_price_history 테이블)에 저장까지 한 번에 수행한다.

    Args:
        session: SQLAlchemy Session. add()와 commit()까지 이 함수 안에서 하지만,
            세션 생성/종료(close)는 호출부 책임이다.
        stock_list: 직접 넘기면 이 목록만 처리한다(테스트, 부분 실행용).
            None이면 stock_master.get_stock_list(market="ALL", common_stock_only=True)로
            KOSPI/KOSDAQ 전체 보통주를 가져온다. records를 직접 넘기면 무시된다.
        stock_master / collector: 테스트에서 Mock으로 교체하기 위한 주입 지점.
            None이면 각각 StockMaster(), PriceHistoryCollector()를 새로 만든다.
            records를 직접 넘기면 둘 다 아예 쓰이지 않는다.
        records: 이미 수집된 (종목, 거래일)별 행 리스트를 직접 넘긴다
            (data/price_history_collector.py의 chart_to_price_rows()/collect()와
            동일한 형식 - {"symbol":, "market":, "date":, "open":, ...}). 넘기면
            collector.get_or_collect()(및 그 안의 API 호출)를 건너뛰고 이 값을
            그대로 DB 중복 제거+저장에 쓴다 - main.py처럼 다른 이유로 이미 같은
            chart 응답을 받아둔 호출부의 중복 API 호출을 막기 위함.

    Returns:
        {"total_symbols": 일봉 데이터가 하나라도 확보된 종목 수(조회 실패/데이터
         없음인 종목은 제외 - PriceHistoryCollector는 그런 종목에 대해 빈 행을
         만들지 않는다), "rows_fetched": 수집된 전체 행 수,
         "rows_saved": 새로 DB에 저장한 행 수(이미 있던 거래일은 제외)}
        stock_list와 stock_master.get_stock_list() 결과가 모두 비어 있으면(records도
        없으면) {"total_symbols": 0, "rows_fetched": 0, "rows_saved": 0}
    """
    from db.models import StockPriceHistory

    if records is None:
        if stock_list is None:
            if stock_master is None:
                from data.stock_master import StockMaster
                stock_master = StockMaster()
            stock_list = stock_master.get_stock_list(market="ALL", common_stock_only=True)

        if not stock_list:
            logger.warning("⚠️  처리할 종목이 없습니다 (빈 stock_list) - 파이프라인 중단")
            return {"total_symbols": 0, "rows_fetched": 0, "rows_saved": 0}

        if collector is None:
            from data.price_history_collector import PriceHistoryCollector
            collector = PriceHistoryCollector()

        records = collector.get_or_collect(
            stock_list,
            days=days,
            force_refresh=force_refresh,
            rate_limit_sec=rate_limit_sec,
            checkpoint_every=checkpoint_every,
            progress_callback=progress_callback,
        )
    elif not records:
        logger.warning("⚠️  넘겨받은 records가 비어 있습니다 - 파이프라인 중단")
        return {"total_symbols": 0, "rows_fetched": 0, "rows_saved": 0}

    tickers = sorted({r["symbol"] for r in records})
    existing_keys = set()
    if tickers:
        existing_rows = (
            session.query(StockPriceHistory.ticker, StockPriceHistory.trade_date)
            .filter(StockPriceHistory.ticker.in_(tickers))
            .all()
        )
        existing_keys = {(t, d) for t, d in existing_rows}

    saved = 0
    for record in records:
        key = (record["symbol"], record["date"])
        if key in existing_keys:
            continue
        existing_keys.add(key)  # 같은 배치 안에서 중복 행이 와도 한 번만 저장

        session.add(StockPriceHistory(
            ticker=record["symbol"],
            market=record.get("market"),
            trade_date=record["date"],
            open=record.get("open"),
            high=record.get("high"),
            low=record.get("low"),
            close=record.get("close"),
            volume=record.get("volume"),
        ))
        saved += 1

    session.commit()
    logger.info(
        f"✅ 일봉 히스토리 파이프라인 완료: {len(tickers)}종목, "
        f"{len(records)}행 수집 중 {saved}행 신규 저장"
    )
    return {"total_symbols": len(tickers), "rows_fetched": len(records), "rows_saved": saved}


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
        result = run_full_price_history_pipeline(session, stock_list=target_stocks, force_refresh=True)
        print(f"\n수집 {result['total_symbols']}종목, {result['rows_fetched']}행 중 신규 {result['rows_saved']}행 저장")
    finally:
        session.close()
