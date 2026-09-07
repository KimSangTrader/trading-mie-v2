"""
ThemeAnalyzer 테스트 (Phase 5-14: 실계산 전환)

================================================================================
【변경 이력】
================================================================================
【2026-08-23】최초 생성
- tests/test_sector_analyzer.py와 동일한 패턴. ThemeAnalyzer 고유 부분(다대다
  매핑, get_stock_theme_score의 Primary/Secondary 가중치·재정규화)을 집중 검증.
================================================================================
"""

import pytest

from market_intelligence.analyzers.theme_analyzer import ThemeAnalyzer


def _basket_rows(ticker, market, daily_pct_change, days=65, start_price=10000):
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


class TestThemeAnalyzerValidation:
    def test_validate_requires_price_history_and_mapping(self):
        analyzer = ThemeAnalyzer()
        assert analyzer.validate({"price_history": [1], "theme_mapping": [1]}) is True
        assert analyzer.validate({"price_history": [1]}) is False
        assert analyzer.validate({}) is False


class TestThemeAnalyzerAnalyze:
    def test_strong_theme_outscores_weak_theme(self):
        price_history = (
            _basket_rows("005930", "KOSPI", 0.6)
            + _basket_rows("000660", "KOSPI", 0.5)
            + _basket_rows("373220", "KOSPI", -0.4)
        )
        theme_mapping = [
            {"ticker": "005930", "theme": "AI", "is_primary": True},
            {"ticker": "000660", "theme": "AI", "is_primary": True},
            {"ticker": "373220", "theme": "Secondary_Battery", "is_primary": True},
        ]
        analyzer = ThemeAnalyzer()
        result = analyzer.run({"price_history": price_history, "theme_mapping": theme_mapping})

        scores = result["details"]["theme_scores"]
        assert scores["AI"] > scores["Secondary_Battery"]

    def test_ticker_counted_once_even_if_tagged_primary_and_secondary_rows(self):
        # 방어적 테스트: 같은 (ticker, theme) 조합이 실수로 두 번 들어와도 바스켓
        # 멤버 수가 중복 카운트되면 안 됨
        price_history = _basket_rows("005930", "KOSPI", 0.3)
        theme_mapping = [
            {"ticker": "005930", "theme": "AI", "is_primary": True},
            {"ticker": "005930", "theme": "AI", "is_primary": False},  # 중복(비정상 입력 가정)
        ]
        analyzer = ThemeAnalyzer()
        result = analyzer.run({"price_history": price_history, "theme_mapping": theme_mapping})
        assert result["details"]["theme_details"]["AI"]["member_count"] == 1

    def test_excluded_tickers_removed_from_basket(self):
        price_history = _basket_rows("005930", "KOSPI", 0.3) + _basket_rows("000660", "KOSPI", 0.3)
        theme_mapping = [
            {"ticker": "005930", "theme": "AI", "is_primary": True},
            {"ticker": "000660", "theme": "AI", "is_primary": True},
        ]
        analyzer = ThemeAnalyzer()
        result = analyzer.run({
            "price_history": price_history, "theme_mapping": theme_mapping,
            "excluded_tickers": ["000660"],
        })
        assert result["details"]["theme_details"]["AI"]["member_count"] == 1


class TestGetStockThemeScore:
    def test_primary_and_two_secondary_weighted_as_documented(self):
        analysis_result = {"theme_scores": {"Secondary_Battery": 40.0, "EV": 80.0, "Renewable_Energy": 70.0}}
        score = ThemeAnalyzer.get_stock_theme_score(
            analysis_result, primary_theme="Secondary_Battery",
            secondary_themes=["EV", "Renewable_Energy"],
        )
        # 문서 7절 예시와 동일: 40*0.7 + 80*0.2 + 70*0.1 = 28+16+7 = 51
        assert score == pytest.approx(51.0)

    def test_primary_only_returns_primary_score(self):
        analysis_result = {"theme_scores": {"AI": 90.0}}
        score = ThemeAnalyzer.get_stock_theme_score(analysis_result, primary_theme="AI", secondary_themes=[])
        assert score == pytest.approx(90.0)

    def test_missing_primary_score_renormalizes_over_available_secondaries(self):
        # Primary 테마 점수가 결측이면(예: 그 테마 자체가 바스켓 계산 대상이 아니었음)
        # 남은 Secondary만으로 재정규화해야 함 (ValuationAnalyzer와 동일 원칙)
        analysis_result = {"theme_scores": {"EV": 80.0}}  # Primary("Secondary_Battery")는 없음
        score = ThemeAnalyzer.get_stock_theme_score(
            analysis_result, primary_theme="Secondary_Battery", secondary_themes=["EV"],
        )
        assert score == pytest.approx(80.0)

    def test_no_themes_at_all_returns_none(self):
        analysis_result = {"theme_scores": {}}
        assert ThemeAnalyzer.get_stock_theme_score(analysis_result, primary_theme=None, secondary_themes=None) is None

    def test_more_than_two_secondary_themes_ignores_extras(self):
        analysis_result = {"theme_scores": {"A": 100.0, "B": 0.0, "C": 0.0, "D": 100.0}}
        score = ThemeAnalyzer.get_stock_theme_score(
            analysis_result, primary_theme="A", secondary_themes=["B", "C", "D"],
        )
        # D는 무시되고 B/C만 반영: 100*0.7 + 0*0.2 + 0*0.1 = 70
        assert score == pytest.approx(70.0)
