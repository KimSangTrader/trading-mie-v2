"""
SectorAnalyzer - 업종(Sector) 분석기

================================================================================
【변경 이력】
================================================================================
【~2026-08 이전】최초 버전
- 하드코딩된 8개 Sector(IT_Semiconductor, Finance, ... Secondary_Battery)와
  고정 bull/bear 지수 기준값으로 동작하는 완전 mock 버전. 실제 종목 데이터를
  전혀 쓰지 않았다(data/sector_theme_importer.py 변경이력에서 이미 지적됨).

【2026-08-23】Phase 5-14: 실계산으로 전면 교체 (docs/hierarchical_scoring_plan.md Phase 2)
- 배경: sector_analy_method.txt(방법론 문서)가 제안한 Sector 점수 공식
  (모멘텀30+상대강도25+상승확산도20+거래대금15+추세안정성10=100점)을, 이제 실제로
  존재하는 데이터(stock_price_history의 종목별 일봉, stock_sector_mapping의
  종목→Sector 실제 매핑, 12종)로 계산하도록 완전히 교체했다.
- 하드코딩된 8개 Sector 딕셔너리를 제거했다. sector_theme_importer.py가 임포트한
  실제 Sector 카테고리는 12종(IT_Semiconductor, Healthcare_Pharma, Telecom_Media,
  Industrials, Finance, Chemicals_Energy, Consumer, Construction_Real_Estate,
  Materials, Utilities, Transportation, Other)이지만, 이 값 자체를 코드에
  하드코딩하지 않고 sector_mapping 입력에 실제로 존재하는 값을 그대로 쓴다 -
  Excel이 나중에 또 바뀌어도(카테고리 추가/이름 변경) 이 analyzer는 자동으로
  따라간다(이전 버전이 "하드코딩된 8개가 실제 12개와 안 맞다"는 문제로
  지적받았던 것을 반복하지 않기 위함).
- 데이터 검증(validate)/입력 계약이 완전히 바뀌었다: 예전엔 하드코딩된 8개
  Sector 키를 가진 dict였지만, 이제는 {"price_history": [...], "sector_mapping":
  [...]} 형태다 - 하위 호환은 없다(전면 교체를 사용자가 명시적으로 승인함,
  docs/hierarchical_scoring_plan.md 결정 사항 참고).
- needs_review=True로 표시된(검토 필요) 매핑 행은 기본적으로 점수 계산에서
  제외한다(sector_theme_importer.py 변경이력이 "소비하는 쪽이 정책을 정하라"고
  남겨둔 부분 - 불확실한 분류가 Sector 점수를 왜곡하지 않도록 보수적으로 선택).
  include_needs_review=True로 생성하면 포함시킬 수 있다.
- 실제 계산 로직(수익률/상대강도/확산도/거래대금/추세 스케일링)은
  market_intelligence/price_series.py로 분리했다 - ThemeAnalyzer도 동일 바스켓
  스코어링 로직이 필요해서 중복을 피하기 위함.
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


class SectorAnalyzer(BaseAnalyzer):
    """업종(Sector) 분석기 - 종목 바스켓(같은 Sector에 속한 종목들)의 실제 가격/거래
    데이터로 Sector별 점수(0~100)를 계산한다. API/DB를 직접 호출하지 않는 순수
    계산기다 - 필요한 데이터(stock_price_history, stock_sector_mapping 최신 배치)는
    호출부가 준비해서 넘긴다(ValuationAnalyzer와 동일한 역할 분리 원칙).
    """

    def __init__(self, include_needs_review: bool = False):
        super().__init__(name="sector", weight=0.18)
        self.include_needs_review = include_needs_review
        logger.info(
            f"✅ SectorAnalyzer 초기화 완료 (실계산 모드, weight={self.weight}, "
            f"include_needs_review={include_needs_review})"
        )

    def validate(self, data: Dict[str, Any]) -> bool:
        """
        필수 입력:
        - price_history: [{"ticker":, "market":, "trade_date":"YYYYMMDD", "close":, "volume":}, ...]
        - sector_mapping: [{"ticker":, "sector":, "market":, "needs_review":}, ...]
          (data/sector_theme_importer.py의 get_latest_sector_mapping() 반환 형식)
        - market_returns (선택): {"KOSPI": {"return_20d": ...}, "KOSDAQ": {...}} -
          없으면 price_history 자체로 시장 대표 수익률을 근사 계산한다.
        """
        if not isinstance(data, dict):
            return False
        return bool(data.get("price_history")) and bool(data.get("sector_mapping"))

    def analyze(self, data: Dict[str, Any]) -> Dict[str, Any]:
        price_history = data["price_history"]
        sector_mapping = data["sector_mapping"]
        explicit_market_returns = data.get("market_returns") or {}

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
        for row in sector_mapping:  # price_history에 시장 정보가 없는 종목을 보강
            ticker = row.get("ticker")
            if ticker and ticker not in ticker_market and row.get("market"):
                ticker_market[ticker] = row["market"]

        market_returns = compute_market_returns(ticker_metrics, ticker_market)
        for market, values in explicit_market_returns.items():
            market_returns.setdefault(market, {}).update(values)

        sector_members: Dict[str, List[str]] = {}
        excluded_needs_review = 0
        for row in sector_mapping:
            ticker = row.get("ticker")
            sector = row.get("sector")
            if not ticker or not sector:
                continue
            if row.get("needs_review") and not self.include_needs_review:
                excluded_needs_review += 1
                continue
            sector_members.setdefault(sector, []).append(ticker)

        sector_scores: Dict[str, float] = {}
        sector_details: Dict[str, Dict[str, Any]] = {}
        for sector, tickers in sector_members.items():
            result = score_basket(tickers, ticker_metrics, ticker_market, market_returns)
            sector_scores[sector] = result["score"]
            sector_details[sector] = result

        if not sector_scores:
            logger.warning("⚠️  집계 가능한 Sector가 없습니다 (sector_mapping이 비었거나 전부 검토대상)")
            return {
                "sector_scores": {}, "sector_details": {}, "average_score": 50.0,
                "sector_count": 0, "market_returns": market_returns,
                "excluded_needs_review": excluded_needs_review,
            }

        strongest = max(sector_scores.items(), key=lambda x: x[1])
        weakest = min(sector_scores.items(), key=lambda x: x[1])
        average_score = sum(sector_scores.values()) / len(sector_scores)

        logger.info(
            f"Sector Analysis: {len(sector_scores)}개 Sector, "
            f"Strongest={strongest[0]}({strongest[1]:.1f}), Weakest={weakest[0]}({weakest[1]:.1f}), "
            f"Average={average_score:.1f}"
        )

        return {
            "sector_scores": sector_scores,
            "sector_details": sector_details,
            "strongest_sector": {"name": strongest[0], "score": strongest[1]},
            "weakest_sector": {"name": weakest[0], "score": weakest[1]},
            "average_score": average_score,
            "sector_count": len(sector_scores),
            "market_returns": market_returns,
            "excluded_needs_review": excluded_needs_review,
        }

    def get_score(self, analysis_result: Dict[str, Any]) -> float:
        """전체 Sector 평균 점수 (0~100) - "시장 전반 Sector 강도" 게이지.

        계층형 결합기(Phase 4)에서 개별 종목에 쓸 Sector 점수는 이 값이 아니라
        get_stock_sector_score()로 그 종목이 속한 Sector 하나의 점수를 찾아 써야 한다.
        """
        score = analysis_result.get("average_score", 50.0)
        return max(0.0, min(100.0, score))

    @staticmethod
    def get_stock_sector_score(analysis_result: Dict[str, Any], sector: Optional[str]) -> Optional[float]:
        """종목 하나의 Sector 점수 = 그 종목이 속한 Sector의 점수(1:1 매핑이므로 조회만 하면 됨).

        sector가 None이거나 analyze() 결과에 없는 Sector면 None을 반환한다 - 호출부
        (Phase 3 StockAnalyzer/Phase 4 결합기)가 결측으로 처리해야 한다.
        """
        if not sector:
            return None
        return analysis_result.get("sector_scores", {}).get(sector)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # Mock 데이터: 2개 Sector, Sector당 2종목, 20일치 가격
    def _mock_rows(ticker, market, start_price, daily_pct_change):
        rows = []
        price = start_price
        for day in range(60):
            date_str = f"202606{(day % 28) + 1:02d}"
            rows.append({
                "ticker": ticker, "market": market, "trade_date": f"2026{(day // 28) + 6:02d}{(day % 28) + 1:02d}",
                "close": price, "volume": 100000 + day * 1000,
            })
            price *= (1 + daily_pct_change / 100)
        return rows

    price_history = (
        _mock_rows("005930", "KOSPI", 70000, 0.5)  # 강세 종목
        + _mock_rows("000660", "KOSPI", 200000, 0.4)
        + _mock_rows("035420", "KOSPI", 180000, -0.2)  # 약세 종목
        + _mock_rows("068270", "KOSPI", 150000, -0.1)
    )
    sector_mapping = [
        {"ticker": "005930", "sector": "IT_Semiconductor", "market": "KOSPI", "needs_review": False},
        {"ticker": "000660", "sector": "IT_Semiconductor", "market": "KOSPI", "needs_review": False},
        {"ticker": "035420", "sector": "Consumer", "market": "KOSPI", "needs_review": False},
        {"ticker": "068270", "sector": "Consumer", "market": "KOSPI", "needs_review": False},
    ]

    analyzer = SectorAnalyzer()
    result = analyzer.run({"price_history": price_history, "sector_mapping": sector_mapping})

    print("=" * 80)
    print("【SectorAnalyzer 실계산 테스트】")
    print("=" * 80)
    print(f"전체 평균 점수: {result['score']:.1f}/100")
    for sector, score in result["details"]["sector_scores"].items():
        print(f"  {sector}: {score:.1f}")
