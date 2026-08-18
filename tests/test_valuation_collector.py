"""
ValuationCollector 테스트 (Phase 5-3: 전체 종목 PER/PBR 수집기)

================================================================================
【변경 이력】
================================================================================
【2026-08-15】최초 생성
- 실제 KIS API/네트워크 없이 Mock 클라이언트로 검증: 정상 수집, 종목별 실패 시
  건너뛰기, 체크포인트 이어받기, 일일 캐시 재사용, rate_limit 호출 횟수

【2026-08-17】배당수익률 병합(Phase 5-8) 테스트 추가 - 1차(KIS 랭킹 API) → 2차(KRX)
- 처음엔 MockKISClient.get_dividend_rates()로 테스트했으나, 실제 KIS "배당률 상위"
  API가 부적합함이 드러나 ValuationCollector가 KRX 정보데이터시스템(data/krx_data.py)
  기반 dividend_fetcher 콜러블을 생성자에서 주입받는 방식으로 바뀌었다. 그에 맞춰
  MockKISClient에서 배당 관련 코드를 제거하고, 별도의 MockDividendFetcher를
  dividend_fetcher로 주입하는 방식으로 테스트를 다시 작성함.
- TestValuationCollectorDividendMerge: 시장별 1회 호출, 종목코드 매칭, 매칭 실패 시
  None 유지, fetch_dividends=False로 끄면 아예 호출 안 함을 검증

【2026-08-17】배당수익률 병합 3차 - KRX 라이브 API(data/krx_data.py) → CSV 임포터
(data/krx_importer.py)로 교체됨에 따라 test_default_dividend_fetcher_uses_krx_data_module
을 test_default_dividend_fetcher_uses_krx_importer_module로 이름 변경, 모듈
경로만 교체(krx_data.get_dividend_yields → krx_importer.get_dividend_yields).
MockDividendFetcher를 쓰는 나머지 테스트들은 dividend_fetcher가 어떤 실제 구현을
가리키는지와 무관하므로(콜러블 인터페이스만 검증) 변경 없음.
================================================================================
"""

import json
import os
import tempfile
import time

import pytest
from market_intelligence.collectors.valuation_collector import ValuationCollector


class MockKISClient:
    """종목코드별로 미리 정해둔 값을 돌려주는 Mock (일부는 실패하도록 구성 가능)"""

    def __init__(self, responses=None, fail_symbols=None):
        self.responses = responses or {}
        self.fail_symbols = fail_symbols or set()
        self.call_count = 0
        self.called_symbols = []

    def get_stock_fundamental(self, symbol):
        self.call_count += 1
        self.called_symbols.append(symbol)
        if symbol in self.fail_symbols:
            raise RuntimeError("API 오류 시뮬레이션")
        return self.responses.get(symbol, {})


class MockDividendFetcher:
    """ValuationCollector(dividend_fetcher=...)에 주입하는 Mock - market(str)을 받아
    {종목코드: 배당수익률} 딕셔너리를 돌려주는 콜러블(KRX data/krx_data.py 대역)"""

    def __init__(self, responses=None, raise_error=False):
        self.responses = responses or {}  # {"KOSPI": {"005930": 2.15}, ...}
        self.raise_error = raise_error
        self.called_markets = []

    def __call__(self, market):
        self.called_markets.append(market)
        if self.raise_error:
            raise RuntimeError("배당 API 장애 시뮬레이션")
        return self.responses.get(market, {})


def _stock(symbol, name="종목", market="KOSPI"):
    return {"symbol": symbol, "name": name, "market": market}


class TestValuationCollectorBasic:
    def test_collects_all_symbols(self):
        client = MockKISClient(responses={
            "005930": {"per": 15.2, "pbr": 1.4, "dividend_yield": None},
            "000660": {"per": 21.0, "pbr": 2.1, "dividend_yield": None},
        })
        with tempfile.TemporaryDirectory() as cache_dir:
            collector = ValuationCollector(
                kis_client=client, cache_dir=cache_dir, dividend_fetcher=MockDividendFetcher()
            )
            stocks = [_stock("005930"), _stock("000660")]
            records = collector.collect(stocks, rate_limit_sec=0)

            assert len(records) == 2
            per_map = {r["symbol"]: r["per"] for r in records}
            assert per_map["005930"] == 15.2
            assert per_map["000660"] == 21.0
            assert client.call_count == 2

    def test_failed_symbol_does_not_stop_collection(self):
        client = MockKISClient(
            responses={"005930": {"per": 15.2, "pbr": 1.4, "dividend_yield": None}},
            fail_symbols={"999999"},
        )
        with tempfile.TemporaryDirectory() as cache_dir:
            collector = ValuationCollector(
                kis_client=client, cache_dir=cache_dir, dividend_fetcher=MockDividendFetcher()
            )
            stocks = [_stock("999999"), _stock("005930")]
            records = collector.collect(stocks, rate_limit_sec=0)

            assert len(records) == 2  # 실패해도 목록에는 남음(값만 None)
            by_symbol = {r["symbol"]: r for r in records}
            assert by_symbol["999999"]["per"] is None
            assert by_symbol["005930"]["per"] == 15.2

    def test_empty_stock_list_returns_empty(self):
        client = MockKISClient()
        with tempfile.TemporaryDirectory() as cache_dir:
            collector = ValuationCollector(
                kis_client=client, cache_dir=cache_dir, dividend_fetcher=MockDividendFetcher()
            )
            assert collector.collect([], rate_limit_sec=0) == []
            assert client.call_count == 0


