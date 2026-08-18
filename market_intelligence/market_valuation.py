"""
MarketValuation - 시장별(KOSPI/KOSDAQ) PER/PBR/배당수익률 중앙값 계산 (Phase 5-4)

================================================================================
【변경 이력】
================================================================================
【2026-08-14】최초 생성 (Phase 5 방향 보고서 반영)
- 배경: ValuationAnalyzer를 절대값 점수(100 - per*3)에서 시장 대비 상대평가로
  바꾸려면, "시장 기준값(중앙값)"이 먼저 필요함
- 설계: 이 모듈은 API를 호출하지 않는 순수 계산 모듈이다.
  종목별 PER/PBR/배당 레코드 리스트(어디서 모았는지는 관여하지 않음 - 감시
  종목 리스트든, KOSPI/KOSDAQ 전체 종목이든 호출부가 결정)를 받아
  시장(KOSPI/KOSDAQ)별로 나눠 중앙값을 계산한다.
- 중요: KOSPI와 KOSDAQ은 절대 하나의 평균/중앙값으로 합치지 않는다
  (Phase 5 방향 보고서 8번 항목).
- 향후: 종목마스터 + ValuationCollector(Phase 5-2/5-3)가 만들어지면,
  그 결과 레코드를 이 모듈에 그대로 넣기만 하면 된다 (인터페이스 변경 없음).
================================================================================
"""

import statistics
from typing import Any, Dict, Iterable, Optional

# 이 모듈이 인식하는 시장 구분 (그 외 값은 별도 그룹으로 보존하되 경고 없이 통과)
KOSPI = "KOSPI"
KOSDAQ = "KOSDAQ"


def _median_of(values: Iterable[Optional[float]]) -> Optional[float]:
    """None/0 이하 값(비정상 PER/PBR 등)을 제외하고 중앙값 계산. 유효값 없으면 None."""
    clean = [v for v in values if isinstance(v, (int, float)) and v > 0]
    if not clean:
        return None
    return statistics.median(clean)


class MarketValuation:
    """
    시장(KOSPI/KOSDAQ)별 PER/PBR/배당수익률 중앙값 계산기

    입력 레코드 형식 (Phase 5 방향 보고서 7번 항목과 동일):
        {
            "symbol": "005930",
            "market": "KOSPI",       # "KOSPI" | "KOSDAQ"
            "per": 15.2,
            "pbr": 1.85,
            "dividend_yield": 1.72,
        }
    """

    @staticmethod
    def calculate_medians(stock_records: Iterable[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        """
        시장별 PER/PBR/배당수익률 중앙값 계산

        Returns:
            {
                "KOSPI": {"per_median": 18.4, "pbr_median": 1.72,
                          "dividend_median": 2.05, "sample_size": 812},
                "KOSDAQ": {...},
            }
            해당 시장의 유효 데이터가 하나도 없으면 그 시장 자체가 결과에서 빠진다.
        """
        grouped: Dict[str, Dict[str, list]] = {}

        for record in stock_records:
            market = record.get("market")
            if not market:
                continue
            bucket = grouped.setdefault(market, {"per": [], "pbr": [], "dividend_yield": []})
            bucket["per"].append(record.get("per"))
            bucket["pbr"].append(record.get("pbr"))
            bucket["dividend_yield"].append(record.get("dividend_yield"))

        result: Dict[str, Dict[str, Any]] = {}
        for market, bucket in grouped.items():
            per_median = _median_of(bucket["per"])
            pbr_median = _median_of(bucket["pbr"])
            dividend_median = _median_of(bucket["dividend_yield"])

            # 시장 기준값이 하나도 계산되지 않으면(전부 결측) 이 시장은 제외
            if per_median is None and pbr_median is None and dividend_median is None:
                continue

            result[market] = {
                "per_median": per_median,
                "pbr_median": pbr_median,
                "dividend_median": dividend_median,
                "sample_size": len(bucket["per"]),
            }

        return result

    @staticmethod
    def get_market_baseline(medians: Dict[str, Dict[str, Any]], market: str) -> Dict[str, Optional[float]]:
        """
        특정 시장의 기준값만 꺼내는 헬퍼 (ValuationAnalyzer 입력용 market_per/market_pbr/
        market_dividend_yield 형태로 변환)
        """
        m = medians.get(market, {})
        return {
            "market_per": m.get("per_median"),
            "market_pbr": m.get("pbr_median"),
            "market_dividend_yield": m.get("dividend_median"),
        }


if __name__ == "__main__":
    # 간단한 사용 예시 (실데이터 없이 로직 확인용)
    sample_records = [
        {"symbol": "005930", "market": KOSPI, "per": 15.2, "pbr": 1.85, "dividend_yield": 1.72},
        {"symbol": "000660", "market": KOSPI, "per": 21.6, "pbr": 2.10, "dividend_yield": 0.90},
        {"symbol": "005380", "market": KOSPI, "per": 18.4, "pbr": 1.72, "dividend_yield": 2.05},
        {"symbol": "247540", "market": KOSDAQ, "per": 32.1, "pbr": 3.40, "dividend_yield": 0.10},
        {"symbol": "091990", "market": KOSDAQ, "per": 27.8, "pbr": 2.31, "dividend_yield": 0.82},
    ]

    medians = MarketValuation.calculate_medians(sample_records)
    print("시장별 중앙값:")
    for market, stats in medians.items():
        print(f"  {market}: PER={stats['per_median']:.1f}, PBR={stats['pbr_median']:.2f}, "
              f"배당={stats['dividend_median']:.2f}% (표본 {stats['sample_size']}종목)")

    baseline = MarketValuation.get_market_baseline(medians, KOSPI)
    print(f"\nKOSPI 기준값 (ValuationAnalyzer 입력용): {baseline}")
