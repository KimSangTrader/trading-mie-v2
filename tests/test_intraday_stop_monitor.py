"""intraday_stop_monitor.py 테스트 (2026-10-14).

판정 함수(judge_intraday_stop)는 순수 함수로, run_tick()은 Mock 시세/주문
클라이언트 + SQLite in-memory DB로 검증한다(test_trade_execution_pipeline.py와
동일한 패턴)."""
from datetime import datetime, time as dtime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db.models import Base, TradePosition, TradingHistory, StockPriceHistory, StockHierarchicalScore
from market_intelligence.trade_execution.config import IntradayMonitorConfig, ExitConfig
from market_intelligence.trade_execution.intraday_stop_monitor import (
    KST,
    IntradayStopMonitor,
    judge_intraday_stop,
    load_atr20,
)

MONITOR_CONFIG = IntradayMonitorConfig()
EXIT_CONFIG = ExitConfig()
AFTER_QUIET = dtime(10, 0)
IN_QUIET = dtime(9, 3)


def _pos(**overrides):
    base = {"stop_price": 9_000.0, "initial_stop_price": 9_000.0}
    base.update(overrides)
    return base


def _quote(price, change_pct=0.0, high=None):
    return {"current_price": price, "change_pct": change_pct, "high": high or price}


class TestJudgeIntradayStop:
    def test_above_stop_holds_and_resets_count(self):
        assert judge_intraday_stop(_pos(), _quote(9_100.0), 500.0, 2, AFTER_QUIET) == ("HOLD", "ABOVE_STOP", 0)

    def test_shallow_breach_needs_consecutive_confirmations(self):
        action, reason, count = judge_intraday_stop(_pos(), _quote(8_950.0), 500.0, 0, AFTER_QUIET)
        assert (action, reason, count) == ("HOLD", "STOP_BREACH_PENDING", 1)
        action, reason, count = judge_intraday_stop(_pos(), _quote(8_950.0), 500.0, count, AFTER_QUIET)
        assert (action, count) == ("HOLD", 2)
        action, reason, count = judge_intraday_stop(_pos(), _quote(8_950.0), 500.0, count, AFTER_QUIET)
        assert (action, reason) == ("SELL_ALL", "INITIAL_STOP")

    def test_recovery_resets_confirmation(self):
        """이탈 2회 후 손절가 위로 회복하면 카운트가 0으로 - 휩쏘에 털리지 않음."""
        _, _, count = judge_intraday_stop(_pos(), _quote(9_050.0), 500.0, 2, AFTER_QUIET)
        assert count == 0

    def test_deep_breach_sells_immediately_even_in_quiet_window(self):
        # 9,000 - 500 x 0.5 = 8,750 이하 -> 즉시
        action, reason, _ = judge_intraday_stop(_pos(), _quote(8_750.0), 500.0, 0, IN_QUIET)
        assert (action, reason) == ("SELL_ALL", "INITIAL_STOP")

    def test_shallow_breach_in_quiet_window_is_ignored(self):
        """083310(2026-10-13) 사례: 09:05 손절가를 0.25% 밑돈 정도는 시초 구간에서 관망."""
        pos = _pos(stop_price=12_060.0, initial_stop_price=11_113.0)
        action, reason, count = judge_intraday_stop(pos, _quote(12_030.0), 672.0, 0, IN_QUIET)
        assert (action, reason, count) == ("HOLD", "STOP_BREACH_QUIET", 0)

    def test_trailing_reason_when_stop_was_raised(self):
        pos = _pos(stop_price=10_500.0, initial_stop_price=9_000.0)
        action, reason, _ = judge_intraday_stop(pos, _quote(10_000.0), 500.0, 0, AFTER_QUIET)
        assert (action, reason) == ("SELL_ALL", "TRAILING_STOP")

    def test_emergency_drop_sells_immediately(self):
        action, reason, _ = judge_intraday_stop(_pos(), _quote(9_500.0, change_pct=-8.5), 500.0, 0, IN_QUIET)
        assert (action, reason) == ("SELL_ALL", "EMERGENCY_EXIT")

    def test_missing_atr_falls_back_to_confirmation_only(self):
        action, reason, count = judge_intraday_stop(_pos(), _quote(8_000.0), None, 0, AFTER_QUIET)
        assert (action, reason, count) == ("HOLD", "STOP_BREACH_PENDING", 1)

    def test_missing_quote_holds_and_keeps_count(self):
        assert judge_intraday_stop(_pos(), {}, 500.0, 2, AFTER_QUIET) == ("HOLD", "MISSING_QUOTE", 2)


