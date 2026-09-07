"""
HierarchicalRankingPipeline - Sector/Theme 매핑+가격 히스토리 → 계층형 순위 → DB 저장 (Phase 5-16)

================================================================================
【변경 이력】
================================================================================
【2026-08-23】최초 생성 (docs/hierarchical_scoring_plan.md Phase 4)
- 배경: market_intelligence/hierarchical_ranker.py(순수 계산)를 실제 DB 데이터로
  구동해서 stock_hierarchical_scores에 저장까지 하는 엔드투엔드 파이프라인.
  data/price_history_collector.py + price_history_pipeline.py, 그리고
  valuation_collector.py + valuation_pipeline.py와 동일한 "수집기/analyzer는
  순수 계산, pipeline이 DB와 이어붙인다" 역할 분리 원칙을 따른다.
- main.py의 기존 per-stock 루프(run_analysis_cycle)는 이 파이프라인을 호출하도록
  아직 바꾸지 않았다 - main.py는 종목 하나씩 순회하며 IntelligenceManager를
  실행하는 구조인데, Sector/Theme 실계산은 종목 하나가 아니라 "전체 종목의 가격
  히스토리"가 있어야 하는 배치 성격의 계산이라 그 루프 안에 그대로 끼워 넣으면
  종목마다 SectorAnalyzer/ThemeAnalyzer를 반복 실행하는 낭비가 생긴다. main.py를
  이 파이프라인을 쓰도록 바꾸는 건 실제 DB/API로 라이브 검증하면서 진행하는 것이
  안전하다고 판단해 후속 작업으로 남긴다(docs/hierarchical_scoring_plan.md 참고).
- 이 세션은 실제 RDS/KIS API에 접근할 수 없어 SQLite + 수동 구성한 price_history/
  sector_mapping/theme_mapping으로만 검증했다(tests/test_hierarchical_ranking_pipeline.py).
  실제 대규모(2,700여 종목) 데이터로는 사용자 환경에서 라이브 검증이 필요하다.
【2026-08-23】_to_float() 방어적 캐스팅 추가 (Phase 5-17, 사용자 라이브 검증 중 발견)
- 배경: 실제 사용자 환경에서 첫 라이브 실행 시 psycopg2가 "schema "np" does not
  exist" 에러를 냈다 - 실제 원인은 StockAnalyzer의 기술적 점수 계산 경로가
  data/technical_indicators.py의 calculate_rsi()(내부적으로 numpy 배열 연산)를
  거치면서 stock_score/final_score에 numpy.float64가 섞여 들어갔고, psycopg2가
  이 타입을 SQL 파라미터로 못 받아 에러 메시지를 스키마명으로 오해석한 것이었다.
  calculate_rsi() 자체도 float()로 감싸도록 고쳤지만(근본 원인), 이 파이프라인이
  DB에 쓰는 마지막 경계이기도 하므로 여기서도 float()로 한 번 더 감싸 다른 경로로
  numpy 타입이 섞여 들어와도 INSERT가 깨지지 않도록 방어했다.
================================================================================
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from market_intelligence.analyzers.sector_analyzer import SectorAnalyzer
from market_intelligence.analyzers.theme_analyzer import ThemeAnalyzer
from market_intelligence.hierarchical_ranker import rank_stocks
from market_intelligence.price_series import group_price_rows_by_ticker

logger = logging.getLogger(__name__)


def _to_float(value: Optional[Any]) -> Optional[float]:
    """DB INSERT 직전 방어적 float 캐스팅 - numpy.float64 등이 섞여 들어와도
    psycopg2가 SQL 파라미터로 못 받아 깨지지 않도록 한다(변경이력 참고)."""
    return float(value) if value is not None else None


def run_hierarchical_ranking_pipeline(
    session,
    market_regime_scores: Dict[str, Optional[float]],
    price_history: Optional[List[Dict[str, Any]]] = None,
    sector_mapping: Optional[List[Dict[str, Any]]] = None,
    theme_mapping: Optional[List[Dict[str, Any]]] = None,
    valuation_by_ticker: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Args:
        session: SQLAlchemy Session. sector_mapping/theme_mapping/price_history를
            직접 넘기지 않으면 이 세션으로 DB에서 최신 배치를 조회한다. 결과 저장
            (add + commit)도 이 세션으로 한다 - 세션 생성/종료는 호출부 책임.
        market_regime_scores: {"KOSPI": 75.0, "KOSDAQ": 45.0} -
            hierarchical_ranker.compute_market_regime_score()로 미리 계산해서
            넘긴다(이 파이프라인은 KIS API를 모른다 - 지수 등락률 조회는 호출부 책임).
        price_history: None이면 stock_price_history 테이블 전체를 읽는다. 종목 수가
            많으면 호출부가 최근 N일로 필터링해서 넘기는 것을 권장(전체를 매번 읽으면
            느려짐 - 이 세션은 실제 규모로 성능을 검증할 수 없었다).
        sector_mapping / theme_mapping: None이면 data/sector_theme_importer.py의
            get_latest_sector_mapping()/get_latest_theme_mapping()으로 최신 배치를 읽는다.
        valuation_by_ticker: {ticker: {"per":, "pbr":, "dividend_yield":,
            "market_per":, "market_pbr":, "market_dividend_yield":, ...}} - 없으면
            밸류에이션 입력 없이 진행되고, StockAnalyzer가 알아서 중립(50점) 처리한다.

    Returns:
        {"total": 순위가 매겨진 종목 수, "saved": DB에 저장한 행 수,
         "sector_count": 계산된 Sector 수, "theme_count": 계산된 Theme 수}
        가격 데이터가 있는 종목이 하나도 없으면 {"total": 0, "saved": 0}.
    """
    from db.models import StockHierarchicalScore, StockPriceHistory

    if sector_mapping is None:
        from data.sector_theme_importer import get_latest_sector_mapping
        sector_mapping = get_latest_sector_mapping(session)
    if theme_mapping is None:
        from data.sector_theme_importer import get_latest_theme_mapping
        theme_mapping = get_latest_theme_mapping(session)
    if price_history is None:
        rows = session.query(StockPriceHistory).all()
        price_history = [
            {
                "ticker": r.ticker, "market": r.market, "trade_date": r.trade_date,
                "close": float(r.close) if r.close is not None else None,
                "volume": int(r.volume) if r.volume is not None else None,
            }
            for r in rows
        ]

    if not sector_mapping and not theme_mapping:
        logger.warning("⚠️  Sector/Theme 매핑이 없습니다 - 계층형 순위를 계산할 수 없습니다")
        return {"total": 0, "saved": 0}

    sector_analysis = SectorAnalyzer().run(
        {"price_history": price_history, "sector_mapping": sector_mapping}
    ).get("details", {})
    theme_analysis = ThemeAnalyzer().run(
        {"price_history": price_history, "theme_mapping": theme_mapping}
    ).get("details", {})

    price_by_ticker = group_price_rows_by_ticker(price_history)
    sector_by_ticker: Dict[str, str] = {}
    market_by_ticker: Dict[str, str] = {}
    for row in sector_mapping:
        ticker = row.get("ticker")
        if not ticker:
            continue
        if row.get("sector"):
            sector_by_ticker[ticker] = row["sector"]
        if row.get("market"):
            market_by_ticker[ticker] = row["market"]

    theme_by_ticker: Dict[str, Dict[str, Any]] = {}
    for row in theme_mapping:
        ticker = row.get("ticker")
        if not ticker or not row.get("theme"):
            continue
        bucket = theme_by_ticker.setdefault(ticker, {"primary": None, "secondary": []})
        if row.get("is_primary"):
            bucket["primary"] = row["theme"]
        else:
            bucket["secondary"].append(row["theme"])

    valuation_by_ticker = valuation_by_ticker or {}

    # 가격 히스토리 없이는 StockAnalyzer가 아무것도 계산할 수 없으므로(validate() 실패
    # 시 0점) 그런 종목은 애초에 순위 대상에서 제외한다 - "0점"으로 순위를 오염시키는
    # 대신, 데이터가 확보된 종목만으로 순위를 매긴다.
    all_tickers = set(sector_by_ticker) | set(theme_by_ticker)
    stocks = []
    for ticker in all_tickers:
        rows = price_by_ticker.get(ticker)
        if not rows:
            continue
        theme_info = theme_by_ticker.get(ticker, {})
        stock_input = {
            "symbol": ticker,
            "market": market_by_ticker.get(ticker),
            "sector": sector_by_ticker.get(ticker),
            "primary_theme": theme_info.get("primary"),
            "secondary_themes": theme_info.get("secondary", []),
            "price_rows": rows,
        }
        stock_input.update(valuation_by_ticker.get(ticker, {}))
        stocks.append(stock_input)

    if not stocks:
        logger.warning("⚠️  가격 히스토리가 확보된 종목이 없어 계층형 순위를 계산할 수 없습니다")
        return {"total": 0, "saved": 0}

    results = rank_stocks(stocks, market_regime_scores, sector_analysis, theme_analysis)
    results.sort(key=lambda r: r["final_score"], reverse=True)
    for i, r in enumerate(results, start=1):
        r["overall_rank"] = i

    batch_ts = datetime.now(timezone.utc)
    for r in results:
        session.add(StockHierarchicalScore(
            timestamp=batch_ts,
            ticker=r["symbol"], market=r["market"], sector=r["sector"],
            primary_theme=r["primary_theme"],
            market_score=_to_float(r["market_score"]), sector_score=_to_float(r["sector_score"]),
            theme_score=_to_float(r["theme_score"]), stock_score=_to_float(r["stock_score"]),
            final_score=_to_float(r["final_score"]),
            sector_rank=r.get("sector_rank"), theme_rank=r.get("theme_rank"),
            overall_rank=r["overall_rank"],
        ))
    session.commit()

    logger.info(
        f"✅ 계층형 순위 파이프라인 완료: {len(results)}종목 저장, "
        f"Sector {len(sector_analysis.get('sector_scores', {}))}개, "
        f"Theme {len(theme_analysis.get('theme_scores', {}))}개"
    )
    return {
        "total": len(results), "saved": len(results),
        "sector_count": len(sector_analysis.get("sector_scores", {})),
        "theme_count": len(theme_analysis.get("theme_scores", {})),
    }
