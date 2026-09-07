"""
price_series 테스트 (Phase 5-14: Sector/Theme 공용 바스켓 스코어링 로직)

================================================================================
【변경 이력】
================================================================================
【2026-08-23】최초 생성
- 순수 계산 함수라 API/DB 없이 SQLite/네트워크 무관하게 어디서든 실행 가능.
================================================================================
"""

import pytest

from market_intelligence.price_series import (
    compute_market_returns,
    compute_ticker_metrics,
    group_price_rows_by_ticker,
    score_basket,
)


def _rows(ticker, market, closes, volumes=None, start_date="20260601"):
    """closes: 오래된 -> 최신 순서의 종가 리스트. 날짜는 순차적으로 붙인다."""
    volumes = volumes or [10000] * len(closes)
    base = int(start_date)
    out = []
    for i, (c, v) in enumerate(zip(closes, volumes)):
        # 간단히 날짜를 순차 증가시킨다(월 경계는 신경쓰지 않음 - 정렬 테스트만 필요하면
        # 문자열 정렬이 깨지므로, 여기서는 숫자 증가로 자연스러운 순서를 만든다)
        out.append({"ticker": ticker, "market": market, "trade_date": str(base + i),
                    "close": c, "volume": v})
    return out


class TestGroupPriceRowsByTicker:
    def test_groups_and_sorts_by_trade_date(self):
        rows = [
            {"ticker": "A", "trade_date": "20260812", "close": 3},
            {"ticker": "A", "trade_date": "20260810", "close": 1},
            {"ticker": "B", "trade_date": "20260810", "close": 100},
            {"ticker": "A", "trade_date": "20260811", "close": 2},
        ]
        grouped = group_price_rows_by_ticker(rows)
        assert [r["close"] for r in grouped["A"]] == [1, 2, 3]
        assert [r["close"] for r in grouped["B"]] == [100]

    def test_rows_without_ticker_are_skipped(self):
        rows = [{"trade_date": "20260810", "close": 1}]
        assert group_price_rows_by_ticker(rows) == {}


class TestComputeTickerMetrics:
    def test_returns_none_for_empty_rows(self):
        assert compute_ticker_metrics([]) is None

    def test_partial_history_leaves_longer_windows_none(self):
        # 10일치만 있으면 5일 수익률은 계산되지만 20일/60일은 None이어야 함
        closes = [100 + i for i in range(10)]  # 100..109
        rows = _rows("A", "KOSPI", closes)
        metrics = compute_ticker_metrics(rows)
        assert metrics["return_5d"] is not None
        assert metrics["return_20d"] is None
        assert metrics["return_60d"] is None
        assert metrics["ma20"] is None

    def test_return_calculation_is_correct(self):
        closes = [100] * 55 + [110]  # 56일치, 마지막날 +10%
        rows = _rows("A", "KOSPI", closes)
        metrics = compute_ticker_metrics(rows)
        assert metrics["return_1d"] == pytest.approx(10.0)
        assert metrics["return_5d"] == pytest.approx(10.0)
        assert metrics["return_20d"] == pytest.approx(10.0)
        assert metrics["return_60d"] is None  # 56일치뿐이라 60일 수익률은 불가

    def test_ma20_above_ma60_detected(self):
        # 최근 20일은 110, 그 이전 40일은 100 -> ma20=110, ma60=(40*100+20*110)/60≈103.3
        closes = [100] * 40 + [110] * 20
        rows = _rows("A", "KOSPI", closes)
        metrics = compute_ticker_metrics(rows)
        assert metrics["ma20"] == pytest.approx(110.0)
        assert metrics["ma20_above_ma60"] is True

    def test_trading_value_ratio_reflects_recent_volume_surge(self):
        closes = [100] * 25
        volumes = [1000] * 20 + [3000] * 5  # 최근 5일 거래량이 3배로 증가
        rows = _rows("A", "KOSPI", closes, volumes=volumes)
        metrics = compute_ticker_metrics(rows)
        # tv20(최근 20일 평균) 안에는 최근 5일의 급증분도 포함되므로 1.0보다는 크게 나와야 함
        assert metrics["trading_value_ratio"] > 1.0

    def test_missing_close_rows_are_skipped_not_crashed(self):
        rows = [
            {"ticker": "A", "market": "KOSPI", "trade_date": "20260810", "close": None, "volume": 100},
            {"ticker": "A", "market": "KOSPI", "trade_date": "20260811", "close": 100, "volume": 100},
        ]
        metrics = compute_ticker_metrics(rows)
        assert metrics["latest_close"] == 100
        assert metrics["data_days"] == 1


