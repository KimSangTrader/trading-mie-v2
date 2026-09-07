"""
hierarchical_ranker - 시장→Sector→Theme→종목 계층형 최종 순위 결합기 (Phase 5-16)

================================================================================
【변경 이력】
================================================================================
【2026-08-23】최초 생성 (docs/hierarchical_scoring_plan.md Phase 4)
- 배경: sector_analy_method.txt(방법론 문서) 4절/6절이 제안한 최종 공식
      final_score = market*0.10 + sector*0.20 + theme*0.20 + stock*0.50
  을 실제로 계산한다. Phase 2(SectorAnalyzer/ThemeAnalyzer 실계산)와 Phase 3
  (StockAnalyzer)가 이미 각 레벨의 점수를 만들 수 있으므로, 이 모듈은 그 세 개를
  받아 종목별로 결합하기만 한다 - 순수 계산 모듈(API/DB 호출 없음).
- IntelligenceManager.run_all()의 flat 7-analyzer 가중평균을 대체하는 최종 경로다
  (사용자가 명시적으로 "최종 결합도 문서의 계층형 공식으로 전면 교체"를 선택함 -
  docs/hierarchical_scoring_plan.md 결정 사항 참고). 다만 이 모듈은
  IntelligenceManager를 직접 수정하지 않는다 - main.py가 이 모듈을 어떻게
  호출할지는 실제 DB/API 라이브 검증이 가능한 사용자 환경에서 마무리하는 것이
  안전하다고 판단해, 이 세션은 "결합 로직 자체"와 그 로직을 DB에서 읽은 데이터로
  구동하는 파이프라인(market_intelligence/collectors/hierarchical_ranking_pipeline.py)
  까지만 준비한다.
- 시장(Level 1) 점수: 기존 MarketAnalyzer는 KOSPI/KOSDAQ를 하나로 합친 단일
  market_strength만 낸다. 방법론 문서 6절은 "KOSPI 75점, KOSDAQ 45점"처럼 시장별로
  분리된 점수를 요구하므로, 이 모듈은 각 시장의 등락률만으로 별도 점수를 내는
  compute_market_regime_score()를 새로 둔다(스케일링 폭 ±3%는 이 세션이 고른 값 -
  KOSPI/KOSDAQ 일간 등락률 분포 기준으로 조정이 필요할 수 있음).
- 결측 처리 원칙(이 프로젝트 전체와 동일 - ValuationAnalyzer가 시초): 종목에 Theme가
  없거나 Sector 매핑이 없는 등 특정 레벨 점수가 없으면 "중립 50점"으로 조용히
  채우지 않고, price_series.renormalize_to_100()으로 나머지 레벨만으로
  재정규화한다 - 그 결과 예를 들어 Theme가 없는 종목은 사실상
  market*0.125+sector*0.25+stock*0.625로 계산되는 셈이다(가중치 비율은 유지,
  분모만 100에서 80으로 줄어듦).
【2026-08-23】_MARKET_REGIME_SPAN_PCT 3.0 → 6.0 (Phase 5-17 라이브 검증 중 사용자 확인)
- 배경: 사용자가 실제 KIS 화면에서 2026-08-13~08-21 KOSPI/KOSDAQ 일별 등락률
  6일치를 캡처해 보여줬다: KOSPI [+0.88, +5.89, -5.80, -1.55, +2.42, +3.56],
  KOSDAQ [-4.63, +1.99, -1.17, -3.52, +0.38, +0.29]. 표준편차가 KOSPI 약 ±3.8%,
  KOSDAQ 약 ±2.3%로 계산돼(이 세션이 계산), 옛 ±3% 폭은 특히 KOSPI 쪽에서 절반
  가까운 날이 0점/100점으로 눌려 변별력을 잃고 있었다(예: +5.89%나 -5.80%가
  전부 100/0으로 뭉개짐). 사용자에게 "고정폭 확대(빠름)" vs "실제 변동성 기반
  동적 스케일(견고하지만 추가 라이브 검증 필요)" 중 선택지를 물었고, 고정폭 확대를
  선택함 - 6일치 표본의 KOSPI +5.89%/-5.80%가 새 폭에서는 거의 극값 근처(하지만
  완전히 눌리지는 않는) 점수가 나오도록 6.0%로 정했다. 여전히 임의 선택값이라
  변동성 국면이 또 바뀌면(예: 다시 저변동성 장세) 재조정이 필요할 수 있다 - 더
  견고한 방법(지수 등락률의 최근 N일 실현변동성 기반 동적 폭)은 사용자가 명시적으로
  보류했다(선택하지 않음), 나중에 필요하면 다시 논의.
================================================================================
"""

from typing import Any, Dict, List, Optional
import logging

from market_intelligence.analyzers.sector_analyzer import SectorAnalyzer
from market_intelligence.analyzers.stock_analyzer import StockAnalyzer
from market_intelligence.analyzers.theme_analyzer import ThemeAnalyzer
from market_intelligence.price_series import renormalize_to_100, scale_symmetric

logger = logging.getLogger(__name__)

_MARKET_MAX = 10.0
_SECTOR_MAX = 20.0
_THEME_MAX = 20.0
_STOCK_MAX = 50.0

_MARKET_REGIME_SPAN_PCT = 6.0  # 지수 일간 등락률 ±6%에서 0점/100점 (2026-08-23, 변경이력 참고)


