"""
StockAnalyzer - 개별 종목 100점 분석기 (Phase 5-15, 신규)

================================================================================
【변경 이력】
================================================================================
【2026-08-23】최초 생성 (docs/hierarchical_scoring_plan.md Phase 3)
- 배경: sector_analy_method.txt(방법론 문서) 5절/6절이 제안한 "개별 종목 100점"
  구조를 구현한다: 기술적35 + 수급25 + 밸류에이션20 + Sector 내 상대강도20.
  기존 7개 analyzer 어디에도 이 조합을 만드는 analyzer가 없었다(TechnicalAnalyzer는
  MACD/RSI/BB/MA 자체 배점이라 문서의 "단기모멘텀/중기모멘텀/거래량/RSI/추세" 35점
  배점과 다름 - 그래서 이 analyzer는 TechnicalAnalyzer를 재사용하는 대신
  market_intelligence/price_series.py의 종목별 수익률·거래대금·이평선 계산을
  SectorAnalyzer/ThemeAnalyzer와 동일하게 재사용해서 문서 배점을 직접 만든다).
- 순수 계산기 원칙을 지키되, 밸류에이션 20점만 예외적으로 기존
  ValuationAnalyzer(순수 계산기)를 내부에서 호출해 재사용한다 - 새로 만들지 않고
  중복을 피하기 위함.
- 【알려진 한계 - docs/hierarchical_scoring_plan.md Phase 3 리스크 항목과 동일】
  1. 수급 25점(외국인/기관 순매수): 이 코드베이스에 종목별 투자자 매매동향을 조회하는
     방법이 아직 없다(시장 전체 합계인 MoneyFlowAnalyzer/money_flow_data 테이블뿐).
     원시 순매수 금액(원)은 종목 시가총액에 따라 스케일이 완전히 달라서, 데이터도
     없는데 임의의 스케일링 함수를 지어내는 것은 조용히 틀린 값을 주는 것과 같다
     (ValuationAnalyzer가 지키는 원칙 위반). 그래서 이 컴포넌트는 데이터 소스가
     연동되기 전까지 캐시로만 열어둔다: 호출부가 이미 0~100으로 정규화된
     `data["supply_demand_score"]`를 넘기면 그대로 25점 배점에 반영하고, 없으면
     결측으로 완전히 제외한 뒤 나머지 3개 구성요소로 재정규화한다.
  2. 밸류에이션 20점: 방법론 문서는 "같은 Sector의 PER 중앙값"과 비교하라고
     하는데, 이 프로젝트의 market_valuation.py는 아직 시장(KOSPI/KOSDAQ) 전체
     중앙값만 계산한다. 이 analyzer는 호출부가 `sector_per_median` 등을 넘기면
     그것을 우선 쓰고, 없으면 `market_per` 등(시장 전체 중앙값)으로 자동
     대체한다 - Sector 중앙값 계산 파이프라인은 별도 후속 작업으로 남긴다.
- 각 배점의 원시값→점수 스케일링 함수는 SectorAnalyzer/ThemeAnalyzer와 동일하게
  price_series.py의 scale_symmetric()/scale_ratio()를 그대로 재사용한다 - 방법론
  문서가 스케일링 공식을 명시하지 않아 이 세션이 합리적으로 고른 값이며, 실거래
  데이터 분포를 보고 조정이 필요할 수 있다(price_series.py 상단 주석과 동일 경고).
【2026-08-24】수급 25점 데이터 소스 연동 완료 (Phase 5-18, 위 "알려진 한계 1" 해소)
- data/kis_client.py.get_investor_trend() + market_intelligence/supply_demand.py.
  compute_supply_demand_score()가 신규로 이 컴포넌트를 채운다. main.py의
  run_analysis_cycle()이 종목별로 계산한 점수를 valuation_by_ticker 경유로
  data["supply_demand_score"]에 넣어준다(main.py Phase 5-18 변경이력 참고).
  이 파일(StockAnalyzer) 자체는 아무것도 바뀌지 않았다 - 애초에 "호출부가 채워
  주면 쓰고, 없으면 결측 처리"하도록 설계돼 있었기 때문(위 클래스 docstring
  "알려진 한계 1" 참고). 아직 라이브 검증(실제 KIS 응답 필드명 확인)은 못했다 -
  main.py 변경이력의 동일 항목 참고.
【2026-08-24】밸류에이션 20점 데이터 소스 연동 완료 (Phase 5-19, 위 "알려진 한계 2" 해소)
- market_intelligence/market_valuation.py + market_intelligence/collectors/
  valuation_pipeline.py가 신규로 Sector별 PER/PBR/배당 중앙값을 계산해
  `data["sector_per_median"]` 등을 채워준다(main.py의 get_latest_stock_valuations()
  경유). 이 파일(StockAnalyzer)도 아무것도 바뀌지 않았다 - 위 "알려진 한계 2"에서
  이미 "호출부가 sector_per_median 등을 넘기면 우선 쓰고, 없으면 market_per로
  자동 대체"하도록 설계해 뒀기 때문. 자세한 내용은 main.py/market_valuation.py
  변경이력 참고.
================================================================================
"""

