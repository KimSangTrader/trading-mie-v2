"""exit_engine.py 테스트 (Phase 6-2).

업로드 문서(miev2tradingsell.txt) §13의 종목 A 예시(700만원 계좌, 매수가
10,000원, ATR20 500원, 초기손절 9,000원, 35주, 1주당 위험 1,000원)를 그대로
픽스처로 써서, 구현이 문서의 수치/우선순위와 정확히 일치하는지 확인한다."""
import pytest
from market_intelligence.trade_execution.config import ExitConfig
from market_intelligence.trade_execution.exit_engine import (
    analyze_exit,
    update_stop,
    get_trailing_atr_multiple,
    calculate_trailing_stop,
    compute_lowest_low,
)

CONFIG = ExitConfig()

# 문서 §13 종목 A 공통 값
ENTRY_PRICE = 10_000.0
INITIAL_STOP = 9_000.0
RISK_PER_SHARE = 1_000.0


def _position(**overrides):
    base = {
        "entry_price": ENTRY_PRICE,
        "entry_rank": 5,
        "initial_stop_price": INITIAL_STOP,
        "stop_price": INITIAL_STOP,
        "initial_risk_per_share": RISK_PER_SHARE,
        "highest_price": ENTRY_PRICE,
        "partial_profit_taken": False,
    }
    base.update(overrides)
    return base


def _market(**overrides):
    base = {
        "current_price": 10_000.0,
        "price_change_pct": 0.0,
        "current_rank": 5,
        "sector_score": 70.0,
        "theme_score": 65.0,
        "lowest_10_days": 8_000.0,
    }
    base.update(overrides)
    return base


class TestAnalyzeExitPriority:
    """우선순위(문서 §2/§11): 긴급청산 > 손절 > 분석논리붕괴 > 부분익절 > 터틀청산 > 보유."""

    def test_emergency_exit_overrides_everything(self):
        """긴급청산 조건과 손절 조건이 동시에 성립해도 EMERGENCY_EXIT이 이긴다(1순위)."""
        action, reason, fraction = analyze_exit(
            _position(), _market(current_price=8_500.0, price_change_pct=-9.0), CONFIG
        )
        assert (action, reason, fraction) == ("SELL_ALL", "EMERGENCY_EXIT", 1.0)

    def test_emergency_exit_exactly_at_threshold(self):
        action, reason, fraction = analyze_exit(
            _position(), _market(current_price=9_500.0, price_change_pct=-8.0), CONFIG
        )
        assert action == "SELL_ALL"
        assert reason == "EMERGENCY_EXIT"

    def test_above_emergency_threshold_does_not_trigger(self):
        action, reason, fraction = analyze_exit(
            _position(), _market(current_price=9_500.0, price_change_pct=-7.9), CONFIG
        )
        assert reason != "EMERGENCY_EXIT"


class TestInitialStop:
    def test_initial_stop_hit(self):
        """현재가가 stop_price(=initial_stop_price, 아직 한 번도 안 올라감) 이하 -> INITIAL_STOP."""
        action, reason, fraction = analyze_exit(_position(), _market(current_price=8_900.0), CONFIG)
        assert (action, reason, fraction) == ("SELL_ALL", "INITIAL_STOP", 1.0)

    def test_exactly_at_stop_triggers(self):
        action, reason, fraction = analyze_exit(_position(), _market(current_price=9_000.0), CONFIG)
        assert action == "SELL_ALL"
        assert reason == "INITIAL_STOP"

    def test_above_stop_holds(self):
        """문서 Day1: 현재가 9,700원, 손절가 9,000원 -> HOLD."""
        action, reason, fraction = analyze_exit(_position(), _market(current_price=9_700.0), CONFIG)
        assert (action, reason, fraction) == ("HOLD", "NONE", 0.0)

    def test_trailing_stop_hit_after_ratchet(self):
        """stop_price가 initial_stop_price보다 위로 올라간 뒤(=트레일링 발동 후) 그 선을
        하회하면 INITIAL_STOP이 아니라 TRAILING_STOP으로 구분돼야 한다."""
        pos = _position(stop_price=12_750.0)  # update_stop()이 이미 올려놓은 상태 가정
        action, reason, fraction = analyze_exit(pos, _market(current_price=12_500.0), CONFIG)
        assert (action, reason, fraction) == ("SELL_ALL", "TRAILING_STOP", 1.0)

    def test_missing_current_price_holds_safely(self):
        action, reason, fraction = analyze_exit(_position(), _market(current_price=None), CONFIG)
        assert (action, reason, fraction) == ("HOLD", "MISSING_CURRENT_PRICE", 0.0)