class MockQuoteClient:
    def __init__(self, quotes):
        self.quotes = quotes

    def get_current_quote(self, ticker):
        return self.quotes.get(ticker, {})


class MockOrderClient:
    def __init__(self, spendable_cash=10_000_000.0):
        self.orders = []
        self.spendable_cash = spendable_cash

    def get_balance(self, verbose=True):
        return {"cash": {"cash_balance": self.spendable_cash, "spendable_cash": self.spendable_cash}}

    def place_order(self, ticker, side, quantity, price=None, order_type="market"):
        self.orders.append({"ticker": ticker, "side": side, "quantity": quantity})
        return {"success": True, "order_no": f"MOCK{len(self.orders)}", "message": ""}


@pytest.fixture()
def session_factory():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)


def _add_position(session_factory, **overrides):
    base = dict(
        ticker="005930", market="KOSPI", sector="반도체", primary_theme="AI", status="OPEN",
        entry_price=10_000.0, entry_rank=5,
        initial_stop_price=9_000.0, initial_risk_per_share=1_000.0,
        stop_price=9_000.0, highest_price=10_000.0,
        average_price=10_000.0, quantity=35, target_shares=35,
        entry_count=1, last_entry_price=10_000.0, partial_profit_taken=False,
    )
    base.update(overrides)
    s = session_factory()
    s.add(TradePosition(**base))
    s.commit()
    s.close()


def _add_price_history(session_factory, ticker="005930", days=25, tr=500.0):
    """True Range가 정확히 tr이 되도록 고가-저가 폭만 있는 평평한 일봉 - ATR20 = tr."""
    s = session_factory()
    for i in range(days):
        s.add(StockPriceHistory(
            ticker=ticker, market="KOSPI", trade_date=f"202609{i + 1:02d}",
            open=10_000, high=10_000 + tr / 2, low=10_000 - tr / 2, close=10_000, volume=1,
        ))
    s.commit()
    s.close()


NOW = datetime(2026, 10, 15, 10, 0, tzinfo=KST)