from typing import Any, Dict, List, Optional
import logging

from market_intelligence.base_analyzer import BaseAnalyzer
from market_intelligence.analyzers.valuation_analyzer import ValuationAnalyzer
from market_intelligence.price_series import (
    compute_ticker_metrics,
    renormalize_to_100,
    scale_ratio,
    scale_symmetric,
)
from data.technical_indicators import TechnicalIndicators

logger = logging.getLogger(__name__)

# 기술적 35점 내부 배점 (문서 5-A절 예시 그대로)
_SHORT_MOMENTUM_MAX = 10.0
_SHORT_MOMENTUM_SPAN_PCT = 10.0  # 5일 수익률 ±10%에서 0점/만점
_MID_MOMENTUM_MAX = 10.0
_MID_MOMENTUM_SPAN_PCT = 15.0  # 20일 수익률 ±15%에서 0점/만점
_VOLUME_MAX = 5.0
_VOLUME_SPAN_RATIO = 1.0  # 거래대금 비율 0배~2배에서 0점/만점
_RSI_MAX = 5.0
_TREND_MAX = 5.0

# 수급 25점 / Sector 상대강도 20점 (문서 5-B/D절)
_SUPPLY_DEMAND_MAX = 25.0
_SECTOR_RELATIVE_MAX = 20.0
_SECTOR_RELATIVE_SPAN_PCT = 10.0  # Sector 대비 ±10%p 초과수익률에서 0점/만점

# 밸류에이션은 기존 ValuationAnalyzer(0~100)를 20점 배점으로 그대로 축소한다
_VALUATION_MAX = 20.0


