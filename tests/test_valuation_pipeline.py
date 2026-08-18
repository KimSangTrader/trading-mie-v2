"""
ValuationPipeline 테스트 (Phase 5-7: 수집→중앙값→상대평가→DB 저장 엔드투엔드)

================================================================================
【변경 이력】
================================================================================
【2026-08-16】최초 생성
- 실제 KIS API/RDS 없이 Mock StockMaster + Mock ValuationCollector +
  SQLite in-memory DB로 파이프라인 전체 흐름(수집→중앙값→상대평가→저장)을 검증한다.
- 이 세션엔 sqlalchemy가 설치되어 있지 않아(PyPI 네트워크 차단) 실행하지 못했다.
  사용자 컴퓨터에서 pytest tests/test_valuation_pipeline.py -v 로 확인 필요.
================================================================================
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db.models import Base, StockValuation
from market_intelligence.collectors.valuation_pipeline import run_full_valuation_pipeline


class MockStockMaster:
    def __init__(self, stocks):
        self._stocks = stocks

    def get_stock_list(self, market="ALL", common_stock_only=True, force_refresh=False):
        return self._stocks


class MockValuationCollector:
    """ValuationCollector.get_or_collect()와 동일한 시그니처/반환형식의 Mock"""

    def __init__(self, responses=None):
        self._responses = responses or {}

    def get_or_collect(self, stock_list, force_refresh=False, rate_limit_sec=0.2,
                        checkpoint_every=50, progress_callback=None):
        records = []
        for s in stock_list:
            data = self._responses.get(s["symbol"], {})
            records.append({
                "symbol": s["symbol"],
                "name": s.get("name"),
                "market": s.get("market"),
                "per": data.get("per"),
                "pbr": data.get("pbr"),
                "dividend_yield": data.get("dividend_yield"),
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


class TestValuationPipelineEndToEnd:
    def test_saves_relative_scores_for_each_stock(self, session):
        stocks = [_stock("005930"), _stock("000660"), _stock("005380")]
        responses = {
            "005930": {"per": 15.2, "pbr": 1.4, "dividend_yield": 2.5},
            "000660": {"per": 21.6, "pbr": 2.1, "dividend_yield": 0.9},
            "005380": {"per": 18.4, "pbr": 1.72, "dividend_yield": 2.05},
        }

        result = run_full_valuation_pipeline(
            session,
            stock_master=MockStockMaster(stocks),
            collector=MockValuationCollector(responses),
        )

        assert result["total"] == 3
        assert result["saved"] == 3
        assert "KOSPI" in result["market_medians"]

        rows = session.query(StockValuation).all()
        assert len(rows) == 3
        by_ticker = {r.ticker: r for r in rows}
        assert by_ticker["005930"].data_source == "relative"
        assert by_ticker["005930"].market_per is not None
        assert by_ticker["005930"].valuation_score is not None

    def test_all_rows_in_one_run_share_the_same_timestamp(self, session):
        stocks = [_stock("005930"), _stock("000660")]
        responses = {
            "005930": {"per": 15.2, "pbr": 1.4, "dividend_yield": 2.5},
            "000660": {"per": 21.6, "pbr": 2.1, "dividend_yield": 0.9},
        }
        run_full_valuation_pipeline(
            session,
            stock_master=MockStockMaster(stocks),
            collector=MockValuationCollector(responses),
        )
        rows = session.query(StockValuation).all()
        assert len({r.timestamp for r in rows}) == 1

    def test_missing_data_still_saved_as_neutral(self, session):
        stocks = [_stock("999999", market="KOSDAQ")]

        result = run_full_valuation_pipeline(
            session,
            stock_master=MockStockMaster(stocks),
            collector=MockValuationCollector({}),  # 응답 없음 - PER/PBR 전부 결측
        )

        assert result["saved"] == 1
        row = session.query(StockValuation).filter_by(ticker="999999").one()
        assert row.data_source == "insufficient_data"
        assert float(row.valuation_score) == 50.0
        assert row.per is None

    def test_stock_list_overrides_stock_master(self, session):
        # stock_list를 직접 넘기면 stock_master.get_stock_list()는 호출되지 않아야 함
        class ExplodingStockMaster:
            def get_stock_list(self, *a, **kw):
                raise AssertionError("stock_list가 있는데 stock_master가 호출됨")

        result = run_full_valuation_pipeline(
            session,
            stock_list=[_stock("005930")],
            stock_master=ExplodingStockMaster(),
            collector=MockValuationCollector({"005930": {"per": 15.2, "pbr": 1.4, "dividend_yield": 2.5}}),
        )
        assert result["total"] == 1

    def test_empty_stock_list_saves_nothing_and_skips_db(self, session):
        result = run_full_valuation_pipeline(
            session,
            stock_list=[],
            collector=MockValuationCollector({}),
        )
        assert result == {"total": 0, "saved": 0}
        assert session.query(StockValuation).count() == 0

    def test_kospi_and_kosdaq_medians_calculated_separately(self, session):
        stocks = [
            _stock("005930", market="KOSPI"),
            _stock("000660", market="KOSPI"),
            _stock("247540", market="KOSDAQ"),
        ]
        responses = {
            "005930": {"per": 15.0, "pbr": 1.0, "dividend_yield": 2.0},
            "000660": {"per": 21.0, "pbr": 2.0, "dividend_yield": 1.0},
            "247540": {"per": 30.0, "pbr": 3.0, "dividend_yield": 0.5},
        }

        result = run_full_valuation_pipeline(
            session,
            stock_master=MockStockMaster(stocks),
            collector=MockValuationCollector(responses),
        )

        medians = result["market_medians"]
        assert medians["KOSPI"]["sample_size"] == 2
        assert medians["KOSDAQ"]["sample_size"] == 1
        # KOSPI 종목의 시장 기준값이 KOSDAQ 종목 값(PER=30)으로 오염되면 안 됨
        row_kospi = session.query(StockValuation).filter_by(ticker="005930").one()
        assert float(row_kospi.market_per) == pytest.approx(18.0)  # (15.0+21.0)/2
