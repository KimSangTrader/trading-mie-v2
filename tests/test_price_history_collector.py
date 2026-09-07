"""
PriceHistoryCollector 테스트 (Phase 5-13: 전체 종목 일봉 히스토리 수집기)

================================================================================
【변경 이력】
================================================================================
【2026-08-23】최초 생성
- ValuationCollector 테스트(tests/test_valuation_collector.py)와 동일한 패턴으로
  Mock KISClient를 사용해 실제 네트워크 없이 검증: 정상 수집(다건 행으로 펼치기),
  종목별 실패 시 건너뛰기, 체크포인트 이어받기, 일일 캐시 재사용, rate_limit.
================================================================================
"""

import json
import os
import tempfile
import time

from data.price_history_collector import PriceHistoryCollector, chart_to_price_rows


class MockKISClient:
    """종목코드별로 미리 정해둔 일봉 차트를 돌려주는 Mock (일부는 실패하도록 구성 가능)"""

    def __init__(self, charts=None, fail_symbols=None):
        self.charts = charts or {}
        self.fail_symbols = fail_symbols or set()
        self.call_count = 0
        self.called_symbols = []

    def get_stock_daily_chart(self, stock_code, days=60):
        self.call_count += 1
        self.called_symbols.append(stock_code)
        if stock_code in self.fail_symbols:
            raise RuntimeError("API 오류 시뮬레이션")
        return self.charts.get(stock_code, {})


def _stock(symbol, name="종목", market="KOSPI"):
    return {"symbol": symbol, "name": name, "market": market}


def _chart(symbol, dates, closes, opens=None, highs=None, lows=None, volumes=None):
    n = len(dates)
    return {
        "symbol": symbol,
        "dates": dates,
        "opens": opens or closes,
        "highs": highs or closes,
        "lows": lows or closes,
        "closes": closes,
        "volumes": volumes or [1000] * n,
    }


class TestPriceHistoryCollectorBasic:
    def test_collects_and_flattens_rows_per_symbol(self):
        client = MockKISClient(charts={
            "005930": _chart("005930", ["20260810", "20260811"], [70000, 71000]),
            "000660": _chart("000660", ["20260810", "20260811"], [200000, 201000]),
        })
        with tempfile.TemporaryDirectory() as cache_dir:
            collector = PriceHistoryCollector(kis_client=client, cache_dir=cache_dir)
            records = collector.collect([_stock("005930"), _stock("000660")], rate_limit_sec=0)

            assert len(records) == 4  # 2종목 x 2일
            by_symbol = {}
            for r in records:
                by_symbol.setdefault(r["symbol"], []).append(r)
            assert len(by_symbol["005930"]) == 2
            assert by_symbol["005930"][1]["close"] == 71000
            assert client.call_count == 2

    def test_failed_symbol_does_not_stop_collection(self):
        client = MockKISClient(
            charts={"005930": _chart("005930", ["20260810"], [70000])},
            fail_symbols={"999999"},
        )
        with tempfile.TemporaryDirectory() as cache_dir:
            collector = PriceHistoryCollector(kis_client=client, cache_dir=cache_dir)
            records = collector.collect([_stock("999999"), _stock("005930")], rate_limit_sec=0)

            symbols = {r["symbol"] for r in records}
            assert symbols == {"005930"}  # 실패 종목은 행이 아예 없음

    def test_empty_chart_produces_no_rows(self):
        client = MockKISClient(charts={})  # 빈 응답
        with tempfile.TemporaryDirectory() as cache_dir:
            collector = PriceHistoryCollector(kis_client=client, cache_dir=cache_dir)
            records = collector.collect([_stock("005930")], rate_limit_sec=0)
            assert records == []

    def test_empty_stock_list_returns_empty(self):
        client = MockKISClient()
        with tempfile.TemporaryDirectory() as cache_dir:
            collector = PriceHistoryCollector(kis_client=client, cache_dir=cache_dir)
            assert collector.collect([], rate_limit_sec=0) == []
            assert client.call_count == 0


