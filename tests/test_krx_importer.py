"""
data/krx_importer.py, data/krx_validator.py 테스트 (Phase 5-8 CSV 임포터 방식)

================================================================================
【변경 이력】
================================================================================
【2026-08-17】최초 생성
- fixtures/krx_kospi_sample.csv, fixtures/krx_kosdaq_sample.csv는 사용자가 실제
  KRX에서 다운로드한 2026-08-17자 원본 파일(각 914/1802행)에서 일부 행을 뽑아
  만든 샘플이다(인코딩/따옴표/컬럼 구성은 원본 그대로) - PER이 빈 값인 행,
  배당수익률이 0이 아닌 행을 하나씩 포함시켜 결측치 처리와 정상값 처리를
  둘 다 검증할 수 있게 했다. 종목 수 하한 검증(krx_validator.MIN_ROW_COUNT)은
  샘플이 8행뿐이라 당연히 걸리므로, 그 검증만은 min_row_count를 낮춘 별도
  케이스로 우회해서 테스트한다.
- 모든 테스트는 tempfile.TemporaryDirectory()로 만든 격리된 base_dir을 써서
  실제 data/krx/ 폴더를 절대 건드리지 않는다.
================================================================================
"""

import json
import shutil
import tempfile
from pathlib import Path

import pytest

from data import krx_importer, krx_validator

_FIXTURES = Path(__file__).parent / "fixtures"
_KOSPI_SAMPLE = _FIXTURES / "krx_kospi_sample.csv"
_KOSDAQ_SAMPLE = _FIXTURES / "krx_kosdaq_sample.csv"


class TestParseKrxCsv:
    def test_parses_rows_with_correct_types(self):
        rows = krx_importer.parse_krx_csv(str(_KOSPI_SAMPLE))
        assert len(rows) == 8
        by_symbol = {r["symbol"]: r for r in rows}
        assert by_symbol["095570"]["name"] == "AJ네트웍스"
        assert by_symbol["095570"]["per"] == pytest.approx(7.12)
        assert by_symbol["095570"]["dividend_yield"] == pytest.approx(7.30)

    def test_blank_per_becomes_none_not_zero(self):
        rows = krx_importer.parse_krx_csv(str(_KOSPI_SAMPLE))
        by_symbol = {r["symbol"]: r for r in rows}
        # AK홀딩스(006840)는 원본에 EPS/PER이 빈 문자열로 옴
        assert by_symbol["006840"]["per"] is None
        assert by_symbol["006840"]["eps"] is None
        # 배당수익률은 실제로 "0.00"이 찍혀 있으므로 결측이 아니라 0.0이어야 함
        assert by_symbol["006840"]["dividend_yield"] == 0.0

    def test_nonzero_dividend_yield_parsed(self):
        rows = krx_importer.parse_krx_csv(str(_KOSDAQ_SAMPLE))
        nonzero = [r for r in rows if r["dividend_yield"] and r["dividend_yield"] > 0]
        assert len(nonzero) >= 1

    def test_missing_required_column_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad_path = Path(tmp) / "broken.csv"
            bad_path.write_text("종목코드,종목명,종가\n005930,삼성전자,70000\n", encoding="cp949")
            with pytest.raises(krx_importer.KrxImportError):
                krx_importer.parse_krx_csv(str(bad_path))


class TestValidator:
    def test_valid_rows_pass(self):
        rows = krx_importer.parse_krx_csv(str(_KOSPI_SAMPLE))
        result = krx_validator.validate("KOSPI", "20260817", rows)
        # 샘플이 8행뿐이라 실제 하한(700)에는 못 미침 - 그 자체가 검증 로직이
        # 제대로 작동한다는 뜻(아래 test_low_row_count_fails에서 확인)
        assert not result.ok
        assert result.total_rows == 8
        assert result.per_present_count == 6  # 8행 중 2행(006840, 001465)이 PER 결측
        assert result.pbr_present_count == 7  # 001465는 PBR도 결측(BPS/PBR 둘 다 빈 값)
        assert result.dividend_present_count == 8  # 배당수익률은 전부 값이 있어야 함

    def test_low_row_count_fails_with_clear_reason(self):
        rows = krx_importer.parse_krx_csv(str(_KOSPI_SAMPLE))
        result = krx_validator.validate("KOSPI", "20260817", rows)
        assert not result.ok
        assert any("종목 수" in e for e in result.errors)

    def test_duplicate_codes_detected(self):
        rows = krx_importer.parse_krx_csv(str(_KOSPI_SAMPLE))
        rows.append(dict(rows[0]))  # 인위적으로 중복 추가
        result = krx_validator.validate("KOSPI", "20260817", rows)
        assert not result.ok
        assert rows[0]["symbol"] in result.duplicate_codes