class TestRunTick:
    def test_load_atr20_uses_only_days_before_today(self, session_factory):
        _add_price_history(session_factory)
        s = session_factory()
        assert load_atr20(s, "005930", "20261015") == pytest.approx(500.0)
        s.close()

    def test_confirmed_breach_sells_and_closes_position(self, session_factory):
        _add_position(session_factory)
        _add_price_history(session_factory)
        orders = MockOrderClient()
        monitor = IntradayStopMonitor(session_factory, MockQuoteClient({"005930": _quote(8_950.0)}), orders)

        for _ in range(2):
            assert monitor.run_tick(NOW)["sold_all"] == 0
        assert monitor.run_tick(NOW)["sold_all"] == 1

        assert orders.orders == [{"ticker": "005930", "side": "sell", "quantity": 35}]
        s = session_factory()
        pos = s.query(TradePosition).one()
        assert (pos.status, pos.close_reason) == ("CLOSED", "INITIAL_STOP")
        assert s.query(TradingHistory).one().signal_source == "EXIT_INITIAL_STOP"
        s.close()

    def test_raises_stop_from_intraday_high(self, session_factory):
        """당일 고가 12,000원(+2R) -> 트레일링 12,000 - 500x3 = 10,500원으로 장중 상향."""
        _add_position(session_factory)
        _add_price_history(session_factory)
        monitor = IntradayStopMonitor(
            session_factory, MockQuoteClient({"005930": _quote(11_500.0, high=12_000.0)}), MockOrderClient(),
        )

        assert monitor.run_tick(NOW)["stops_raised"] == 1

        s = session_factory()
        pos = s.query(TradePosition).one()
        assert float(pos.stop_price) == 10_500.0
        assert float(pos.highest_price) == 12_000.0
        s.close()

    def test_closed_position_is_skipped(self, session_factory):
        _add_position(session_factory, status="CLOSED")
        orders = MockOrderClient()
        monitor = IntradayStopMonitor(session_factory, MockQuoteClient({"005930": _quote(8_000.0)}), orders)
        assert monitor.run_tick(NOW)["checked"] == 0
        assert orders.orders == []

    def test_quote_failure_skips_without_order(self, session_factory):
        _add_position(session_factory)
        orders = MockOrderClient()
        monitor = IntradayStopMonitor(session_factory, MockQuoteClient({}), orders)
        assert monitor.run_tick(NOW)["quote_failed"] == 1
        assert orders.orders == []

    def test_dry_run_never_writes_db(self, session_factory):
        """dry-run은 매도 판정이 나도 주문/포지션/거래기록/손절가 어느 것도 바꾸지 않는다."""
        _add_position(session_factory)
        _add_price_history(session_factory)
        orders = MockOrderClient()
        monitor = IntradayStopMonitor(
            session_factory, MockQuoteClient({"005930": _quote(8_000.0, change_pct=-9.0)}), orders, dry_run=True,
        )
        assert monitor.run_tick(NOW)["sold_all"] == 1  # 판정은 그대로

        s = session_factory()
        assert s.query(TradePosition).one().status == "OPEN"
        assert s.query(TradingHistory).count() == 0
        s.close()
        assert orders.orders == []

    def test_dry_run_does_not_persist_stop_raise(self, session_factory):
        _add_position(session_factory)
        _add_price_history(session_factory)
        monitor = IntradayStopMonitor(
            session_factory, MockQuoteClient({"005930": _quote(11_500.0, high=12_000.0)}), MockOrderClient(), dry_run=True,
        )
        assert monitor.run_tick(NOW)["stops_raised"] == 1
        s = session_factory()
        assert float(s.query(TradePosition).one().stop_price) == 9_000.0
        s.close()


def _add_ranking(session_factory, ticker="000660", rank=1, final=85.0, sector=75.0, theme=70.0):
    s = session_factory()
    s.add(StockHierarchicalScore(
        timestamp=datetime(2026, 10, 14, 13, 0), ticker=ticker, market="KOSPI", sector="IT", primary_theme="HBM",
        final_score=final, sector_score=sector, theme_score=theme, overall_rank=rank,
    ))
    s.commit()
    s.close()


