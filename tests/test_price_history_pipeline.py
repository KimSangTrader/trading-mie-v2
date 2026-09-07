"""
PriceHistoryPipeline 테스트 (Phase 5-13: 수집→DB 신규 저장 엔드투엔드)

================================================================================
【변경 이력】
================================================================================
【2026-08-23】최초 생성
- 실제 KIS API/RDS 없이 Mock StockMaster + Mock PriceHistoryCollector +
  SQLite in-memory DB로 파이프라인 전체 흐름을 검증한다
  (tests/test_valuation_pipeline.py와 동일한 패턴).
- 핵심 검증 포인트: stock_price_history는 배치 스냅샷이 아니라 (ticker, trade_date)
  누적 테이블이므로, 같은 파이프라인을 두 번 실행해도 이미 저장된 거래일은
  중복 저장되지 않아야 한다.
【2026-08-23】records 파라미터(TestPriceHistoryPipelineWithPreCollectedRecords) 추가
  (Phase 5-17: main.py 배선) - collector/stock_master를 아예 거치지 않고 이미
  수집된 행을 바로 저장하는 경로를 검증한다. main.py가 TechnicalAnalyzer용으로
  이미 받은 chart 응답을 중복 API 호출 없이 재사용하는 경로와 동일하다.
================================================================================
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db.models import Base, StockPriceHistory
from market_intelligence.collectors.price_history_pipeline import run_full_price_history_pipeline


class MockStockMaster:
    def __init__(self, stocks):
        self._stocks = stocks

    def get_stock_list(self, market="ALL", common_stock_only=True, force_refresh=False):
        return self._stocks


class MockPriceHistoryCollector:
    """PriceHistoryCollector.get_or_collect()와 동일한 시그니처/반환형식의 Mock"""

    def __init__(self, rows_by_symbol=None):
        self._rows_by_symbol = rows_by_symbol or {}

    def get_or_collect(self, stock_list, days=60, force_refresh=False, rate_limit_sec=0.2,
                        checkpoint_every=50, progress_callback=None):
        records = []
        for s in stock_list:
            for row in self._rows_by_symbol.get(s["symbol"], []):
                records.append({
                    "symbol": s["symbol"],
                    "market": s.get("market"),
                    "date": row["date"],
                    "open": row["close"],
                    "high": row["close"],
                    "low": row["close"],
                    "close": row["close"],
                    "volume": row.get("volume", 1000),
                })
        return records


def _stock(symbol, market="KOSPI", name="종목"):
    return {"symbol": symbol, "market": market, "name": name}


@pytest.fixture()
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class TestPriceHistoryPipelineEndToEnd:
    def test_saves_all_rows_for_new_tickers(self, session):
        stocks = [_stock("005930"), _stock("000660")]
        rows_by_symbol = {
            "005930": [{"date": "20260810", "close": 70000}, {"date": "20260811", "close": 71000}],
            "000660": [{"date": "20260810", "close": 200000}],
        }

        result = run_full_price_history_pipeline(
            session,
            stock_master=MockStockMaster(stocks),
            collector=MockPriceHistoryCollector(rows_by_symbol),
        )

        assert result["total_symbols"] == 2
        assert result["rows_fetched"] == 3
        assert result["rows_saved"] == 3
        assert session.query(StockPriceHistory).count() == 3

    def test_rerun_does_not_duplicate_existing_trade_dates(self, session):
        stocks = [_stock("005930")]
        rows_by_symbol = {
            "005930": [{"date": "20260810", "close": 70000}, {"date": "20260811", "close": 71000}],
        }
        collector = MockPriceHistoryCollector(rows_by_symbol)

        first = run_full_price_history_pipeline(
            session, stock_master=MockStockMaster(stocks), collector=collector,
        )
        assert first["rows_saved"] == 2

        # 같은 종목에 거래일이 하나 더 늘어난 상황(다음날 재실행) 시뮬레이션
        collector._rows_by_symbol["005930"].append({"date": "20260812", "close": 72000})
        second = run_full_price_history_pipeline(
            session, stock_master=MockStockMaster(stocks), collector=collector,
        )

        assert second["rows_fetched"] == 3  # 수집기는 항상 전체(days)를 다시 반환
        assert second["rows_saved"] == 1  # 새로 생긴 거래일 1개만 저장
        assert session.query(StockPriceHistory).count() == 3

    def test_stock_list_overrides_stock_master(self, session):
        class ExplodingStockMaster:
            def get_stock_list(self, *a, **kw):
                raise AssertionError("stock_list가 있는데 stock_master가 호출됨")

        result = run_full_price_history_pipeline(
            session,
            stock_list=[_stock("005930")],
            stock_master=ExplodingStockMaster(),
            collector=MockPriceHistoryCollector({"005930": [{"date": "20260810", "close": 70000}]}),
        )
        assert result["total_symbols"] == 1

    def test_empty_stock_list_saves_nothing_and_skips_db(self, session):
        result = run_full_price_history_pipeline(
            session,
            stock_list=[],
            collector=MockPriceHistoryCollector({}),
        )
        assert result == {"total_symbols": 0, "rows_fetched": 0, "rows_saved": 0}
        assert session.query(StockPriceHistory).count() == 0

    def test_no_chart_data_for_symbol_saves_nothing_for_it(self, session):
        stocks = [_stock("999999")]
        result = run_full_price_history_pipeline(
            session,
            stock_master=MockStockMaster(stocks),
            collector=MockPriceHistoryCollector({}),  # 응답 없음
        )
        assert result["rows_fetched"] == 0
        assert result["rows_saved"] == 0


class TestPriceHistoryPipelineWithPreCollectedRecords:
    """records를 직접 넘기면 collector/stock_master를 아예 건드리지 않아야 한다."""

    def test_records_bypasses_collector_and_stock_master_entirely(self, session):
        class ExplodingStockMaster:
            def get_stock_list(self, *a, **kw):
                raise AssertionError("records가 있는데 stock_master가 호출됨")

        class ExplodingCollector:
            def get_or_collect(self, *a, **kw):
                raise AssertionError("records가 있는데 collector가 호출됨")

        records = [
            {"symbol": "005930", "market": "KOSPI", "date": "20260810",
             "open": 70000, "high": 70000, "low": 70000, "close": 70000, "volume": 1000},
            {"symbol": "005930", "market": "KOSPI", "date": "20260811",
             "open": 71000, "high": 71000, "low": 71000, "close": 71000, "volume": 1200},
        ]

        result = run_full_price_history_pipeline(
            session,
            stock_master=ExplodingStockMaster(),
            collector=ExplodingCollector(),
            records=records,
        )

        assert result["total_symbols"] == 1
        assert result["rows_fetched"] == 2
        assert result["rows_saved"] == 2
        assert session.query(StockPriceHistory).count() == 2

    def test_rerun_with_records_does_not_duplicate_existing_trade_dates(self, session):
        first_records = [
            {"symbol": "005930", "market": "KOSPI", "date": "20260810",
             "open": 70000, "high": 70000, "low": 70000, "close": 70000, "volume": 1000},
        ]
        first = run_full_price_history_pipeline(session, records=first_records)
        assert first["rows_saved"] == 1

        second_records = first_records + [
            {"symbol": "005930", "market": "KOSPI", "date": "20260811",
             "open": 71000, "high": 71000, "low": 71000, "close": 71000, "volume": 1200},
        ]
        second = run_full_price_history_pipeline(session, records=second_records)
        assert second["rows_fetched"] == 2
        assert second["rows_saved"] == 1  # 이미 있던 20260810은 건너뜀
        assert session.query(StockPriceHistory).count() == 2

    def test_empty_records_saves_nothing_and_skips_db(self, session):
        result = run_full_price_history_pipeline(session, records=[])
        assert result == {"total_symbols": 0, "rows_fetched": 0, "rows_saved": 0}
        assert session.query(StockPriceHistory).count() == 0
