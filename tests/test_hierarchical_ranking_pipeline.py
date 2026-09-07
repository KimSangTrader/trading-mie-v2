"""
HierarchicalRankingPipeline 테스트 (Phase 5-16: 계층형 순위 엔드투엔드)

================================================================================
【변경 이력】
================================================================================
【2026-08-23】최초 생성
- 실제 KIS API/RDS 없이 SQLite in-memory DB + 수동 구성한 price_history/
  sector_mapping/theme_mapping으로 파이프라인 전체 흐름을 검증한다
  (tests/test_valuation_pipeline.py, tests/test_price_history_pipeline.py와
  동일한 패턴).
================================================================================
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db.models import (
    Base,
    StockHierarchicalScore,
    StockPriceHistory,
    StockSectorMapping,
    StockThemeMapping,
)
from market_intelligence.collectors.hierarchical_ranking_pipeline import (
    run_hierarchical_ranking_pipeline,
)


def _price_rows(ticker, daily_pct_change, days=65, start_price=10000, market="KOSPI"):
    rows = []
    price = start_price
    for day in range(days):
        rows.append({
            "ticker": ticker, "market": market,
            "trade_date": f"20260{(day // 28) % 9 + 1}{(day % 28) + 1:02d}",
            "close": round(price, 2), "volume": 10000,
        })
        price *= (1 + daily_pct_change / 100)
    return rows


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


class TestHierarchicalRankingPipelineEndToEnd:
    def test_saves_ranked_rows_for_stocks_with_price_data(self, session):
        price_history = _price_rows("005930", 0.5) + _price_rows("035420", -0.3)
        sector_mapping = [
            {"ticker": "005930", "sector": "IT_Semiconductor", "market": "KOSPI", "needs_review": False},
            {"ticker": "035420", "sector": "Consumer", "market": "KOSPI", "needs_review": False},
        ]
        theme_mapping = [
            {"ticker": "005930", "theme": "AI", "is_primary": True},
        ]

        result = run_hierarchical_ranking_pipeline(
            session,
            market_regime_scores={"KOSPI": 60.0},
            price_history=price_history,
            sector_mapping=sector_mapping,
            theme_mapping=theme_mapping,
        )

        assert result["total"] == 2
        assert result["saved"] == 2
        assert result["sector_count"] == 2

        rows = session.query(StockHierarchicalScore).all()
        assert len(rows) == 2
        by_ticker = {r.ticker: r for r in rows}
        assert by_ticker["005930"].final_score > by_ticker["035420"].final_score
        assert by_ticker["005930"].overall_rank == 1
        assert by_ticker["035420"].overall_rank == 2

    def test_tickers_without_price_data_are_excluded(self, session):
        # sector_mapping에는 있지만 price_history가 전혀 없는 종목은 순위 대상에서 빠져야 함
        price_history = _price_rows("005930", 0.2)
        sector_mapping = [
            {"ticker": "005930", "sector": "IT_Semiconductor", "market": "KOSPI", "needs_review": False},
            {"ticker": "999999", "sector": "Other", "market": "KOSPI", "needs_review": False},
        ]

        result = run_hierarchical_ranking_pipeline(
            session, market_regime_scores={"KOSPI": 50.0},
            price_history=price_history, sector_mapping=sector_mapping, theme_mapping=[],
        )

        assert result["total"] == 1
        tickers = {r.ticker for r in session.query(StockHierarchicalScore).all()}
        assert tickers == {"005930"}

    def test_no_mapping_at_all_saves_nothing(self, session):
        result = run_hierarchical_ranking_pipeline(
            session, market_regime_scores={}, price_history=[], sector_mapping=[], theme_mapping=[],
        )
        assert result == {"total": 0, "saved": 0}
        assert session.query(StockHierarchicalScore).count() == 0

    def test_all_rows_in_one_run_share_the_same_timestamp(self, session):
        price_history = _price_rows("005930", 0.2) + _price_rows("035420", 0.1)
        sector_mapping = [
            {"ticker": "005930", "sector": "IT_Semiconductor", "market": "KOSPI", "needs_review": False},
            {"ticker": "035420", "sector": "IT_Semiconductor", "market": "KOSPI", "needs_review": False},
        ]
        run_hierarchical_ranking_pipeline(
            session, market_regime_scores={"KOSPI": 50.0},
            price_history=price_history, sector_mapping=sector_mapping, theme_mapping=[],
        )
        rows = session.query(StockHierarchicalScore).all()
        assert len({r.timestamp for r in rows}) == 1

    def test_valuation_by_ticker_is_forwarded_into_stock_score(self, session):
        price_history = _price_rows("005930", 0.1)
        sector_mapping = [
            {"ticker": "005930", "sector": "IT_Semiconductor", "market": "KOSPI", "needs_review": False},
        ]
        result = run_hierarchical_ranking_pipeline(
            session, market_regime_scores={"KOSPI": 50.0},
            price_history=price_history, sector_mapping=sector_mapping, theme_mapping=[],
            valuation_by_ticker={
                "005930": {"per": 10.0, "market_per": 20.0, "pbr": 0.8, "market_pbr": 1.6,
                           "dividend_yield": 3.0, "market_dividend_yield": 1.5},
            },
        )
        assert result["saved"] == 1
        row = session.query(StockHierarchicalScore).filter_by(ticker="005930").one()
        # 저평가+고배당 입력이므로 stock_score는 중립(50)보다 뚜렷하게 높아야 함
        assert float(row.stock_score) > 55.0


class TestHierarchicalRankingPipelineReadsFromDbWhenNotProvided:
    """price_history/sector_mapping/theme_mapping을 명시적으로 넘기지 않으면
    DB(stock_price_history, get_latest_sector_mapping/get_latest_theme_mapping)에서
    직접 읽어와야 한다 - 실제 운영에서 쓰일 경로라 명시적으로 검증해 둔다."""

    def test_reads_price_history_from_db_when_none(self, session):
        for day, close in enumerate([100.0 + i for i in range(65)]):
            session.add(StockPriceHistory(
                ticker="005930", market="KOSPI", trade_date=f"2026{6 + day // 28:02d}{(day % 28) + 1:02d}",
                close=close, volume=10000,
            ))
        session.add(StockSectorMapping(
            ticker="005930", name="종목", market="KOSPI", sector="IT_Semiconductor", needs_review=False,
        ))
        session.commit()

        result = run_hierarchical_ranking_pipeline(
            session, market_regime_scores={"KOSPI": 50.0}, theme_mapping=[],
        )
        assert result["total"] == 1
        assert session.query(StockHierarchicalScore).filter_by(ticker="005930").count() == 1

    def test_reads_only_latest_sector_mapping_batch(self, session):
        import datetime as dt

        old_ts = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)
        new_ts = dt.datetime(2026, 8, 1, tzinfo=dt.timezone.utc)
        # 옛 배치: 000660만 있음 / 최신 배치: 005930만 있음 - 최신 배치만 반영되어야 함
        session.add(StockSectorMapping(
            ticker="000660", name="옛종목", market="KOSPI", sector="Finance",
            needs_review=False, timestamp=old_ts,
        ))
        session.add(StockSectorMapping(
            ticker="005930", name="신종목", market="KOSPI", sector="IT_Semiconductor",
            needs_review=False, timestamp=new_ts,
        ))
        for day, close in enumerate([100.0 + i for i in range(65)]):
            date_str = f"2026{6 + day // 28:02d}{(day % 28) + 1:02d}"
            session.add(StockPriceHistory(ticker="005930", market="KOSPI", trade_date=date_str,
                                           close=close, volume=10000))
            session.add(StockPriceHistory(ticker="000660", market="KOSPI", trade_date=date_str,
                                           close=close, volume=10000))
        session.commit()

        result = run_hierarchical_ranking_pipeline(
            session, market_regime_scores={"KOSPI": 50.0}, theme_mapping=[],
        )
        tickers = {r.ticker for r in session.query(StockHierarchicalScore).all()}
        assert tickers == {"005930"}
        assert result["total"] == 1
