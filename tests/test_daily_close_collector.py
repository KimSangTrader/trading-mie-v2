"""daily_close_collector.py 테스트 (2026-10-30) - 실제 KIS는 호출하지 않는다."""
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db.models import Base, StockPriceHistory, StockValuation
from market_intelligence.collectors import daily_close_collector as dcc

KST = dcc.KST


@pytest.fixture()
def session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    s = sessionmaker(bind=engine)()
    for t in ("000660", "005930", "035720"):
        s.add(StockValuation(timestamp=datetime(2026, 10, 29, 9, 0), ticker=t, market="KOSPI"))
    s.commit()
    yield s
    s.close()


class FakeKIS:
    """종목마다 10/29(공식으로 고쳐진 값), 10/30(당일) 두 행을 준다."""

    def __init__(self, today_close=225_000.0, prev_close=232_000.0):
        self.calls = []
        self.today_close, self.prev_close = today_close, prev_close

    def get_stock_daily_chart(self, ticker, days=60):
        self.calls.append(ticker)
        return {"dates": ["20261029", "20261030"], "opens": [1.0, 1.0], "highs": [1.0, 1.0], "lows": [1.0, 1.0],
                "closes": [self.prev_close, self.today_close], "volumes": [100, 200]}


class RecordingNotifier:
    def __init__(self):
        self.sent = []

    def send(self, text, key=None):
        self.sent.append(key)
        return True


def _clock(*times):
    """호출될 때마다 다음 시각을 돌려준다(마지막 값은 계속 유지)."""
    seq = [datetime(2026, 10, 30, h, m, s, tzinfo=KST) for h, m, s in times]

    def now():
        return seq.pop(0) if len(seq) > 1 else seq[0]
    return now


def _closes(session, date):
    return {r.ticker: float(r.close) for r in session.query(StockPriceHistory).filter_by(trade_date=date)}


class TestCloseSnapshot:
    def test_saves_only_today_rows(self, session):
        result = dcc.run_close_snapshot(session, FakeKIS(), now_fn=_clock((15, 41, 0)), rate_limit_sec=0)
        assert result["status"] == "ok" and result["with_rows"] == 3
        assert _closes(session, "20261030") == {"000660": 225_000, "005930": 225_000, "035720": 225_000}
        assert _closes(session, "20261029") == {}  # 지난 날짜는 이 모드에서 건드리지 않음

    def test_refuses_after_deadline(self, session):
        notifier = RecordingNotifier()
        result = dcc.run_close_snapshot(session, FakeKIS(), notifier=notifier, now_fn=_clock((16, 5, 0)), rate_limit_sec=0)
        assert result["status"] == "too_late"
        assert session.query(StockPriceHistory).count() == 0
        assert notifier.sent == ["daily_close_late"]

    def test_stops_at_deadline_and_alerts_low_coverage(self, session):
        kis, notifier = FakeKIS(), RecordingNotifier()
        # 시작 15:58:50 -> 첫 종목 15:59:00 수집 -> 두 번째 확인 시점 15:59:40(마감 이후)에 멈춤
        result = dcc.run_close_snapshot(session, kis, notifier=notifier,
                                        now_fn=_clock((15, 58, 50), (15, 59, 0), (15, 59, 40)), rate_limit_sec=0)
        assert kis.calls == ["000660"]
        assert result["stopped_at_deadline"] == 2
        assert notifier.sent == ["daily_close_coverage"]

    def test_holiday_does_nothing(self, session):
        holiday = lambda: datetime(2026, 11, 1, 15, 41, tzinfo=KST)  # 일요일
        assert dcc.run_close_snapshot(session, FakeKIS(), now_fn=holiday, rate_limit_sec=0)["status"] == "holiday"
        assert session.query(StockPriceHistory).count() == 0


class TestBackfill:
    def test_overwrites_past_rows_and_skips_today(self, session):
        session.add(StockPriceHistory(ticker="005930", market="KOSPI", trade_date="20261029",
                                      open=1, high=1, low=1, close=230_500, volume=100))
        session.commit()

        result = dcc.run_backfill(session, FakeKIS(), days=5, now_fn=lambda: datetime(2026, 10, 30, 20, 30, tzinfo=KST),
                                  rate_limit_sec=0)

        assert result["rows_updated"] == 1 and result["rows_saved"] == 2
        assert _closes(session, "20261029") == {"000660": 232_000, "005930": 232_000, "035720": 232_000}
        assert _closes(session, "20261030") == {}  # 오늘(임시 값)은 넣지 않음