class TestIntradayTrading:
    """【2026-10-14】장중 매매 틱: 기존 파이프라인을 1분 주기로 재사용."""

    def test_enters_new_position_intraday(self, session_factory):
        _add_ranking(session_factory)
        _add_price_history(session_factory, ticker="000660")  # 전일 종가 10,000 / ATR20 500
        orders = MockOrderClient()
        monitor = IntradayStopMonitor(session_factory, MockQuoteClient({"000660": _quote(10_100.0)}), orders)

        result = monitor.run_cycle(NOW, include_trading=True)

        assert result["trading"]["entry"]["entered"] == 1
        assert orders.orders[0]["side"] == "buy"
        s = session_factory()
        pos = s.query(TradePosition).one()
        assert (pos.ticker, pos.status) == ("000660", "OPEN")
        s.close()

    def test_next_tick_does_not_buy_same_ticker_again(self, session_factory):
        _add_ranking(session_factory)
        _add_price_history(session_factory, ticker="000660")
        orders = MockOrderClient()
        monitor = IntradayStopMonitor(session_factory, MockQuoteClient({"000660": _quote(10_100.0)}), orders)

        monitor.run_cycle(NOW, include_trading=True)
        monitor.run_cycle(NOW, include_trading=True)

        assert [o["side"] for o in orders.orders] == ["buy"]

    def test_recently_closed_ticker_is_not_reentered(self, session_factory):
        _add_ranking(session_factory)
        _add_price_history(session_factory, ticker="000660")
        _add_position(session_factory, ticker="000660", status="CLOSED", closed_at=datetime.now(), close_reason="INITIAL_STOP")
        orders = MockOrderClient()
        monitor = IntradayStopMonitor(session_factory, MockQuoteClient({"000660": _quote(10_100.0)}), orders)

        monitor.run_cycle(NOW, include_trading=True)

        assert orders.orders == []

    def test_pyramiding_runs_intraday(self, session_factory):
        """보유 005930(진입 10,000, ATR 500) 현재가 10,600 -> +1N 돌파 추가매수(랭킹 유지 조건 충족)."""
        _add_position(session_factory)
        _add_price_history(session_factory)
        _add_ranking(session_factory, ticker="005930", rank=3)
        orders = MockOrderClient()
        monitor = IntradayStopMonitor(session_factory, MockQuoteClient({"005930": _quote(10_600.0)}), orders)

        result = monitor.run_cycle(NOW, include_trading=True)

        assert result["trading"]["pyramiding"]["added"] == 1
        assert orders.orders[0]["side"] == "buy"

    def test_stop_only_mode_skips_trading(self, session_factory):
        _add_ranking(session_factory)
        _add_price_history(session_factory, ticker="000660")
        orders = MockOrderClient()
        monitor = IntradayStopMonitor(session_factory, MockQuoteClient({"000660": _quote(10_100.0)}), orders)

        result = monitor.run_cycle(NOW, include_trading=False)

        assert "trading" not in result
        assert orders.orders == []

    def test_dry_run_trading_never_writes_db(self, session_factory):
        _add_ranking(session_factory)
        _add_price_history(session_factory, ticker="000660")
        orders = MockOrderClient()
        monitor = IntradayStopMonitor(
            session_factory, MockQuoteClient({"000660": _quote(10_100.0)}), orders, dry_run=True,
        )

        result = monitor.run_cycle(NOW, include_trading=True)

        assert result["trading"]["entry"]["entered"] == 1  # 판정은 그대로
        assert orders.orders == []
        s = session_factory()
        assert s.query(TradePosition).count() == 0
        assert s.query(TradingHistory).count() == 0
        s.close()


class CountingOrderClient(MockOrderClient):
    """잔고조회 횟수를 세고, None을 넣으면 조회 실패(빈 dict)를 흉내 낸다."""

    def __init__(self, spendable_cash=10_000_000.0):
        super().__init__(spendable_cash)
        self.balance_calls = 0

    def get_balance(self, verbose=True):
        self.balance_calls += 1
        if self.spendable_cash is None:
            return {}
        return super().get_balance(verbose)


class TestBalanceCache:
    """【2026-10-30】잔고조회 캐싱 - KIS 원장 초당 한도(EGW00215) 회피."""

    def _waiting_candidate(self, session_factory):
        """후보는 있지만 섹터 미달로 진입하지 않는 상태(매 틱 잔고가 필요한 상황)."""
        _add_ranking(session_factory, sector=50.0)
        _add_price_history(session_factory, ticker="000660")

    def test_reuses_balance_within_cache_window(self, session_factory):
        self._waiting_candidate(session_factory)
        orders = CountingOrderClient()
        monitor = IntradayStopMonitor(session_factory, MockQuoteClient({"000660": _quote(10_100.0)}), orders)

        for minute in range(5):  # 10:00~10:04 - 5분(300초) 안
            monitor.run_cycle(NOW + timedelta(minutes=minute), include_trading=True)
        assert orders.balance_calls == 1

        monitor.run_cycle(NOW + timedelta(minutes=5), include_trading=True)
        assert orders.balance_calls == 2

    def test_failure_uses_last_good_value(self, session_factory):
        orders = CountingOrderClient(spendable_cash=3_000_000.0)
        monitor = IntradayStopMonitor(session_factory, MockQuoteClient({}), orders)
        assert monitor._available_cash(NOW) == 3_000_000.0

        orders.spendable_cash = None
        assert monitor._available_cash(NOW + timedelta(minutes=10)) == 3_000_000.0

    def test_failure_without_any_good_value_returns_zero(self, session_factory):
        orders = CountingOrderClient(spendable_cash=None)
        monitor = IntradayStopMonitor(session_factory, MockQuoteClient({}), orders)
        assert monitor._available_cash(NOW) == 0.0

    def test_buy_forces_refresh_and_caps_cash_until_kis_reflects_it(self, session_factory):
        _add_ranking(session_factory)
        _add_price_history(session_factory, ticker="000660")
        orders = CountingOrderClient(spendable_cash=5_000_000.0)
        monitor = IntradayStopMonitor(session_factory, MockQuoteClient({"000660": _quote(10_100.0)}), orders)

        monitor.run_cycle(NOW, include_trading=True)
        assert orders.orders[0]["side"] == "buy"
        spent = orders.orders[0]["quantity"] * 10_100.0
        assert orders.balance_calls == 1

        # KIS가 아직 매수를 반영하지 않음(5,000,000 그대로) -> 상한(매수 전 - 매수 대금) 적용, 즉시 재조회
        assert monitor._available_cash(NOW + timedelta(minutes=1)) == pytest.approx(5_000_000.0 - spent)
        assert orders.balance_calls == 2

        # KIS 반영 후(상한 이하로 내려옴) -> 상한 해제, KIS 값을 그대로 사용
        orders.spendable_cash = 4_000_000.0
        assert monitor._available_cash(NOW + timedelta(minutes=7)) == 4_000_000.0
        assert monitor._cash_ceiling is None