class StockAnalyzer(BaseAnalyzer):
    """개별 종목 100점 분석기 - 기술적35 + 수급25 + 밸류에이션20 + Sector상대강도20.

    IntelligenceManager의 flat 7-analyzer 체계에는 등록하지 않는다 - 이 analyzer는
    계층형 결합기(Phase 4)에서 "종목 개별 점수" 레벨(최종 공식의 stock*0.50)을
    만드는 용도로만 쓰인다.
    """

    def __init__(self):
        super().__init__(name="stock", weight=0.50)  # 0.50은 최종 계층형 공식에서의 몫을 나타내는 값
        self._valuation_analyzer = ValuationAnalyzer()
        logger.info(f"✅ StockAnalyzer 초기화 완료 (weight={self.weight})")

    def validate(self, data: Dict[str, Any]) -> bool:
        """
        필수 입력:
        - price_rows: 이 종목 자신의 일봉 리스트 [{"trade_date":, "close":, "volume":}, ...]

        선택 입력:
        - symbol, market
        - per, pbr, dividend_yield (이 종목 자신의 값)
        - sector_per_median/sector_pbr_median/sector_dividend_median (우선 사용) 또는
          market_per/market_pbr/market_dividend_yield (없으면 이걸로 대체)
        - sector_return_20d (그 종목이 속한 Sector의 20일 수익률 중앙값 -
          SectorAnalyzer 결과의 sector_details[sector]["return_20d_pct"])
        - supply_demand_score (0~100, 이미 정규화된 수급 점수 - 없으면 결측 처리)
        """
        if not isinstance(data, dict):
            return False
        return bool(data.get("price_rows"))

    def analyze(self, data: Dict[str, Any]) -> Dict[str, Any]:
        rows: List[Dict[str, Any]] = sorted(
            data["price_rows"], key=lambda r: r.get("trade_date") or ""
        )
        metrics = compute_ticker_metrics(rows)
        closes = [float(r["close"]) for r in rows if r.get("close") is not None]

        rsi_value: Optional[float] = None
        if len(closes) >= 15:  # TechnicalIndicators.calculate_rsi 기본 period=14
            try:
                rsi_value = TechnicalIndicators.calculate_rsi(closes)
            except Exception as e:
                logger.warning(f"⚠️  RSI 계산 실패 - {e}")

        trend_points: Optional[float] = None
        if metrics is not None and metrics.get("ma20_above_ma60") is not None:
            trend_points = _TREND_MAX if metrics["ma20_above_ma60"] else 0.0

        # ---------- A. 기술적 35점 ----------
        technical_components = {
            "short_momentum": (
                scale_symmetric(metrics.get("return_5d") if metrics else None,
                                 _SHORT_MOMENTUM_MAX, _SHORT_MOMENTUM_SPAN_PCT),
                _SHORT_MOMENTUM_MAX,
            ),
            "mid_momentum": (
                scale_symmetric(metrics.get("return_20d") if metrics else None,
                                 _MID_MOMENTUM_MAX, _MID_MOMENTUM_SPAN_PCT),
                _MID_MOMENTUM_MAX,
            ),
            "volume": (
                scale_ratio(metrics.get("trading_value_ratio") if metrics else None,
                            _VOLUME_MAX, _VOLUME_SPAN_RATIO),
                _VOLUME_MAX,
            ),
            "rsi": (
                scale_symmetric((rsi_value - 50) if rsi_value is not None else None, _RSI_MAX, 50.0),
                _RSI_MAX,
            ),
            "trend": (trend_points, _TREND_MAX),
        }
        technical_subscore_100 = renormalize_to_100(technical_components)
        technical_points = technical_subscore_100 * (35.0 / 100.0) if metrics is not None else None

        # ---------- B. 수급 25점 (결측 시 완전 제외 - 클래스 docstring 참고) ----------
        supply_demand_score = data.get("supply_demand_score")
        supply_demand_points = (
            max(0.0, min(100.0, supply_demand_score)) * (_SUPPLY_DEMAND_MAX / 100.0)
            if supply_demand_score is not None else None
        )

        # ---------- C. 밸류에이션 20점 (ValuationAnalyzer 재사용, Sector 중앙값 우선) ----------
        sector_per = data.get("sector_per_median", data.get("market_per"))
        sector_pbr = data.get("sector_pbr_median", data.get("market_pbr"))
        sector_dividend = data.get("sector_dividend_median", data.get("market_dividend_yield"))
        valuation_basis = "sector" if data.get("sector_per_median") is not None else "market"

        valuation_result = self._valuation_analyzer.run({
            "symbol": data.get("symbol"), "market": data.get("market"),
            "asset_type": data.get("asset_type", "stock"),
            "per": data.get("per"), "pbr": data.get("pbr"),
            "dividend_yield": data.get("dividend_yield"),
            "market_per": sector_per, "market_pbr": sector_pbr,
            "market_dividend_yield": sector_dividend,
        })
        valuation_points = valuation_result["score"] * (_VALUATION_MAX / 100.0)

        # ---------- D. Sector 내 상대강도 20점 ----------
        sector_relative_pct = None
        if metrics and metrics.get("return_20d") is not None and data.get("sector_return_20d") is not None:
            sector_relative_pct = metrics["return_20d"] - data["sector_return_20d"]
        sector_relative_points = scale_symmetric(sector_relative_pct, _SECTOR_RELATIVE_MAX, _SECTOR_RELATIVE_SPAN_PCT)

        stock_components = {
            "technical": (technical_points, 35.0),
            "supply_demand": (supply_demand_points, _SUPPLY_DEMAND_MAX),
            "valuation": (valuation_points, _VALUATION_MAX),
            "sector_relative": (sector_relative_points, _SECTOR_RELATIVE_MAX),
        }
        stock_score = renormalize_to_100(stock_components)

        return {
            "symbol": data.get("symbol"),
            "market": data.get("market"),
            "metrics": metrics,
            "rsi": rsi_value,
            "technical_subscore": technical_subscore_100,
            "technical_points": technical_points,
            "supply_demand_points": supply_demand_points,
            "valuation_points": valuation_points,
            "valuation_score_100": valuation_result["score"],
            "valuation_basis": valuation_basis,
            "sector_relative_pct": sector_relative_pct,
            "sector_relative_points": sector_relative_points,
            "component_points": {k: pts for k, (pts, _) in stock_components.items()},
            "stock_score": stock_score,
            "data_quality": 100.0 if metrics is not None else 0.0,
        }

    def get_score(self, analysis_result: Dict[str, Any]) -> float:
        return max(0.0, min(100.0, analysis_result.get("stock_score", 50.0)))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    price_rows = []
    price = 70000
    for day in range(65):
        price_rows.append({
            "ticker": "005930", "market": "KOSPI",
            "trade_date": f"2026{(day // 28) + 6:02d}{(day % 28) + 1:02d}",
            "close": round(price, 2), "volume": 500000 + day * 1000,
        })
        price *= 1.004  # 꾸준한 상승 종목

    analyzer = StockAnalyzer()
    result = analyzer.run({
        "price_rows": price_rows, "symbol": "005930", "market": "KOSPI",
        "per": 15.2, "pbr": 1.4, "dividend_yield": 2.5,
        "market_per": 18.4, "market_pbr": 1.72, "market_dividend_yield": 2.05,
        "sector_return_20d": 3.0,  # 이 종목이 속한 Sector는 20일간 +3%
    })

    print("=" * 80)
    print("【StockAnalyzer 테스트】삼성전자 가정")
    print("=" * 80)
    print(f"종목 점수: {result['score']:.1f}/100")
    for k, v in result["details"]["component_points"].items():
        print(f"  {k}: {v}")