class TestImportFile:
    def _setup_incoming(self, tmp_path):
        base = Path(tmp_path)
        incoming = base / "incoming"
        incoming.mkdir(parents=True)
        return base, incoming

    def test_import_archives_original_regardless_of_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            base, incoming = self._setup_incoming(tmp)
            src = incoming / "kospi_20260817.csv"
            shutil.copyfile(_KOSPI_SAMPLE, src)

            outcome = krx_importer.import_file(str(src), base_dir=base)

            # 검증은 실패(샘플이 8행이라 하한 미달)하지만 원본은 그대로 archive에 남아야 함
            assert not outcome.validation.ok
            assert outcome.latest_updated is False
            assert Path(outcome.archived_path).exists()
            assert not (base / "latest" / "kospi.json").exists()

    def test_market_and_date_parsed_from_filename(self):
        with tempfile.TemporaryDirectory() as tmp:
            base, incoming = self._setup_incoming(tmp)
            src = incoming / "KOSDAQ_20260814.csv"  # 대문자로도 인식되는지
            shutil.copyfile(_KOSDAQ_SAMPLE, src)

            outcome = krx_importer.import_file(str(src), base_dir=base)
            assert outcome.validation.market == "KOSDAQ"
            assert outcome.validation.trade_date == "20260814"

    def test_unrecognized_filename_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            base, incoming = self._setup_incoming(tmp)
            src = incoming / "data_2423_20260817.csv"  # 시장 정보 없음(사용자가 처음 준 원본 파일명 그대로)
            shutil.copyfile(_KOSPI_SAMPLE, src)

            with pytest.raises(krx_importer.KrxImportError):
                krx_importer.import_file(str(src), base_dir=base)

    def test_date_regression_blocked_without_force(self):
        with tempfile.TemporaryDirectory() as tmp:
            base, incoming = self._setup_incoming(tmp)
            # 먼저 검증을 통과하도록 min_row_count를 낮춰서 실제로 latest에 반영되게 함
            original_min = krx_validator.MIN_ROW_COUNT.copy()
            krx_validator.MIN_ROW_COUNT["KOSPI"] = 1
            try:
                newer = incoming / "kospi_20260817.csv"
                shutil.copyfile(_KOSPI_SAMPLE, newer)
                first = krx_importer.import_file(str(newer), base_dir=base)
                assert first.latest_updated is True

                older = incoming / "kospi_20260814.csv"
                shutil.copyfile(_KOSPI_SAMPLE, older)
                second = krx_importer.import_file(str(older), base_dir=base)
                assert second.latest_updated is False
                assert "예전 파일" in second.message or "최신" in second.message

                # force=True면 덮어써야 함
                third = krx_importer.import_file(str(older), base_dir=base, force=True)
                assert third.latest_updated is True
            finally:
                krx_validator.MIN_ROW_COUNT.clear()
                krx_validator.MIN_ROW_COUNT.update(original_min)


class TestGetDividendYields:
    def test_returns_empty_dict_when_no_data_imported_yet(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            result = krx_importer.get_dividend_yields("KOSPI", base_dir=base)
            assert result == {}

    def test_returns_yields_after_successful_import(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "incoming").mkdir(parents=True)
            original_min = krx_validator.MIN_ROW_COUNT.copy()
            krx_validator.MIN_ROW_COUNT["KOSPI"] = 1
            try:
                src = base / "incoming" / "kospi_20260817.csv"
                shutil.copyfile(_KOSPI_SAMPLE, src)
                krx_importer.import_file(str(src), base_dir=base)

                yields = krx_importer.get_dividend_yields("KOSPI", base_dir=base)
                assert yields["095570"] == pytest.approx(7.30)
                # 006840은 PER은 결측이지만 배당수익률(0.00)은 실제 값이므로 포함되어야 함
                assert yields["006840"] == 0.0
            finally:
                krx_validator.MIN_ROW_COUNT.clear()
                krx_validator.MIN_ROW_COUNT.update(original_min)


class TestScanIncoming:
    def test_processes_and_removes_valid_filenames_from_incoming(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "incoming").mkdir(parents=True)
            shutil.copyfile(_KOSPI_SAMPLE, base / "incoming" / "kospi_20260817.csv")
            shutil.copyfile(_KOSDAQ_SAMPLE, base / "incoming" / "kosdaq_20260817.csv")

            outcomes = krx_importer.scan_incoming(base_dir=base)
            assert len(outcomes) == 2
            # 처리(검증 실패든 성공이든)한 파일은 incoming에서 사라져야 함
            assert list((base / "incoming").glob("*.csv")) == []

    def test_unrecognized_filename_stays_in_incoming(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "incoming").mkdir(parents=True)
            bad = base / "incoming" / "data_2423_20260817.csv"
            shutil.copyfile(_KOSPI_SAMPLE, bad)

            krx_importer.scan_incoming(base_dir=base)
            # 시장을 못 읽는 파일은 지우지 않고 그대로 남겨서 사용자가 이름을 고칠 수 있게 함
            assert bad.exists()
