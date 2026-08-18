"""
StockValuation DB 모델 테스트 (Phase 5: db/models.py에 추가된 상대평가 결과 테이블)

================================================================================
【변경 이력】
================================================================================
【2026-08-15】최초 생성
- 이 세션(클라우드 샌드박스)에는 sqlalchemy가 설치되어 있지 않아(PyPI 네트워크 차단)
  실행 검증을 하지 못했다. 실제 Postgres 대신 SQLite in-memory 엔진으로
  create_all/insert/select 왕복을 검증하도록 작성했으니, 사용자 컴퓨터에서
  pytest tests/test_db_models.py -v 로 직접 실행해서 확인해야 한다.
- 라이브 Postgres 연결(config.database.engine)은 사용하지 않는다 - 순수하게
  모델 정의 자체(컬럼, 인덱스, 왕복 저장)만 검증하는 것이 목적이라 어떤 환경에서든
  실행 가능한 SQLite in-memory를 사용한다.
================================================================================
"""

from decimal import Decimal

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

from db.models import Base, StockValuation


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


class TestStockValuationSchema:
    def test_table_registered_in_metadata(self):
        assert "stock_valuation" in Base.metadata.tables

    def test_expected_columns_present(self):
        columns = {c.name for c in Base.metadata.tables["stock_valuation"].columns}
        expected = {
            "id", "timestamp", "ticker", "market",
            "per", "pbr", "dividend_yield",
            "market_per", "market_pbr", "market_dividend_yield",
            "per_relative_score", "pbr_relative_score", "dividend_relative_score",
            "valuation_score", "data_quality", "data_source",
            "created_at",
        }
        assert expected.issubset(columns)

    def test_indexes_present(self, session):
        engine = session.get_bind()
        index_names = {ix["name"] for ix in inspect(engine).get_indexes("stock_valuation")}
        assert "idx_stock_valuation_timestamp" in index_names
        assert "idx_stock_valuation_ticker" in index_names
        assert "idx_stock_valuation_market" in index_names


class TestStockValuationRoundTrip:
    def test_insert_and_query_relative_result(self, session):
        row = StockValuation(
            ticker="005930",
            market="KOSPI",
            per=Decimal("15.20"),
            pbr=Decimal("1.40"),
            dividend_yield=Decimal("2.10"),
            market_per=Decimal("18.40"),
            market_pbr=Decimal("1.72"),
            market_dividend_yield=Decimal("2.05"),
            per_relative_score=Decimal("67.40"),
            pbr_relative_score=Decimal("68.60"),
            dividend_relative_score=Decimal("52.40"),
            valuation_score=Decimal("62.80"),
            data_quality=Decimal("100.00"),
            data_source="relative",
        )
        session.add(row)
        session.commit()

        fetched = session.query(StockValuation).filter_by(ticker="005930").one()
        assert fetched.market == "KOSPI"
        assert float(fetched.valuation_score) == 62.8
        assert fetched.data_source == "relative"
        assert fetched.id is not None
        assert fetched.timestamp is not None  # default 적용 확인

    def test_insufficient_data_row_allows_null_scores(self, session):
        # 종목 마스터에는 있지만 PER/PBR/배당 모두 조회 실패한 경우 -
        # ValuationAnalyzer의 insufficient_data 결과를 그대로 저장할 수 있어야 함
        row = StockValuation(
            ticker="999999",
            market="KOSDAQ",
            data_source="insufficient_data",
            data_quality=Decimal("0.00"),
            valuation_score=Decimal("50.00"),
        )
        session.add(row)
        session.commit()

        fetched = session.query(StockValuation).filter_by(ticker="999999").one()
        assert fetched.per is None
        assert fetched.market_per is None
        assert fetched.data_source == "insufficient_data"

    def test_multiple_tickers_same_timestamp_allowed(self, session):
        # sector_data와 동일한 패턴: 한 번의 수집(같은 timestamp)에 종목 수만큼 행이 생김
        import datetime as dt
        ts = dt.datetime.now(dt.timezone.utc)
        session.add_all([
            StockValuation(ticker="005930", market="KOSPI", timestamp=ts, valuation_score=Decimal("60.0")),
            StockValuation(ticker="000660", market="KOSPI", timestamp=ts, valuation_score=Decimal("55.0")),
        ])
        session.commit()

        rows = session.query(StockValuation).filter_by(timestamp=ts).all()
        assert len(rows) == 2
        assert {r.ticker for r in rows} == {"005930", "000660"}
