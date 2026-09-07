"""
ThemeAnalyzer - 테마(Theme) 분석기

================================================================================
【변경 이력】
================================================================================
【~2026-08 이전】최초 버전
- 하드코딩된 6개 추상적 "시장 심리" 테마(geopolitical_risk, ai_semiconductor 등)와
  고정 base/bull/bear 점수로 동작하는 완전 mock 버전. 실제 종목이 어떤 테마에
  속하는지는 전혀 반영하지 않았다.

【2026-08-23】Phase 5-14: 실계산으로 전면 교체 (docs/hierarchical_scoring_plan.md Phase 2)
- 배경: sector_analy_method.txt(방법론 문서)가 제안한 대로, 이제 실제 존재하는
  종목별 Theme 태그(stock_theme_mapping, 18종, Primary+Secondary 다대다)와
  일봉 데이터(stock_price_history)로 Theme별 점수를 계산한다.
- SectorAnalyzer와 마찬가지로 Theme 카테고리를 코드에 하드코딩하지 않는다 -
  theme_mapping 입력에 실제로 존재하는 테마만 계산 대상이 된다.
- 이전 6개 "시장 심리" 테마와 실제 18개 종목 태그형 테마는 성격이 완전히 다르다
  (sector_theme_importer.py 변경이력에서 이미 지적된 부분) - 하위 호환 없음.
- Sector와 다른 점: 종목 1개가 여러 Theme에 속할 수 있다(Primary 1개 +
  Secondary 0~N개). 각 Theme "바스켓 점수"(예: AI Theme 자체가 몇 점인가)는
  그 Theme에 속한 모든 종목(Primary든 Secondary든 상관없이)을 바스켓으로 써서
  SectorAnalyzer와 동일한 계산(market_intelligence/price_series.py)을 한다.
  반면 종목 1개의 "이 종목의 Theme 점수"는 별도로 get_stock_theme_score()가
  방법론 문서 7절 공식(Primary×0.70+Secondary1×0.20+Secondary2×0.10)으로 계산한다 -
  이 두 가지를 혼동하면 안 된다.
- stock_theme_mapping 테이블에는 needs_review 컬럼이 없다(그 플래그는
  stock_sector_mapping에만 있음 - 같은 원본 엑셀 행에서 나왔지만 두 테이블이
  분리되어 있어서). 검토 대상 종목을 Theme 계산에서도 빼고 싶으면 호출부가
  data["excluded_tickers"]로 넘겨야 한다(기본값: 아무도 제외하지 않음).
================================================================================
"""

from typing import Any, Dict, List, Optional
import logging

from market_intelligence.base_analyzer import BaseAnalyzer
from market_intelligence.price_series import (
    compute_market_returns,
    compute_ticker_metrics,
    group_price_rows_by_ticker,
    score_basket,
)

logger = logging.getLogger(__name__)