class TestComputeMarketReturns:
    def test_computes_median_return_per_market(self):
        ticker_metrics = {
            "A": {"return_5d": 1.0, "return_20d": 10.0, "return_60d": 20.0},
            "B": {"return_5d": 3.0, "return_20d": 30.0, "return_60d": 40.0},
            "C": {"return_5d": None, "return_20d": None, "return_60d": None},  # 결측
        }
        ticker_market = {"A": "KOSPI", "B": "KOSPI", "C": "KOSDAQ"}
        result = compute_market_returns(ticker_metrics, ticker_market)
        assert result["KOSPI"]["return_20d"] == pytest.approx(20.0)  # median(10, 30)
        assert result["KOSDAQ"]["return_20d"] is None  # 유일한 KOSDAQ 종목이 결측


class TestScoreBasket:
    def test_neutral_score_when_no_data_available(self):
        result = score_basket(["A", "B"], {}, {}, {})
        assert result["score"] == 50.0
        assert result["data_quality"] == 0.0

    def test_strong_basket_scores_above_neutral(self):
        # 바스켓 전체가 뚜렷한 상승 모멘텀 + 시장 대비 초과수익 + 전원 상승 + 거래대금 급증
        ticker_metrics = {
            "A": {"return_1d": 2.0, "return_5d": 8.0, "return_20d": 15.0, "return_60d": 20.0,
                  "trading_value_ratio": 1.8, "ma20_above_ma60": True},
            "B": {"return_1d": 1.5, "return_5d": 7.0, "return_20d": 14.0, "return_60d": 18.0,
                  "trading_value_ratio": 1.6, "ma20_above_ma60": True},
        }
        ticker_market = {"A": "KOSPI", "B": "KOSPI"}
        market_returns = {"KOSPI": {"return_20d": 2.0}}  # 시장은 겨우 +2%, 바스켓은 훨씬 강함

        result = score_basket(["A", "B"], ticker_metrics, ticker_market, market_returns)
        assert result["score"] > 70
        assert result["data_quality"] == 100.0

    def test_weak_basket_scores_below_neutral(self):
        ticker_metrics = {
            "A": {"return_1d": -2.0, "return_5d": -8.0, "return_20d": -15.0, "return_60d": -20.0,
                  "trading_value_ratio": 0.5, "ma20_above_ma60": False},
            "B": {"return_1d": -1.5, "return_5d": -7.0, "return_20d": -14.0, "return_60d": -18.0,
                  "trading_value_ratio": 0.6, "ma20_above_ma60": False},
        }
        ticker_market = {"A": "KOSPI", "B": "KOSPI"}
        market_returns = {"KOSPI": {"return_20d": 2.0}}

        result = score_basket(["A", "B"], ticker_metrics, ticker_market, market_returns)
        assert result["score"] < 30

    def test_partial_membership_reflected_in_data_quality(self):
        ticker_metrics = {"A": {"return_1d": 1.0, "return_5d": 1.0, "return_20d": 1.0,
                                 "return_60d": 1.0, "trading_value_ratio": 1.0, "ma20_above_ma60": True}}
        ticker_market = {"A": "KOSPI"}
        result = score_basket(["A", "B", "C", "D"], ticker_metrics, ticker_market, {})
        assert result["data_quality"] == 25.0  # 4종목 중 1종목만 데이터 있음
        assert result["member_count"] == 4