class TestThesisCollapse:
    def test_rank_collapse(self):
        """entry_rank=5 -> current_rank=90 (drop=85 >= 80) -> RANK_COLLAPSE."""
        pos = _position(entry_rank=5)
        mkt = _market(current_price=9_800.0, current_rank=90)  # 손절가(9,000) 위, 아직 안 걸림
        action, reason, fraction = analyze_exit(pos, mkt, CONFIG)
        assert (action, reason, fraction) == ("SELL_ALL", "RANK_COLLAPSE", 1.0)

    def test_rank_drop_below_threshold_does_not_trigger(self):
        pos = _position(entry_rank=5)
        mkt = _market(current_price=9_800.0, current_rank=84)  # drop=79 < 80
        action, reason, fraction = analyze_exit(pos, mkt, CONFIG)
        assert reason != "RANK_COLLAPSE"

    def test_sector_theme_collapse(self):
        mkt = _market(current_price=9_800.0, sector_score=40.0, theme_score=44.0)
        action, reason, fraction = analyze_exit(_position(), mkt, CONFIG)
        assert (action, reason, fraction) == ("SELL_ALL", "SECTOR_THEME_COLLAPSE", 1.0)

    def test_only_one_side_weak_does_not_trigger(self):
        """Sector/Theme 둘 다 45 미만이어야 한다(AND) - 하나만 약하면 아직 청산 안 함."""
        mkt = _market(current_price=9_800.0, sector_score=40.0, theme_score=60.0)
        action, reason, fraction = analyze_exit(_position(), mkt, CONFIG)
        assert reason != "SECTOR_THEME_COLLAPSE"


class TestPartialTakeProfit:
    def test_document_day8_example(self):
        """문서 Day8: 현재가 12,000원 -> +2R -> 25% 부분 익절."""
        action, reason, fraction = analyze_exit(
            _position(stop_price=10_000.0), _market(current_price=12_000.0), CONFIG
        )
        assert (action, reason, fraction) == ("PARTIAL_SELL", "TAKE_PROFIT_2R", 0.25)

    def test_below_2r_holds(self):
        """문서 Day3: 현재가 10,500원 -> +0.5R -> HOLD."""
        action, reason, fraction = analyze_exit(_position(), _market(current_price=10_500.0), CONFIG)
        assert (action, reason, fraction) == ("HOLD", "NONE", 0.0)

    def test_already_taken_does_not_retrigger(self):
        pos = _position(stop_price=10_000.0, partial_profit_taken=True)
        action, reason, fraction = analyze_exit(pos, _market(current_price=12_000.0), CONFIG)
        assert reason != "TAKE_PROFIT_2R"


class TestTurtleExit:
    def test_below_10day_low_triggers(self):
        mkt = _market(current_price=7_900.0, lowest_10_days=8_000.0)
        # stop_price(9,000)보다 낮아 사실 손절이 먼저 걸림 - 손절선보다 위에서
        # 터틀청산만 단독으로 걸리는 경우를 보려면 stop을 더 낮춰야 한다.
        pos = _position(stop_price=7_000.0, initial_stop_price=7_000.0)
        action, reason, fraction = analyze_exit(pos, mkt, CONFIG)
        assert (action, reason, fraction) == ("SELL_ALL", "TURTLE_10DAY_EXIT", 1.0)

    def test_above_10day_low_does_not_trigger(self):
        pos = _position(stop_price=7_000.0, initial_stop_price=7_000.0)
        mkt = _market(current_price=8_500.0, lowest_10_days=8_000.0)
        action, reason, fraction = analyze_exit(pos, mkt, CONFIG)
        assert reason != "TURTLE_10DAY_EXIT"


class TestGetTrailingAtrMultiple:
    def test_below_2r_returns_none(self):
        assert get_trailing_atr_multiple(1.9, CONFIG) is None

    def test_2r_to_4r_returns_3x(self):
        assert get_trailing_atr_multiple(2.0, CONFIG) == 3.0
        assert get_trailing_atr_multiple(3.9, CONFIG) == 3.0

    def test_4r_and_above_returns_2_5x(self):
        assert get_trailing_atr_multiple(4.0, CONFIG) == 2.5
        assert get_trailing_atr_multiple(10.0, CONFIG) == 2.5


class TestCalculateTrailingStop:
    def test_document_section7_example(self):
        """문서 §7: 최고가 12,000원, ATR20 500원, 3배 -> 12,000-1,500=10,500원."""
        assert calculate_trailing_stop(current_stop=9_000.0, highest_price=12_000.0, atr20=500.0, atr_multiple=3.0) == 10_500.0

    def test_never_lowers_stop(self):
        """후보 손절가가 기존보다 낮으면(하락 반전) 절대 낮추지 않는다."""
        result = calculate_trailing_stop(current_stop=10_500.0, highest_price=11_000.0, atr20=500.0, atr_multiple=3.0)
        assert result == 10_500.0  # candidate=11,000-1,500=9,500 < 10,500 -> 유지