class ThemeAnalyzer(BaseAnalyzer):
    """테마(Theme) 분석기 - 종목 바스켓(같은 Theme에 속한 종목들)의 실제 가격/거래
    데이터로 Theme별 점수(0~100)를 계산한다. SectorAnalyzer와 동일하게 순수
    계산기다(API/DB 직접 호출 없음).
    """

    def __init__(self):
        super().__init__(name="theme", weight=0.14)
        logger.info(f"✅ ThemeAnalyzer 초기화 완료 (실계산 모드, weight={self.weight})")

    def validate(self, data: Dict[str, Any]) -> bool:
        """
        필수 입력:
        - price_history: SectorAnalyzer와 동일 형식
        - theme_mapping: [{"ticker":, "theme":, "is_primary":}, ...]
          (data/sector_theme_importer.py의 get_latest_theme_mapping() 반환 형식)
        - market_returns / excluded_tickers (선택)
        """
        if not isinstance(data, dict):
            return False
        return bool(data.get("price_history")) and bool(data.get("theme_mapping"))

    def analyze(self, data: Dict[str, Any]) -> Dict[str, Any]:
        price_history = data["price_history"]
        theme_mapping = data["theme_mapping"]
        explicit_market_returns = data.get("market_returns") or {}
        excluded_tickers = set(data.get("excluded_tickers") or ())

        ticker_rows = group_price_rows_by_ticker(price_history)
        ticker_metrics = {}
        for ticker, rows in ticker_rows.items():
            metrics = compute_ticker_metrics(rows)
            if metrics is not None:
                ticker_metrics[ticker] = metrics

        ticker_market: Dict[str, str] = {}
        for row in price_history:
            ticker = row.get("ticker")
            if ticker and row.get("market"):
                ticker_market[ticker] = row["market"]

        market_returns = compute_market_returns(ticker_metrics, ticker_market)
        for market, values in explicit_market_returns.items():
            market_returns.setdefault(market, {}).update(values)

        theme_members: Dict[str, List[str]] = {}
        for row in theme_mapping:
            ticker = row.get("ticker")
            theme = row.get("theme")
            if not ticker or not theme or ticker in excluded_tickers:
                continue
            members = theme_members.setdefault(theme, [])
            if ticker not in members:  # Primary/Secondary 중복 태깅 방지
                members.append(ticker)

        theme_scores: Dict[str, float] = {}
        theme_details: Dict[str, Dict[str, Any]] = {}
        for theme, tickers in theme_members.items():
            result = score_basket(tickers, ticker_metrics, ticker_market, market_returns)
            theme_scores[theme] = result["score"]
            theme_details[theme] = result

        if not theme_scores:
            logger.warning("⚠️  집계 가능한 Theme가 없습니다 (theme_mapping이 비어 있음)")
            return {
                "theme_scores": {}, "theme_details": {}, "average_score": 50.0,
                "theme_count": 0, "market_returns": market_returns,
            }

        strongest = max(theme_scores.items(), key=lambda x: x[1])
        weakest = min(theme_scores.items(), key=lambda x: x[1])
        average_score = sum(theme_scores.values()) / len(theme_scores)

        logger.info(
            f"Theme Analysis: {len(theme_scores)}개 Theme, "
            f"Strongest={strongest[0]}({strongest[1]:.1f}), Weakest={weakest[0]}({weakest[1]:.1f}), "
            f"Average={average_score:.1f}"
        )

        return {
            "theme_scores": theme_scores,
            "theme_details": theme_details,
            "strongest_theme": {"name": strongest[0], "score": strongest[1]},
            "weakest_theme": {"name": weakest[0], "score": weakest[1]},
            "average_score": average_score,
            "theme_count": len(theme_scores),
            "market_returns": market_returns,
        }

    def get_score(self, analysis_result: Dict[str, Any]) -> float:
        """전체 Theme 평균 점수 (0~100) - "시장 전반 Theme 강도" 게이지.

        계층형 결합기(Phase 4)에서 개별 종목에 쓸 Theme 점수는 이 값이 아니라
        get_stock_theme_score()로 그 종목의 Primary/Secondary Theme 조합 점수를
        따로 계산해야 한다.
        """
        score = analysis_result.get("average_score", 50.0)
        return max(0.0, min(100.0, score))

    @staticmethod
    def get_stock_theme_score(
        analysis_result: Dict[str, Any],
        primary_theme: Optional[str],
        secondary_themes: Optional[List[str]] = None,
    ) -> Optional[float]:
        """종목 하나의 Theme 점수 (방법론 문서 7절):
        Primary×0.70 + Secondary1×0.20 + Secondary2×0.10

        Secondary가 2개 미만이거나 일부 Theme 점수가 결측이면, 계산 가능한
        항목만으로 가중치를 재정규화한다(ValuationAnalyzer와 동일 원칙) -
        Primary만 있으면 그냥 Primary 점수를 그대로 반환한다.
        Primary/Secondary가 모두 없거나 전부 결측이면 None.
        """
        theme_scores = analysis_result.get("theme_scores", {})
        secondary_themes = (secondary_themes or [])[:2]  # 문서 예시가 최대 2개까지만 다룸

        weighted = [(primary_theme, 0.70)] + list(zip(secondary_themes, (0.20, 0.10)))
        available = [
            (theme_scores[t], w) for t, w in weighted if t and theme_scores.get(t) is not None
        ]
        if not available:
            return None

        total_weight = sum(w for _, w in available)
        return sum(score * w for score, w in available) / total_weight


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    def _mock_rows(ticker, market, start_price, daily_pct_change):
        rows = []
        price = start_price
        for day in range(60):
            rows.append({
                "ticker": ticker, "market": market,
                "trade_date": f"2026{(day // 28) + 6:02d}{(day % 28) + 1:02d}",
                "close": price, "volume": 100000 + day * 1000,
            })
            price *= (1 + daily_pct_change / 100)
        return rows

    price_history = (
        _mock_rows("005930", "KOSPI", 70000, 0.6)
        + _mock_rows("000660", "KOSPI", 200000, 0.5)
        + _mock_rows("373220", "KOSPI", 400000, -0.3)
    )
    theme_mapping = [
        {"ticker": "005930", "theme": "AI", "is_primary": True},
        {"ticker": "005930", "theme": "Semiconductor", "is_primary": False},
        {"ticker": "000660", "theme": "AI", "is_primary": True},
        {"ticker": "373220", "theme": "Secondary_Battery", "is_primary": True},
    ]

    analyzer = ThemeAnalyzer()
    result = analyzer.run({"price_history": price_history, "theme_mapping": theme_mapping})

    print("=" * 80)
    print("【ThemeAnalyzer 실계산 테스트】")
    print("=" * 80)
    print(f"전체 평균 점수: {result['score']:.1f}/100")
    for theme, score in result["details"]["theme_scores"].items():
        print(f"  {theme}: {score:.1f}")

    stock_score = analyzer.get_stock_theme_score(result["details"], "AI", ["Semiconductor"])
    print(f"\n삼성전자(Primary=AI, Secondary=[Semiconductor]) Theme 점수: {stock_score:.1f}")