def compute_market_regime_score(change_rate_pct: Optional[float]) -> Optional[float]:
    """시장(KOSPI 또는 KOSDAQ) 하나의 당일 등락률만으로 0~100점을 낸다.

    change_rate_pct가 None이면 그 시장 점수를 결측으로 두고(중립 50으로 채우지
    않음), 호출부가 rank_stocks()의 재정규화 로직에 맡긴다.
    """
    if change_rate_pct is None:
        return None
    return scale_symmetric(change_rate_pct, 100.0, _MARKET_REGIME_SPAN_PCT)


def rank_stocks(
    stocks: List[Dict[str, Any]],
    market_regime_scores: Dict[str, Optional[float]],
    sector_analysis: Dict[str, Any],
    theme_analysis: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """종목 리스트를 방법론 문서의 계층형 공식으로 채점하고 순위를 매긴다.

    Args:
        stocks: 종목별 입력. 각 원소는 StockAnalyzer가 요구하는 필드(price_rows,
            symbol, market, per/pbr/dividend_yield, market_per 등, 선택적
            supply_demand_score)에 더해 "sector"(str)와 "primary_theme"/
            "secondary_themes"(list)를 포함해야 한다.
        market_regime_scores: {"KOSPI": 75.0, "KOSDAQ": 45.0} 같은 시장별 점수 -
            보통 compute_market_regime_score()로 미리 계산해서 넘긴다.
        sector_analysis / theme_analysis: SectorAnalyzer.run()/ThemeAnalyzer.run()의
            "details" 딕셔너리(= analyze()의 반환값 그대로).

    Returns:
        각 종목에 대해 다음을 담은 dict 리스트(입력 순서 유지 - 정렬은 호출부가
        final_score 등 원하는 기준으로 한다):
        {"symbol":, "market":, "sector":, "market_score":, "sector_score":,
         "theme_score":, "stock_score":, "final_score":,
         "stock_analysis": StockAnalyzer 상세 결과}
    """
    stock_analyzer = StockAnalyzer()
    results = []

    for stock in stocks:
        symbol = stock.get("symbol")
        market = stock.get("market")
        sector = stock.get("sector")
        primary_theme = stock.get("primary_theme")
        secondary_themes = stock.get("secondary_themes") or []

        market_score = market_regime_scores.get(market) if market else None
        sector_score = SectorAnalyzer.get_stock_sector_score(sector_analysis, sector)
        theme_score = ThemeAnalyzer.get_stock_theme_score(theme_analysis, primary_theme, secondary_themes)

        sector_return_20d = None
        if sector:
            sector_return_20d = sector_analysis.get("sector_details", {}).get(sector, {}).get("return_20d_pct")

        stock_input = {k: v for k, v in stock.items() if k not in ("sector", "primary_theme", "secondary_themes")}
        stock_input.setdefault("sector_return_20d", sector_return_20d)

        stock_result = stock_analyzer.run(stock_input)
        stock_score = stock_result["score"]

        # 【중요】renormalize_to_100()은 각 컴포넌트 값이 "이미 그 컴포넌트의 만점
        # 범위(max_pts)로 환산된 점수"라고 가정한다(score_basket/StockAnalyzer와
        # 동일한 규약). market/sector/theme/stock_score는 전부 원점수가 0~100
        # 범위이므로, 그대로 넘기면 예를 들어 "70점(100점 만점)"이 "70점(10점
        # 만점)"으로 잘못 해석되어 거의 모든 종목이 100점 상한에 눌린다 - 반드시
        # raw_score * max_pts / 100로 그 레벨의 배점 범위로 먼저 축소해야 한다.
        final_components = {
            "market": (market_score * _MARKET_MAX / 100.0 if market_score is not None else None, _MARKET_MAX),
            "sector": (sector_score * _SECTOR_MAX / 100.0 if sector_score is not None else None, _SECTOR_MAX),
            "theme": (theme_score * _THEME_MAX / 100.0 if theme_score is not None else None, _THEME_MAX),
            "stock": (stock_score * _STOCK_MAX / 100.0 if stock_score is not None else None, _STOCK_MAX),
        }
        final_score = renormalize_to_100(final_components)

        results.append({
            "symbol": symbol,
            "market": market,
            "sector": sector,
            "primary_theme": primary_theme,
            "market_score": market_score,
            "sector_score": sector_score,
            "theme_score": theme_score,
            "stock_score": stock_score,
            "final_score": final_score,
            "stock_analysis": stock_result.get("details", {}),
        })

    _assign_group_ranks(results, "sector", "sector_rank")
    _assign_group_ranks(results, "primary_theme", "theme_rank")

    logger.info(f"✅ 계층형 순위 계산 완료: {len(results)}종목")
    return results


def _assign_group_ranks(results: List[Dict[str, Any]], group_key: str, rank_field: str) -> None:
    """같은 그룹(Sector 또는 Primary Theme) 안에서 final_score 기준 순위를 매겨
    결과 dict에 in-place로 추가한다. 그룹이 없는(None) 종목은 순위를 매기지 않는다
    (문서 9절 "Sector 내 순위/Theme 내 순위" 보조 지표)."""
    groups: Dict[Any, List[Dict[str, Any]]] = {}
    for r in results:
        key = r.get(group_key)
        if key is None:
            continue
        groups.setdefault(key, []).append(r)

    for members in groups.values():
        ranked = sorted(members, key=lambda r: r["final_score"], reverse=True)
        for i, r in enumerate(ranked, start=1):
            r[rank_field] = i