class TestPriceHistoryCollectorCheckpoint:
    def test_resumes_from_checkpoint_without_refetching(self):
        client = MockKISClient(charts={
            "005930": _chart("005930", ["20260810"], [70000]),
            "000660": _chart("000660", ["20260810"], [200000]),
        })
        with tempfile.TemporaryDirectory() as cache_dir:
            collector = PriceHistoryCollector(kis_client=client, cache_dir=cache_dir)

            checkpoint = {
                "done_symbols": ["005930"],
                "rows": [{"symbol": "005930", "market": "KOSPI", "date": "20260810",
                          "open": 70000, "high": 70000, "low": 70000, "close": 70000,
                          "volume": 1000}],
                "updated_at": "2026-08-23T00:00:00",
            }
            with open(collector._checkpoint_path(), "w", encoding="utf-8") as f:
                json.dump(checkpoint, f)

            records = collector.collect([_stock("005930"), _stock("000660")], rate_limit_sec=0)

            assert "005930" not in client.called_symbols
            assert client.called_symbols == ["000660"]
            symbols = {r["symbol"] for r in records}
            assert symbols == {"005930", "000660"}  # 체크포인트 행 + 새로 수집한 행 모두 포함

    def test_get_or_collect_clears_checkpoint_after_success(self):
        client = MockKISClient(charts={"005930": _chart("005930", ["20260810"], [70000])})
        with tempfile.TemporaryDirectory() as cache_dir:
            collector = PriceHistoryCollector(kis_client=client, cache_dir=cache_dir)
            collector.get_or_collect([_stock("005930")], force_refresh=True, rate_limit_sec=0)
            assert not os.path.exists(collector._checkpoint_path())


class TestPriceHistoryCollectorDailyCache:
    def test_get_or_collect_reuses_same_day_cache(self):
        client = MockKISClient(charts={"005930": _chart("005930", ["20260810"], [70000])})
        with tempfile.TemporaryDirectory() as cache_dir:
            collector = PriceHistoryCollector(kis_client=client, cache_dir=cache_dir)
            stocks = [_stock("005930")]

            first = collector.get_or_collect(stocks, rate_limit_sec=0)
            assert client.call_count == 1

            second = collector.get_or_collect(stocks, rate_limit_sec=0)
            assert client.call_count == 1  # 캐시 재사용 - 추가 호출 없음
            assert first == second

    def test_force_refresh_bypasses_cache(self):
        client = MockKISClient(charts={"005930": _chart("005930", ["20260810"], [70000])})
        with tempfile.TemporaryDirectory() as cache_dir:
            collector = PriceHistoryCollector(kis_client=client, cache_dir=cache_dir)
            stocks = [_stock("005930")]

            collector.get_or_collect(stocks, rate_limit_sec=0)
            collector.get_or_collect(stocks, force_refresh=True, rate_limit_sec=0)
            assert client.call_count == 2


class TestChartToPriceRows:
    """collect()가 내부적으로 쓰는 chart→행 변환을 main.py 등 다른 호출부도
    바로 쓸 수 있도록 모듈 함수로 뽑아낸 부분 (Phase 5-17)."""

    def test_converts_parallel_lists_to_rows(self):
        chart = _chart("005930", ["20260810", "20260811"], [70000, 71000])
        rows = chart_to_price_rows("005930", "KOSPI", chart)
        assert len(rows) == 2
        assert rows[0] == {"symbol": "005930", "market": "KOSPI", "date": "20260810",
                            "open": 70000, "high": 70000, "low": 70000,
                            "close": 70000, "volume": 1000}
        assert rows[1]["date"] == "20260811"
        assert rows[1]["close"] == 71000

    def test_empty_chart_returns_empty_list(self):
        assert chart_to_price_rows("005930", "KOSPI", {}) == []

    def test_malformed_chart_returns_empty_list_not_raises(self):
        # closes가 dates보다 짧은 경우(형식 오류) - IndexError가 나야 정상인데
        # 그걸 삼키고 빈 리스트를 돌려줘야 한다 (한 종목 실패가 전체를 막지 않음)
        broken_chart = {"dates": ["20260810", "20260811"], "opens": [70000],
                        "highs": [70000], "lows": [70000], "closes": [70000], "volumes": [1000]}
        assert chart_to_price_rows("005930", "KOSPI", broken_chart) == []


class TestPriceHistoryCollectorRateLimit:
    def test_rate_limit_sleeps_between_calls(self):
        client = MockKISClient(charts={
            "005930": _chart("005930", ["20260810"], [70000]),
            "000660": _chart("000660", ["20260810"], [200000]),
        })
        with tempfile.TemporaryDirectory() as cache_dir:
            collector = PriceHistoryCollector(kis_client=client, cache_dir=cache_dir)
            start = time.monotonic()
            collector.collect([_stock("005930"), _stock("000660")], rate_limit_sec=0.05)
            elapsed = time.monotonic() - start
            assert elapsed >= 0.04
