"""
ValuationAnalyzer - 기본분석 모듈 (Phase 5-5: 상대평가 전면 교체)
PER, PBR, 배당수익률을 "시장(KOSPI/KOSDAQ) 중앙값 대비 상대값"으로 평가

================================================================================
【변경 이력】
================================================================================
【2026-08-13 수정】weight 0.25 → 0.09로 변경

【2026-08-14】Phase 5-2: 개별 종목 실시간 데이터 연동 (KISClient 내부 결합)
- 이후 Phase 5 방향 보고서 검토 결과, 아래 Phase 5-5에서 다시 교체됨

【2026-08-14】Phase 5-5: 절대값 점수 → 시장 대비 상대평가로 전면 교체
- 배경 (Phase 5 방향 보고서 지적사항):
  1. 기존 방식(100 - per*3)은 PER의 절대값만 봄 — "삼성전자 PER 15"가
     좋은지 나쁜지는 KOSPI 중앙값(예: 18) 대비로 판단해야 함
  2. ValuationAnalyzer가 KISClient를 직접 호출하는 구조는 종목 수가
     많아지면(KOSPI/KOSDAQ 전체 분석 등) 좋지 않음 → API 호출 없는
     순수 계산 모듈로 분리
- 변경 사항:
  * __init__(kis_client=...) 파라미터 완전 제거. 이제 순수 계산기이며
    API를 호출하지 않는다. 실시간 데이터 수집은 별도 계층
    (KISClient.get_stock_fundamental() + 추후 ValuationCollector,
    시장 중앙값은 market_intelligence/market_valuation.py)의 책임이다.
  * 입력 데이터 계약을 다음으로 통일 (Phase 5 방향 보고서 7번 항목과 동일):
      symbol, market('KOSPI'/'KOSDAQ'), per, pbr, dividend_yield,
      market_per, market_pbr, market_dividend_yield
  * per_relative = per / market_per (낮을수록 저평가)
    pbr_relative = pbr / market_pbr (낮을수록 저평가)
    dividend_relative = dividend_yield / market_dividend_yield (높을수록 좋음)
  * 각 지표 점수는 상대값 1.0(시장과 동일)을 50점 기준으로 대칭 매핑:
      저평가/고배당 지표일수록 100에 가깝고, 고평가/저배당 지표일수록 0에 가까움
  * 시장 기준값이 없는 지표는 "억지로 50점 처리하지 않고" 그 지표를 가중평균에서
    제외한 뒤 나머지 지표로 재정규화하고, data_quality로 결측 정도를 별도 노출
    (Phase 5 방향 보고서 Phase 5-6 요구사항을 함께 반영)
  * 코인/크립토 자산은 여전히 밸류에이션 미적용 → 중립(50점) 처리 유지
- 하위 호환 안내:
  * 이전 방식(per/pbr/dividend_yield만 제공, market_per 등 없음)으로 호출하면
    상대평가를 계산할 시장 기준값이 없으므로 데이터 부족(insufficient_data)으로
    처리되어 중립(50점) + data_quality 낮음으로 반환된다. 즉 "조용히 틀린 값"을
    주지 않고, 값이 없다는 사실 자체를 신호로 넘긴다.
================================================================================
"""

import sys
import os
from typing import Any, Dict, Optional
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from market_intelligence.base_analyzer import BaseAnalyzer

logger = logging.getLogger(__name__)

# 코인/크립토처럼 PER·PBR 개념이 적용되지 않는 자산 유형
_NON_EQUITY_ASSET_TYPES = {"coin", "crypto", "cryptocurrency"}

# 내부 지표 가중치 (기존 Phase 4 가중치와 동일하게 유지 — PER 35% / PBR 35% / 배당 30%)
_WEIGHT_PER = 0.35
_WEIGHT_PBR = 0.35
_WEIGHT_DIVIDEND = 0.30

# 상대값 1.0(시장과 동일) 대비 편차 1.0당 몇 점을 움직일지 (대칭, 0~100로 clip)
_RELATIVE_SCORE_SCALE = 100


