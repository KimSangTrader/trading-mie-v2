"""
StockMaster 테스트 (Phase 5-2: KOSPI/KOSDAQ 전체 종목코드 마스터)

================================================================================
【변경 이력】
================================================================================
【2026-08-15】최초 생성
- parse_mst_line()은 순수 문자열 파싱이라 네트워크 없이 직접 검증
- StockMaster.get_stock_list()는 파일 캐시를 직접 만들어두고 force_refresh=False로
  호출해 네트워크 호출 없이 캐시 경로를 검증 (실제 다운로드는 이 세션에서 검증 불가 -
  사용자 컴퓨터에서 __main__ 실행으로 별도 확인 필요)
================================================================================
"""

import json
import os
import tempfile
from datetime import date

import pytest
from data.stock_master import StockMaster, parse_mst_line, KOSPI, KOSDAQ


def _make_mst_line(symbol: str, name: str, group_code: str, market: str) -> str:
    """테스트용 마스터파일 한 줄 생성 (KIS 공식 필드 폭에 맞춤)

    2026-08-16 실제 파일로 검증한 실측 레이아웃 반영: 그룹코드는 part2[0:2]가
    아니라 part2[1:3]에 있다 (앞에 1자리 필드가 있음, 삼성전자 실제 라인:
    part2 앞부분 = ' ST1002700130000 NN5YYY YYNNNN').
    """
    part2_width = 228 if market == KOSPI else 222
    part1 = symbol.ljust(9) + "KR7000000000".ljust(12) + name
    part2 = " " + group_code.ljust(2) + " " * (part2_width - 3)
    return part1 + part2


class TestParseMstLine:
    def test_valid_kospi_line(self):
        line = _make_mst_line("005930", "삼성전자", "ST", KOSPI)
        record = parse_mst_line(line, KOSPI)

        assert record == {
            "symbol": "005930",
            "name": "삼성전자",
            "market": KOSPI,
            "group_code": "ST",
        }

    def test_valid_kosdaq_line(self):
        line = _make_mst_line("247540", "에코프로비엠", "ST", KOSDAQ)
        record = parse_mst_line(line, KOSDAQ)

        assert record["symbol"] == "247540"
        assert record["name"] == "에코프로비엠"
        assert record["market"] == KOSDAQ

    def test_non_common_stock_group_code_still_parsed(self):
        # SPAC 등 비-보통주도 파싱 자체는 되어야 함 (필터링은 상위 레벨 책임)
        line = _make_mst_line("123456", "테스트스팩", "SC", KOSPI)
        record = parse_mst_line(line, KOSPI)
        assert record["group_code"] == "SC"

    def test_too_short_line_returns_none(self):
        assert parse_mst_line("short line", KOSPI) is None

    def test_empty_line_returns_none(self):
        assert parse_mst_line("", KOSPI) is None

    def test_unknown_market_raises(self):
        with pytest.raises(ValueError):
            parse_mst_line("x" * 300, "NYSE")


class TestStockMasterCaching:
    def test_get_stock_list_uses_cache_without_network(self):
        with tempfile.TemporaryDirectory() as cache_dir:
            today = date.today().isoformat()
            cached_records = [
                {"symbol": "005930", "name": "삼성전자", "market": KOSPI, "group_code": "ST"},
                {"symbol": "000660", "name": "SK하이닉스", "market": KOSPI, "group_code": "ST"},
            ]
            with open(os.path.join(cache_dir, f"kospi_{today}.json"), "w", encoding="utf-8") as f:
                json.dump(cached_records, f)
            with open(os.path.join(cache_dir, f"kosdaq_{today}.json"), "w", encoding="utf-8") as f:
                json.dump([], f)

            master = StockMaster(cache_dir=cache_dir)
            # force_refresh=False + 캐시 존재 → _download_and_parse가 호출되면 안 됨
            master._download_and_parse = lambda market: (_ for _ in ()).throw(
                AssertionError("캐시가 있는데 네트워크 다운로드를 시도함")
            )

            result = master.get_stock_list(market="ALL", common_stock_only=False)
            assert len(result) == 2
            assert result[0]["symbol"] == "005930"

    def test_common_stock_only_filters_non_st(self):
        with tempfile.TemporaryDirectory() as cache_dir:
            today = date.today().isoformat()
            cached_records = [
                {"symbol": "005930", "name": "삼성전자", "market": KOSPI, "group_code": "ST"},
                {"symbol": "123456", "name": "테스트스팩", "market": KOSPI, "group_code": "SC"},
            ]
            with open(os.path.join(cache_dir, f"kospi_{today}.json"), "w", encoding="utf-8") as f:
                json.dump(cached_records, f)
            with open(os.path.join(cache_dir, f"kosdaq_{today}.json"), "w", encoding="utf-8") as f:
                json.dump([], f)

            master = StockMaster(cache_dir=cache_dir)
            master._download_and_parse = lambda market: (_ for _ in ()).throw(
                AssertionError("캐시가 있는데 네트워크 다운로드를 시도함")
            )

            result = master.get_stock_list(market="ALL", common_stock_only=True)
            assert len(result) == 1
            assert result[0]["symbol"] == "005930"


class TestStockMasterSelfValidation:
    def test_too_few_records_raises(self):
        # 파싱 결과가 비정상적으로 적으면(형식이 바뀌었을 가능성) 명시적으로 예외
        import data.stock_master as sm_module

        with tempfile.TemporaryDirectory() as tmp_dir:
            mst_path = os.path.join(tmp_dir, "tiny.mst")
            with open(mst_path, "w", encoding="cp949") as f:
                f.write(_make_mst_line("005930", "삼성전자", "ST", KOSPI) + "\n")

            with pytest.raises(RuntimeError):
                sm_module.StockMaster._parse_mst_file(mst_path, KOSPI)