class TestValuationCollectorCheckpoint:
    def test_resumes_from_checkpoint_without_refetching(self):
        client = MockKISClient(responses={
            "005930": {"per": 15.2, "pbr": 1.4, "dividend_yield": None},
            "000660": {"per": 21.0, "pbr": 2.1, "dividend_yield": None},
            "005380": {"per": 18.0, "pbr": 1.2, "dividend_yield": None},
        })
        with tempfile.TemporaryDirectory() as cache_dir:
            collector = ValuationCollector(
                kis_client=client, cache_dir=cache_dir, dividend_fetcher=MockDividendFetcher()
            )

            # 체크포인트를 미리 만들어 둠 (005930은 이미 완료된 것처럼)
            checkpoint = {
                "collected": [{"symbol": "005930", "name": "종목", "market": "KOSPI",
                                "per": 15.2, "pbr": 1.4, "dividend_yield": None}],
                "updated_at": "2026-08-15T00:00:00",
            }
            with open(collector._checkpoint_path(), "w", encoding="utf-8") as f:
                json.dump(checkpoint, f)

            stocks = [_stock("005930"), _stock("000660"), _stock("005380")]
            records = collector.collect(stocks, rate_limit_sec=0)

            assert len(records) == 3
            # 005930은 체크포인트에서 왔으므로 API가 재호출되면 안 됨
            assert "005930" not in client.called_symbols
            assert set(client.called_symbols) == {"000660", "005380"}

    def test_get_or_collect_clears_checkpoint_after_success(self):
        client = MockKISClient(responses={"005930": {"per": 15.2, "pbr": 1.4, "dividend_yield": None}})
        with tempfile.TemporaryDirectory() as cache_dir:
            collector = ValuationCollector(
                kis_client=client, cache_dir=cache_dir, dividend_fetcher=MockDividendFetcher()
            )
            collector.get_or_collect([_stock("005930")], force_refresh=True, rate_limit_sec=0)
            assert not os.path.exists(collector._checkpoint_path())


class TestValuationCollectorDailyCache:
    def test_get_or_collect_reuses_same_day_cache(self):
        client = MockKISClient(responses={"005930": {"per": 15.2, "pbr": 1.4, "dividend_yield": None}})
        with tempfile.TemporaryDirectory() as cache_dir:
            collector = ValuationCollector(
                kis_client=client, cache_dir=cache_dir, dividend_fetcher=MockDividendFetcher()
            )
            stocks = [_stock("005930")]

            first = collector.get_or_collect(stocks, rate_limit_sec=0)
            assert client.call_count == 1

            second = collector.get_or_collect(stocks, rate_limit_sec=0)
            assert client.call_count == 1  # 캐시 재사용 - 추가 호출 없음
            assert first == second

    def test_force_refresh_bypasses_cache(self):
        client = MockKISClient(responses={"005930": {"per": 15.2, "pbr": 1.4, "dividend_yield": None}})
        with tempfile.TemporaryDirectory() as cache_dir:
            collector = ValuationCollector(
                kis_client=client, cache_dir=cache_dir, dividend_fetcher=MockDividendFetcher()
            )
            stocks = [_stock("005930")]

            collector.get_or_collect(stocks, rate_limit_sec=0)
            collector.get_or_collect(stocks, force_refresh=True, rate_limit_sec=0)
            assert client.call_count == 2


class TestValuationCollectorRateLimit:
    def test_rate_limit_sleeps_between_calls(self):
        client = MockKISClient(responses={
            "005930": {"per": 15.2, "pbr": 1.4, "dividend_yield": None},
            "000660": {"per": 21.0, "pbr": 2.1, "dividend_yield": None},
        })
        with tempfile.TemporaryDirectory() as cache_dir:
            collector = ValuationCollector(
                kis_client=client, cache_dir=cache_dir, dividend_fetcher=MockDividendFetcher()
            )
            start = time.monotonic()
            collector.collect([_stock("005930"), _stock("000660")], rate_limit_sec=0.05)
            elapsed = time.monotonic() - start
            # 종목 2개, 마지막 종목 뒤에는 안 쉬므로 최소 1회(0.05초)는 대기해야 함
            assert elapsed >= 0.04


