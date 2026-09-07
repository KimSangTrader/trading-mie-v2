"""
SectorAnalyzer 테스트 (Phase 5-14: 실계산 전환)

================================================================================
【변경 이력】
================================================================================
【2026-08-23】최초 생성
- 기존 tests/test_analyzers.py::TestSectorAnalyzer는 name/weight만 확인하는
  최소 테스트라 그대로 두고, 이 파일에서 새 입력 계약(price_history +
  sector_mapping)과 실계산 동작을 검증한다.
================================================================================
"""

import pytest

from market_intelligence.analyzers.sector_analyzer import SectorAnalyzer


def _basket_rows(ticker, market, daily_pct_change, days=65, start_price=10000):
    """일정한 일간 등락률로 days일치 가격을 만든다(과거->최신)."""
    rows = []
    price = start_price
    for day in range(days):
        rows.append({
            "ticker": ticker, "market": market,
            "trade_date": f"20260{ (day // 28) % 9 + 1 }{ (day % 28) + 1:02d}",
            "close": round(price, 2), "volume": 10000,
        })
        price *= (1 + daily_pct_change / 100)
    return rows


class TestSectorAnalyzerValidation:
    def test_validate_requires_price_history_and_mapping(self):
        analyzer = SectorAnalyzer()
        assert analyzer.validate({"price_history": [1], "sector_mapping": [1]}) is True
        assert analyzer.validate({"price_history": [1]}) is False
        assert analyzer.validate({"sector_mapping": [1]}) is False
        assert analyzer.validate({}) is False
        assert analyzer.validate("not a dict") is False


class TestSectorAnalyzerAnalyze:
    def test_strong_sector_outscores_weak_sector(self):
        price_history = (
            _basket_rows("005930", "KOSPI", 0.5)
            + _basket_rows("000660", "KOSPI", 0.4)
            + _basket_rows("035420", "KOSPI", -0.3)
            + _basket_rows("068270", "KOSPI", -0.2)
        )
        sector_mapping = [
            {"ticker": "005930", "sector": "IT_Semiconductor", "market": "KOSPI", "needs_review": False},
            {"ticker": "000660", "sector": "IT_Semiconductor", "market": "KOSPI", "needs_review": False},
            {"ticker": "035420", "sector": "Consumer", "market": "KOSPI", "needs_review": False},
            {"ticker": "068270", "sector": "Consumer", "market": "KOSPI", "needs_review": False},
        ]

        analyzer = SectorAnalyzer()
        result = analyzer.run({"price_history": price_history, "sector_mapping": sector_mapping})

        scores = result["details"]["sector_scores"]
        assert set(scores.keys()) == {"IT_Semiconductor", "Consumer"}
        assert scores["IT_Semiconductor"] > scores["Consumer"]
        assert 0 <= result["score"] <= 100

    def test_needs_review_excluded_by_default(self):
        price_history = _basket_rows("999999", "KOSPI", 0.1)
        sector_mapping = [
            {"ticker": "999999", "sector": "Other", "market": "KOSPI", "needs_review": True},
        ]
        analyzer = SectorAnalyzer()
        result = analyzer.run({"price_history": price_history, "sector_mapping": sector_mapping})
        assert result["details"]["sector_scores"] == {}
        assert result["details"]["excluded_needs_review"] == 1

    def test_needs_review_included_when_opted_in(self):
        price_history = _basket_rows("999999", "KOSPI", 0.1)
        sector_mapping = [
            {"ticker": "999999", "sector": "Other", "market": "KOSPI", "needs_review": True},
        ]
        analyzer = SectorAnalyzer(include_needs_review=True)
        result = analyzer.run({"price_history": price_history, "sector_mapping": sector_mapping})
        assert "Other" in result["details"]["sector_scores"]

    def test_sector_with_no_matching_price_data_falls_back_to_neutral(self):
        # sector_mapping의 005930은 price_history에 없고(다른 종목만 있음),
        # 그 Sector는 데이터가 하나도 없으므로 중립(50점) 처리되어야 함
        price_history = _basket_rows("000660", "KOSPI", 0.5)  # 005930과 무관한 종목
        sector_mapping = [{"ticker": "005930", "sector": "IT_Semiconductor", "market": "KOSPI",
                            "needs_review": False}]
        analyzer = SectorAnalyzer()
        result = analyzer.run({"price_history": price_history, "sector_mapping": sector_mapping})
        assert result["success"] is True
        assert result["details"]["sector_scores"]["IT_Semiconductor"] == 50.0
        assert result["details"]["sector_details"]["IT_Semiconductor"]["data_quality"] == 0.0

    def test_empty_price_history_fails_validation(self):
        sector_mapping = [{"ticker": "005930", "sector": "IT_Semiconductor", "market": "KOSPI",
                            "needs_review": False}]
        analyzer = SectorAnalyzer()
        result = analyzer.run({"price_history": [], "sector_mapping": sector_mapping})
        assert result["success"] is False


class TestSectorAnalyzerStockLookup:
    def test_get_stock_sector_score_looks_up_own_sector(self):
        price_history = _basket_rows("005930", "KOSPI", 0.5) + _basket_rows("035420", "KOSPI", -0.3)
        sector_mapping = [
            {"ticker": "005930", "sector": "IT_Semiconductor", "market": "KOSPI", "needs_review": False},
            {"ticker": "035420", "sector": "Consumer", "market": "KOSPI", "needs_review": False},
        ]
        analyzer = SectorAnalyzer()
        result = analyzer.run({"price_history": price_history, "sector_mapping": sector_mapping})
        details = result["details"]

        assert SectorAnalyzer.get_stock_sector_score(details, "IT_Semiconductor") == pytest.approx(
            details["sector_scores"]["IT_Semiconductor"]
        )
        assert SectorAnalyzer.get_stock_sector_score(details, "NonexistentSector") is None
        assert SectorAnalyzer.get_stock_sector_score(details, None) is None
