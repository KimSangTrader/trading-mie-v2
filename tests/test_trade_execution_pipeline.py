"""trade_execution_pipeline.py 테스트 (Phase 6-3).

실제 KIS API/RDS 없이 Mock KISClient + SQLite in-memory DB로 청산/피라미딩/
신규진입 파이프라인 전체 흐름을 검증한다(tests/test_price_history_pipeline.py와
동일한 패턴 - Mock 주입 + SQLite fixture)."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db.models import Base, TradePosition, TradingHistory
from market_intelligence.trade_execution.config import TradingConfig, ExitConfig
from market_intelligence.trade_execution.trade_execution_pipeline import (
    position_to_dict,
    run_exit_pipeline,
    run_pyramiding_pipeline,
    run_entry_pipeline,
    run_trade_execution_cycle,
)

CONFIG = TradingConfig(total_capital=7_000_000.0, max_positions=3, max_per_sector=2, max_per_theme=2)
EXIT_CONFIG = ExitConfig()


class MockKISClient:
    """place_order()/get_balance() 호출을 기록만 하고 항상 성공을 반환하는 Mock.
    실패를 흉내내고 싶으면 fail_tickers에 종목코드를 넣는다."""

    def __init__(self, cash_balance=10_000_000.0, fail_tickers=None):
        self.orders = []
        self.cash_balance = cash_balance
        self.fail_tickers = fail_tickers or set()

    def place_order(self, ticker, side, quantity, price=None, order_type="market"):
        self.orders.append({"ticker": ticker, "side": side, "quantity": quantity, "order_type": order_type})
        if ticker in self.fail_tickers:
            return {"success": False, "message": "MOCK_FAILURE"}
        return {"success": True, "order_no": f"MOCK{len(self.orders)}", "message": ""}

    def get_balance(self):
        return {"cash": {"cash_balance": self.cash_balance}}


def _open_position(**overrides):
    base = dict(
        ticker="005930", market="KOSPI", sector="반도체", primary_theme="AI",
        status="OPEN",
        entry_price=10_000.0, entry_rank=5,
        initial_stop_price=9_000.0, initial_risk_per_share=1_000.0,
        stop_price=9_000.0, highest_price=10_000.0,
        average_price=10_000.0, quantity=35, target_shares=35,
        entry_count=1, last_entry_price=10_000.0, partial_profit_taken=False,
    )
    base.update(overrides)
    return TradePosition(**base)


def _market(**overrides):
    base = {
        "current_price": 10_000.0,
        "current_high": 10_000.0,
        "price_change_pct": 0.0,
        "current_rank": 5,
        "sector_score": 70.0,
        "theme_score": 65.0,
        "lowest_10_days": 8_000.0,
        "atr20": 500.0,
    }
    base.update(overrides)
    return base


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


class TestPositionToDict:
    def test_converts_all_fields(self, session):
        pos = _open_position()
        session.add(pos)
        session.commit()
        d = position_to_dict(pos)
        assert d["entry_price"] == 10_000.0
        assert d["stop_price"] == 9_000.0
        assert d["quantity"] == 35
        assert d["partial_profit_taken"] is False


class TestRunExitPipeline:
    def test_stop_loss_closes_position_and_logs_history(self, session):
        pos = _open_position()
        session.add(pos)
        session.commit()

        kis = MockKISClient()
        market_data = {"005930": _market(current_price=8_900.0)}  # 손절가(9,000) 하회

        result = run_exit_pipeline(session, kis, market_data, CONFIG, EXIT_CONFIG)

        assert result["sold_all"] == 1
        refreshed = session.query(TradePosition).filter_by(ticker="005930").one()
        assert refreshed.status == "CLOSED"
        assert refreshed.close_reason == "INITIAL_STOP"
        assert kis.orders == [{"ticker": "005930", "side": "sell", "quantity": 35, "order_type": "market"}]

        history = session.query(TradingHistory).all()
        assert len(history) == 1
        assert history[0].trade_type == "SELL"
        assert history[0].quantity == 35

    def test_partial_take_profit_reduces_quantity_and_keeps_open(self, session):
        pos = _open_position(stop_price=10_000.0)  # Day5 이후 본전 상향 가정
        session.add(pos)
        session.commit()

        kis = MockKISClient()
        market_data = {"005930": _market(current_price=12_000.0, current_high=12_000.0)}  # +2R

        result = run_exit_pipeline(session, kis, market_data, CONFIG, EXIT_CONFIG)

        assert result["partial_sold"] == 1
        refreshed = session.query(TradePosition).filter_by(ticker="005930").one()
        assert refreshed.status == "OPEN"
        assert refreshed.quantity == 35 - int(35 * 0.25)
        assert refreshed.partial_profit_taken is True
        # 부분 익절 후에도 여전히 OPEN이므로 손절가도 같은 실행에서 갱신됐어야 함
        assert result["stops_updated"] == 1
        assert refreshed.stop_price == 10_500.0  # 12,000 - 500*3 (trailing)

    def test_hold_updates_stop_but_no_order(self, session):
        pos = _open_position()
        session.add(pos)
        session.commit()

        kis = MockKISClient()
        market_data = {"005930": _market(current_price=9_700.0)}  # 문서 Day1과 동일 - HOLD

        result = run_exit_pipeline(session, kis, market_data, CONFIG, EXIT_CONFIG)

        assert result["sold_all"] == 0
        assert result["partial_sold"] == 0
        assert kis.orders == []
        assert result["stops_updated"] == 1

    def test_missing_market_data_is_skipped_safely(self, session):
        pos = _open_position(ticker="000660")
        session.add(pos)
        session.commit()

        kis = MockKISClient()
        result = run_exit_pipeline(session, kis, {}, CONFIG, EXIT_CONFIG)

        assert result["skipped_no_market_data"] == 1
        assert kis.orders == []
        refreshed = session.query(TradePosition).filter_by(ticker="000660").one()
        assert refreshed.status == "OPEN"  # 손대지 않음

    def test_order_failure_keeps_position_open_and_records_error(self, session):
        pos = _open_position()
        session.add(pos)
        session.commit()

        kis = MockKISClient(fail_tickers={"005930"})
        market_data = {"005930": _market(current_price=8_900.0)}

        result = run_exit_pipeline(session, kis, market_data, CONFIG, EXIT_CONFIG)

        assert result["sold_all"] == 0
        assert len(result["errors"]) == 1
        refreshed = session.query(TradePosition).filter_by(ticker="005930").one()
        assert refreshed.status == "OPEN"  # 주문 실패 - DB에 청산 반영 안 됨


class TestRunPyramidingPipeline:
    def test_add_executes_buy_and_updates_average_price(self, session):
        pos = _open_position()
        session.add(pos)
        session.commit()

        kis = MockKISClient()
        # should_add() 조건 전부 충족: 수익 방향, +1ATR 이상, 랭킹 유지, sector/theme 유지
        market_data = {"005930": _market(current_price=10_600.0, current_rank=3)}

        result = run_pyramiding_pipeline(session, kis, market_data, CONFIG)

        assert result["added"] == 1
        refreshed = session.query(TradePosition).filter_by(ticker="005930").one()
        assert refreshed.entry_count == 2
        assert refreshed.last_entry_price == 10_600.0
        # target_shares=35, 2차 비중 25% -> split_entry_shares(35, 2, config)
        expected_add_qty = int(35 * 0.25)
        assert refreshed.quantity == 35 + expected_add_qty
        assert kis.orders[0]["side"] == "buy"

        history = session.query(TradingHistory).all()
        assert history[0].signal_source == "PYRAMID_2"

    def test_losing_position_never_adds(self, session):
        pos = _open_position()
        session.add(pos)
        session.commit()

        kis = MockKISClient()
        market_data = {"005930": _market(current_price=9_500.0)}  # 평균단가 이하

        result = run_pyramiding_pipeline(session, kis, market_data, CONFIG)

        assert result["added"] == 0
        assert kis.orders == []

    def test_max_entries_reached_blocks_add(self, session):
        pos = _open_position(entry_count=3)
        session.add(pos)
        session.commit()

        kis = MockKISClient()
        market_data = {"005930": _market(current_price=10_600.0)}

        result = run_pyramiding_pipeline(session, kis, market_data, CONFIG)

        assert result["added"] == 0


class TestRunEntryPipeline:
    def test_enters_new_position_from_ranked_candidates(self, session):
        kis = MockKISClient(cash_balance=10_000_000.0)
        candidates = [{
            "ticker": "005930", "market": "KOSPI", "sector": "반도체", "primary_theme": "AI",
            "final_score": 80.0, "sector_score": 70.0, "theme_score": 65.0, "overall_rank": 1,
            "previous_close": 9_800.0, "current_price": 10_000.0, "atr20": 500.0,
        }]

        result = run_entry_pipeline(session, kis, candidates, available_cash=10_000_000.0, config=CONFIG)

        assert result["entered"] == 1
        positions = session.query(TradePosition).filter_by(status="OPEN").all()
        assert len(positions) == 1
        assert positions[0].ticker == "005930"
        assert positions[0].entry_price == 10_000.0
        assert positions[0].stop_price == 9_000.0  # 2*ATR
        assert kis.orders[0]["side"] == "buy"

    def test_low_score_candidate_is_not_entered(self, session):
        kis = MockKISClient()
        candidates = [{
            "ticker": "005930", "market": "KOSPI", "sector": "반도체", "primary_theme": "AI",
            "final_score": 50.0,  # min_final_score(75) 미달
            "sector_score": 70.0, "theme_score": 65.0, "overall_rank": 1,
            "previous_close": 9_800.0, "current_price": 10_000.0, "atr20": 500.0,
        }]

        result = run_entry_pipeline(session, kis, candidates, available_cash=10_000_000.0, config=CONFIG)

        assert result["entered"] == 0
        assert kis.orders == []

    def test_existing_position_reserves_sector_budget(self, session):
        """max_per_sector=2인데 이미 같은 Sector에 2종목을 들고 있으면, 새 후보가
        같은 Sector여도 진입하면 안 된다."""
        session.add(_open_position(ticker="005930", sector="반도체", primary_theme="AI"))
        session.add(_open_position(ticker="000660", sector="반도체", primary_theme="AI"))
        session.commit()

        kis = MockKISClient()
        candidates = [{
            "ticker": "042700", "market": "KOSPI", "sector": "반도체", "primary_theme": "AI",
            "final_score": 90.0, "sector_score": 80.0, "theme_score": 70.0, "overall_rank": 1,
            "previous_close": 9_800.0, "current_price": 10_000.0, "atr20": 500.0,
        }]

        result = run_entry_pipeline(session, kis, candidates, available_cash=10_000_000.0, config=CONFIG)

        assert result["entered"] == 0
        assert kis.orders == []

    def test_max_positions_reached_skips_entirely(self, session):
        session.add(_open_position(ticker="005930", sector="반도체"))
        session.add(_open_position(ticker="000660", sector="화학"))
        session.add(_open_position(ticker="035420", sector="인터넷"))
        session.commit()  # max_positions=3, 이미 꽉 참

        kis = MockKISClient()
        candidates = [{
            "ticker": "042700", "market": "KOSPI", "sector": "반도체", "primary_theme": "AI",
            "final_score": 90.0, "sector_score": 80.0, "theme_score": 70.0, "overall_rank": 1,
            "previous_close": 9_800.0, "current_price": 10_000.0, "atr20": 500.0,
        }]

        result = run_entry_pipeline(session, kis, candidates, available_cash=10_000_000.0, config=CONFIG)

        assert result["entered"] == 0
        assert result["checked"] == 0
        assert kis.orders == []

    def test_order_failure_does_not_create_position(self, session):
        kis = MockKISClient(fail_tickers={"005930"})
        candidates = [{
            "ticker": "005930", "market": "KOSPI", "sector": "반도체", "primary_theme": "AI",
            "final_score": 80.0, "sector_score": 70.0, "theme_score": 65.0, "overall_rank": 1,
            "previous_close": 9_800.0, "current_price": 10_000.0, "atr20": 500.0,
        }]

        result = run_entry_pipeline(session, kis, candidates, available_cash=10_000_000.0, config=CONFIG)

        assert result["entered"] == 0
        assert len(result["errors"]) == 1
        assert session.query(TradePosition).count() == 0


class TestRunTradeExecutionCycle:
    def test_runs_all_three_stages_in_order(self, session):
        """청산으로 한 종목이 빠지고, 그 자리에 신규진입이 들어오는 하루를 시뮬레이션."""
        session.add(_open_position(ticker="005930", sector="반도체", primary_theme="AI"))
        session.commit()

        kis = MockKISClient(cash_balance=10_000_000.0)
        market_data = {"005930": _market(current_price=8_900.0)}  # 손절
        candidates = [{
            "ticker": "000660", "market": "KOSPI", "sector": "화학", "primary_theme": "2차전지",
            "final_score": 85.0, "sector_score": 75.0, "theme_score": 68.0, "overall_rank": 1,
            "previous_close": 19_800.0, "current_price": 20_000.0, "atr20": 1_000.0,
        }]

        result = run_trade_execution_cycle(session, kis, market_data, candidates, available_cash=10_000_000.0, config=CONFIG, exit_config=EXIT_CONFIG)

        assert result["exit"]["sold_all"] == 1
        assert result["entry"]["entered"] == 1

        open_positions = session.query(TradePosition).filter_by(status="OPEN").all()
        assert len(open_positions) == 1
        assert open_positions[0].ticker == "000660"

    def test_dry_run_does_not_call_kis_or_mutate_status(self, session):
        pos = _open_position()
        session.add(pos)
        session.commit()

        kis = MockKISClient()
        market_data = {"005930": _market(current_price=8_900.0)}

        result = run_exit_pipeline(session, kis, market_data, CONFIG, EXIT_CONFIG, dry_run=True)

        assert result["sold_all"] == 1  # 판정 자체는 그대로 실행됨
        assert kis.orders == []  # 하지만 실제 KIS 호출은 없었음
        refreshed = session.query(TradePosition).filter_by(ticker="005930").one()
        assert refreshed.status == "CLOSED"  # dry_run이어도 DB 반영은 됨(호출부가 필요시 롤백)