class RecordingNotifier:
    def __init__(self):
        self.sent = []

    def send(self, text, key=None):
        self.sent.append((key, text))
        return True


class FailingOrderClient(MockOrderClient):
    def place_order(self, ticker, side, quantity, price=None, order_type="market"):
        self.orders.append({"ticker": ticker, "side": side, "quantity": quantity})
        return {"success": False, "order_no": None, "message": "EGW00215 초당 거래건수 초과"}


class TestAlerts:
    """【2026-10-30】주문 실패/예외 텔레그램 알림."""

    def test_stop_sell_failure_alerts(self, session_factory):
        _add_position(session_factory)
        _add_price_history(session_factory)
        notifier = RecordingNotifier()
        monitor = IntradayStopMonitor(session_factory, MockQuoteClient({"005930": _quote(8_950.0)}),
                                      FailingOrderClient(), notifier=notifier)

        for _ in range(3):
            monitor.run_tick(NOW)

        assert [k for k, _ in notifier.sent] == ["stop_fail:005930"]
        assert "손절 매도 주문 실패" in notifier.sent[0][1] and "EGW00215" in notifier.sent[0][1]
        s = session_factory()
        assert s.query(TradePosition).one().status == "OPEN"  # 실패했으니 포지션은 그대로
        s.close()

    def test_entry_order_failure_alerts(self, session_factory):
        _add_ranking(session_factory)
        _add_price_history(session_factory, ticker="000660")
        notifier = RecordingNotifier()
        monitor = IntradayStopMonitor(session_factory, MockQuoteClient({"000660": _quote(10_100.0)}),
                                      FailingOrderClient(), notifier=notifier)

        monitor.run_cycle(NOW, include_trading=True)

        assert [k for k, _ in notifier.sent] == ["order_fail:신규진입 매수:000660"]

    def test_trading_tick_exception_alerts(self, session_factory):
        notifier = RecordingNotifier()
        monitor = IntradayStopMonitor(session_factory, MockQuoteClient({}), MockOrderClient(), notifier=notifier)
        monitor._ranking = lambda session, today: (_ for _ in ()).throw(RuntimeError("db down"))

        monitor.run_trading_tick(NOW, {})

        assert notifier.sent[0][0] == "exception:trading_tick"
        assert "db down" in notifier.sent[0][1]

    def test_success_sends_no_alert(self, session_factory):
        _add_ranking(session_factory)
        _add_price_history(session_factory, ticker="000660")
        notifier = RecordingNotifier()
        monitor = IntradayStopMonitor(session_factory, MockQuoteClient({"000660": _quote(10_100.0)}),
                                      MockOrderClient(), notifier=notifier)

        monitor.run_cycle(NOW, include_trading=True)

        assert notifier.sent == []