class TestUpdateStop:
    def test_document_day5_breakeven(self):
        """문서 Day5: 현재가 11,000원(+1R) -> 손절가 9,000 -> 10,000원(본전)으로 상승."""
        pos = _position(stop_price=9_000.0, highest_price=10_000.0)
        result = update_stop(pos, current_high=11_000.0, atr20=500.0, current_price=11_000.0, config=CONFIG)
        assert result["stop_price"] == 10_000.0

    def test_document_section7_2r_trailing(self):
        """문서 §7: 최고가 12,000원 도달(+2R), ATR20 500 -> 트레일링 스톱 10,500원."""
        pos = _position(stop_price=9_000.0, highest_price=10_000.0)
        result = update_stop(pos, current_high=12_000.0, atr20=500.0, current_price=12_000.0, config=CONFIG)
        assert result["stop_price"] == 10_500.0
        assert result["highest_price"] == 12_000.0

    def test_day15_discrepancy_with_document_walkthrough(self):
        """문서 §13 Day15는 "최고가 14,000원, ATR20 500원 -> Trailing Stop =
        14,000-(500x3)=12,500원"이라고 서술한다. 하지만 이 시점 profit_r =
        (14,000-10,000)/1,000 = 4.0으로, 같은 문서 §8/§12 자체 공식("+4R
        이상이면 ATR 2.5배")을 적용하면 14,000-(500x2.5)=12,750원이 맞다
        (3배를 쓴 12,500원과 다름). Phase 6-1의 E종목(14주/21주) 불일치와
        같은 유형의 문서 자체 오탈자로 판단 - 이 구현은 문서가 명시한 공식
        (§8/§12)을 그대로 따르고, 서술형 예시 문장의 숫자(12,500원)는 따라가지
        않는다. (Day15는 "현재가"가 명시되지 않아 최고가=현재가로 가정했다.)"""
        pos = _position(stop_price=10_000.0, highest_price=12_000.0)  # Day5 이후 본전 손절 상태 가정
        result = update_stop(pos, current_high=14_000.0, atr20=500.0, current_price=14_000.0, config=CONFIG)
        assert result["stop_price"] == 12_750.0  # 문서 서술의 12,500원이 아님 - 위 설명 참고
        assert result["highest_price"] == 14_000.0

    def test_document_day20_full_exit_after_trailing(self):
        """문서 Day20: 가격이 14,000 -> 13,500 -> 12,500으로 하락하며 트레일링
        스톱에 도달해 "남은 수량 전량 매도". 위 discrepancy 테스트에서 계산한
        올바른 손절가(12,750원) 기준으로도 12,500원에서는 이미 하회해 SELL_ALL이
        나와야 한다(방향성 결론은 문서와 동일, 도달 시점만 이 구현이 더 보수적)."""
        pos = _position(stop_price=12_750.0)
        action, reason, fraction = analyze_exit(pos, _market(current_price=12_500.0), CONFIG)
        assert (action, reason, fraction) == ("SELL_ALL", "TRAILING_STOP", 1.0)

    def test_below_1r_does_not_move_stop(self):
        """문서 Day3: +0.5R -> 아직 본전 보호도 트레일링도 시작 안 함, 손절가 그대로."""
        pos = _position(stop_price=9_000.0, highest_price=10_500.0)
        result = update_stop(pos, current_high=10_500.0, atr20=500.0, current_price=10_500.0, config=CONFIG)
        assert result["stop_price"] == 9_000.0

    def test_never_lowers_stop_on_pullback(self):
        """이미 트레일링으로 올라간 손절가는 가격이 눌려도 절대 다시 안 내려간다."""
        pos = _position(stop_price=10_500.0, highest_price=12_000.0)
        result = update_stop(pos, current_high=11_800.0, atr20=500.0, current_price=11_800.0, config=CONFIG)
        assert result["stop_price"] == 10_500.0
        assert result["highest_price"] == 12_000.0  # 최고가도 내려가지 않음

    @pytest.mark.parametrize(
        "kwargs",
        [
            dict(current_high=None, atr20=500.0, current_price=10_000.0),
            dict(current_high=10_000.0, atr20=None, current_price=10_000.0),
            dict(current_high=10_000.0, atr20=0, current_price=10_000.0),
            dict(current_high=10_000.0, atr20=500.0, current_price=None),
        ],
    )
    def test_missing_or_invalid_inputs_return_none(self, kwargs):
        assert update_stop(_position(), config=CONFIG, **kwargs) is None


class TestComputeLowestLow:
    def test_basic(self):
        rows = [{"low": v} for v in [100, 90, 95, 80, 85, 92, 88, 91, 87, 93]]
        assert compute_lowest_low(rows, period=10) == 80

    def test_uses_only_most_recent_period(self):
        rows = [{"low": 1}] + [{"low": v} for v in [100, 90, 95, 80, 85, 92, 88, 91, 87, 93]]
        assert compute_lowest_low(rows, period=10) == 80  # 맨 앞의 1은 기간 밖

    def test_insufficient_rows_returns_none(self):
        rows = [{"low": v} for v in [100, 90, 95]]
        assert compute_lowest_low(rows, period=10) is None

    def test_missing_low_returns_none(self):
        rows = [{"low": v} for v in [100, 90, 95, 80, 85, 92, 88, None, 87, 93]]
        assert compute_lowest_low(rows, period=10) is None

    def test_empty_returns_none(self):
        assert compute_lowest_low([], period=10) is None
