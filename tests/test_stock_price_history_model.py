"""
StockPriceHistory DB 모델 테스트 (Phase 5-13: 종목별 일봉 히스토리 테이블)

================================================================================
【변경 이력】
================================================================================
【2026-08-23】최초 생성
- tests/test_db_models.py(StockValuation)와 동일한 패턴 - SQLite in-memory로
  모델 정의(컬럼/인덱스)와 왕복 저장을 검증한다. 이 세션은 실제 Postgres에
  접근할 수 없어 라이브 검증은 사용자 컴퓨터에서 필요.
- 이 테이블 고유의 핵심 검증 포인트: stock_valuation과 달리 "같은 timestamp에
  여러 종목이 함께 들어가는 배치 스냅샷"이 아니라 (ticker, trade_date)로
  유일해야 하는 누적 사실 테이블이라는 점 - UNIQUE 제약 위반 테스트를 추가함.
================================================================================
"""

from decimal import Decimal

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from db.models import Base, StockPriceHistory


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


class TestStockPriceHistorySchema:
    def test_table_registered_in_metadata(self):
        assert "stock_price_history" in Base.metadata.tables

    def test_expected_columns_present(self):
        columns = {c.name for c in Base.metadata.tables["stock_price_history"].columns}
        expected = {
            "id", "ticker", "market", "trade_date",
            "open", "high", "low", "close", "volume",
            "collected_at", "created_at",
        }
        assert expected.issubset(columns)

    def test_indexes_present(self, session):
        engine = session.get_bind()
        index_names = {ix["name"] for ix in inspect(engine).get_indexes("stock_price_history")}
        assert "idx_stock_price_history_ticker_date" in index_names
        assert "idx_stock_price_history_trade_date" in index_names


class TestStockPriceHistoryRoundTrip:
    def test_insert_and_query_single_row(self, session):
        row = StockPriceHistory(
            ticker="005930", market="KOSPI", trade_date="20260810",
            open=Decimal("70000"), high=Decimal("70500"), low=Decimal("69800"),
            close=Decimal("70200"), volume=12345678,
        )
        session.add(row)
        session.commit()

        fetched = session.query(StockPriceHistory).filter_by(ticker="005930").one()
        assert fetched.trade_date == "20260810"
        assert float(fetched.close) == 70200
        assert fetched.volume == 12345678
        assert fetched.id is not None
        assert fetched.collected_at is not None  # default 적용 확인

    def test_same_ticker_multiple_trade_dates_allowed(self, session):
        session.add_all([
            StockPriceHistory(ticker="005930", trade_date="20260810", close=Decimal("70000")),
            StockPriceHistory(ticker="005930", trade_date="20260811", close=Decimal("71000")),
        ])
        session.commit()

        rows = session.query(StockPriceHistory).filter_by(ticker="005930").order_by(
            StockPriceHistory.trade_date
        ).all()
        assert [float(r.close) for r in rows] == [70000, 71000]

    def test_duplicate_ticker_and_trade_date_rejected(self, session):
        # (ticker, trade_date) UNIQUE 제약 - 같은 종목의 같은 거래일이 두 번 들어가면 안 됨
        session.add(StockPriceHistory(ticker="005930", trade_date="20260810", close=Decimal("70000")))
        session.commit()

        session.add(StockPriceHistory(ticker="005930", trade_date="20260810", close=Decimal("70500")))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

    def test_multiple_tickers_same_trade_date_allowed(self, session):
        session.add_all([
            StockPriceHistory(ticker="005930", trade_date="20260810", close=Decimal("70000")),
            StockPriceHistory(ticker="000660", trade_date="20260810", close=Decimal("200000")),
        ])
        session.commit()

        rows = session.query(StockPriceHistory).filter_by(trade_date="20260810").all()
        assert {r.ticker for r in rows} == {"005930", "000660"}