def _relative_score(value: Optional[float], market_value: Optional[float], higher_is_better: bool) -> Optional[float]:
    """
    시장 대비 상대값을 0~100 점수로 변환.

    - value 또는 market_value가 없거나(0 이하 포함) 계산 불가하면 None 반환
      (→ 호출부가 이 지표를 가중평균에서 제외)
    - relative = value / market_value
    - higher_is_better=False (PER, PBR): relative가 1보다 작을수록(저평가) 고득점
    - higher_is_better=True  (배당수익률): relative가 1보다 클수록(고배당) 고득점
    - relative == 1.0(시장과 동일)일 때 50점 기준
    """
    if value is None or market_value is None:
        return None
    try:
        value = float(value)
        market_value = float(market_value)
    except (TypeError, ValueError):
        return None
    if value <= 0 or market_value <= 0:
        return None

    relative = value / market_value

    if higher_is_better:
        score = 50 + (relative - 1) * _RELATIVE_SCORE_SCALE
    else:
        score = 50 + (1 - relative) * _RELATIVE_SCORE_SCALE

    return max(0.0, min(100.0, score))


class ValuationAnalyzer(BaseAnalyzer):
    """기본분석 모듈 - PER/PBR/배당수익률의 "시장 대비 상대평가" (개별 종목 기준)

    API를 호출하지 않는 순수 계산 모듈이다. 실시간 종목 PER/PBR과 시장(KOSPI/
    KOSDAQ) 중앙값은 호출부가 KISClient.get_stock_fundamental() +
    market_intelligence.market_valuation.MarketValuation으로 준비해서 넘겨준다.
    """

    def __init__(self):
        super().__init__(name="valuation", weight=0.09)
        logger.info(f"✅ ValuationAnalyzer 초기화 완료 (상대평가 모드, weight={self.weight})")

    def validate(self, data: Dict[str, Any]) -> bool:
        """
        데이터 검증

        analyze()가 (1) 코인 등 밸류에이션 미적용 자산 → 중립 처리,
        (2) 상대평가 계산 가능한 지표만 부분적으로 계산,
        (3) 계산 가능한 지표가 하나도 없으면 데이터 부족으로 중립 처리
        까지 모두 스스로 처리하므로, data가 dict이기만 하면 유효로 본다.
        """
        return isinstance(data, dict)

    def analyze(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """기본분석 수행 (시장 대비 상대평가)"""
        asset_type = str(data.get("asset_type", "stock")).lower()
        symbol = data.get("symbol", "")
        market = data.get("market", "")

        # 1) 코인 등 밸류에이션 미적용 자산 → 중립 처리
        if asset_type in _NON_EQUITY_ASSET_TYPES:
            logger.info(f"ℹ️  {symbol or '코인'}: PER/PBR 밸류에이션 미적용 자산 → 중립(50점) 처리")
            return self._neutral_result(asset_type, symbol, market, data_source="not_applicable")

        # 2) 상대평가 계산 (지표별로 독립적으로 시도)
        per_score = _relative_score(data.get("per"), data.get("market_per"), higher_is_better=False)
        pbr_score = _relative_score(data.get("pbr"), data.get("market_pbr"), higher_is_better=False)
        dividend_score = _relative_score(
            data.get("dividend_yield"), data.get("market_dividend_yield"), higher_is_better=True
        )

        components = {
            "per": (per_score, _WEIGHT_PER),
            "pbr": (pbr_score, _WEIGHT_PBR),
            "dividend": (dividend_score, _WEIGHT_DIVIDEND),
        }
        available = {k: (s, w) for k, (s, w) in components.items() if s is not None}

        data_quality = round(100 * len(available) / len(components), 1)

        if not available:
            logger.warning(f"⚠️  {symbol or market or '종목'}: 상대평가 가능한 지표 없음 (시장 기준값 누락) → 중립 처리")
            return self._neutral_result(asset_type, symbol, market, data_source="insufficient_data",
                                         data_quality=data_quality)

        return {
            "applicable": True,
            "asset_type": asset_type,
            "symbol": symbol,
            "market": market,
            "data_source": "relative",
            "data_quality": data_quality,
            "per": data.get("per"),
            "market_per": data.get("market_per"),
            "per_relative_score": per_score,
            "pbr": data.get("pbr"),
            "market_pbr": data.get("market_pbr"),
            "pbr_relative_score": pbr_score,
            "dividend_yield": data.get("dividend_yield"),
            "market_dividend_yield": data.get("market_dividend_yield"),
            "dividend_relative_score": dividend_score,
            "_available_components": available,  # get_score()에서만 사용, 외부 계약 아님
        }

    def get_score(self, analysis_result: Dict[str, Any]) -> float:
        """종합 점수 (계산 가능했던 지표만으로 가중평균 재정규화)"""
        if not analysis_result.get("applicable", True):
            return 50.0

        available = analysis_result.get("_available_components")
        if not available:
            return 50.0

        total_weight = sum(w for _, w in available.values())
        if total_weight <= 0:
            return 50.0

        weighted_sum = sum(score * w for score, w in available.values())
        score = weighted_sum / total_weight
        return max(0.0, min(100.0, score))

    @staticmethod
    def _neutral_result(asset_type: str, symbol: str, market: str, data_source: str,
                         data_quality: float = 0.0) -> Dict[str, Any]:
        """밸류에이션 미적용/데이터 부족 시 공통 중립 결과"""
        return {
            "applicable": False,
            "asset_type": asset_type,
            "symbol": symbol,
            "market": market,
            "data_source": data_source,
            "data_quality": data_quality,
            "per": None,
            "market_per": None,
            "per_relative_score": None,
            "pbr": None,
            "market_pbr": None,
            "pbr_relative_score": None,
            "dividend_yield": None,
            "market_dividend_yield": None,
            "dividend_relative_score": None,
            "_available_components": {},
        }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    analyzer = ValuationAnalyzer()

    print("=" * 80)
    print("【테스트 1】저평가 종목 - PER/PBR이 시장보다 낮고 배당은 시장보다 높음")
    print("=" * 80)
    data_undervalued = {
        "symbol": "005930", "market": "KOSPI", "asset_type": "stock",
        "per": 15.2, "market_per": 18.4,
        "pbr": 1.40, "market_pbr": 1.72,
        "dividend_yield": 2.50, "market_dividend_yield": 2.05,
    }
    result = analyzer.run(data_undervalued)
    print(f"기본분석 점수: {result.get('score', 0):.1f}/100 "
          f"(data_quality={result['details'].get('data_quality')}%)")

    print("\n" + "=" * 80)
    print("【테스트 2】고평가 종목 - PER/PBR이 시장보다 높고 배당은 시장보다 낮음")
    print("=" * 80)
    data_overvalued = {
        "symbol": "247540", "market": "KOSDAQ", "asset_type": "stock",
        "per": 40.0, "market_per": 27.8,
        "pbr": 4.50, "market_pbr": 2.31,
        "dividend_yield": 0.10, "market_dividend_yield": 0.82,
    }
    result2 = analyzer.run(data_overvalued)
    print(f"기본분석 점수: {result2.get('score', 0):.1f}/100 "
          f"(data_quality={result2['details'].get('data_quality')}%)")

    print("\n" + "=" * 80)
    print("【테스트 3】시장 기준값 없음 - 데이터 부족으로 중립 처리")
    print("=" * 80)
    data_no_market = {"symbol": "005930", "per": 15.2, "pbr": 1.4}
    result3 = analyzer.run(data_no_market)
    print(f"기본분석 점수: {result3.get('score', 0):.1f}/100 "
          f"(data_source={result3['details'].get('data_source')}, "
          f"data_quality={result3['details'].get('data_quality')}%)")

    print("\n" + "=" * 80)
    print("【테스트 4】코인 자산 - PER/PBR 밸류에이션 미적용 → 중립 처리")
    print("=" * 80)
    data_coin = {"symbol": "BTC", "asset_type": "coin"}
    result4 = analyzer.run(data_coin)
    print(f"기본분석 점수: {result4.get('score', 0):.1f}/100 "
          f"(applicable={result4['details'].get('applicable')})")