class TestValuationCollectorDividendMerge:
    def test_merges_dividend_rate_by_symbol_and_market(self):
        client = MockKISClient(responses={
            "005930": {"per": 15.2, "pbr": 1.4, "dividend_yield": None},
            "247540": {"per": 30.0, "pbr": 3.0, "dividend_yield": None},
        })
        dividend_fetcher = MockDividendFetcher(responses={
            "KOSPI": {"005930": 2.15},
            "KOSDAQ": {"247540": 0.42},
        })
        with tempfile.TemporaryDirectory() as cache_dir:
            collector = ValuationCollector(
                kis_client=client, cache_dir=cache_dir, dividend_fetcher=dividend_fetcher
            )
            records = collector.collect(
                [_stock("005930", market="KOSPI"), _stock("247540", market="KOSDAQ")],
                rate_limit_sec=0,
            )

            by_symbol = {r["symbol"]: r for r in records}
            assert by_symbol["005930"]["dividend_yield"] == 2.15
            assert by_symbol["247540"]["dividend_yield"] == 0.42
            # 시장마다 1회씩만 조회해야 함 (종목 수만큼이 아니라)
            assert sorted(dividend_fetcher.called_markets) == ["KOSDAQ", "KOSPI"]

    def test_unmatched_symbol_stays_none(self):
        client = MockKISClient(responses={
            "005930": {"per": 15.2, "pbr": 1.4, "dividend_yield": None},
        })
        dividend_fetcher = MockDividendFetcher(responses={
            "KOSPI": {"000660": 1.0},  # 005930은 배당 데이터에 없음
        })
        with tempfile.TemporaryDirectory() as cache_dir:
            collector = ValuationCollector(
                kis_client=client, cache_dir=cache_dir, dividend_fetcher=dividend_fetcher
            )
            records = collector.collect([_stock("005930", market="KOSPI")], rate_limit_sec=0)
            assert records[0]["dividend_yield"] is None

    def test_fetch_dividends_false_skips_dividend_call_entirely(self):
        client = MockKISClient(responses={
            "005930": {"per": 15.2, "pbr": 1.4, "dividend_yield": None},
        })
        dividend_fetcher = MockDividendFetcher(responses={"KOSPI": {"005930": 2.15}})
        with tempfile.TemporaryDirectory() as cache_dir:
            collector = ValuationCollector(
                kis_client=client, cache_dir=cache_dir, dividend_fetcher=dividend_fetcher
            )
            records = collector.collect(
                [_stock("005930", market="KOSPI")], rate_limit_sec=0, fetch_dividends=False
            )
            assert records[0]["dividend_yield"] is None
            assert dividend_fetcher.called_markets == []

    def test_dividend_lookup_failure_does_not_break_per_pbr_results(self):
        client = MockKISClient(responses={
            "005930": {"per": 15.2, "pbr": 1.4, "dividend_yield": None},
        })
        dividend_fetcher = MockDividendFetcher(raise_error=True)
        with tempfile.TemporaryDirectory() as cache_dir:
            collector = ValuationCollector(
                kis_client=client, cache_dir=cache_dir, dividend_fetcher=dividend_fetcher
            )
            records = collector.collect([_stock("005930", market="KOSPI")], rate_limit_sec=0)
            # 배당 조회가 통째로 실패해도 PER/PBR 결과는 그대로 남아야 함
            assert records[0]["per"] == 15.2
            assert records[0]["dividend_yield"] is None

    def test_default_dividend_fetcher_uses_krx_importer_module(self):
        # dividend_fetcher를 안 넘기면 data.krx_importer.get_dividend_yields를 쓴다
        # (CSV 임포터 방식으로 교체됨, 2026-08-17) - 실제 파일시스템 접근까지 가지
        # 않고, 지연 임포트가 올바른 모듈/함수를 가리키는지만 확인한다.
        import data.krx_importer as krx_importer

        captured = {}

        def fake_get_dividend_yields(market):
            captured["market"] = market
            return {"005930": 1.23}

        original = krx_importer.get_dividend_yields
        krx_importer.get_dividend_yields = fake_get_dividend_yields
        try:
            client = MockKISClient(responses={
                "005930": {"per": 15.2, "pbr": 1.4, "dividend_yield": None},
            })
            with tempfile.TemporaryDirectory() as cache_dir:
                collector = ValuationCollector(kis_client=client, cache_dir=cache_dir)
                records = collector.collect([_stock("005930", market="KOSPI")], rate_limit_sec=0)
                assert records[0]["dividend_yield"] == 1.23
                assert captured["market"] == "KOSPI"
        finally:
            krx_importer.get_dividend_yields = original
