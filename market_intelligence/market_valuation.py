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

【2026-08-24】Sector별 중앙값 지원 추가 (docs/hierarchical_scoring_plan.md
백로그 2번, StockAnalyzer가 이미 "알려진 한계 2"로 문서화해 둔 갭 해소)
- 배경: `market_intelligence/analyzers/stock_analyzer.py`는 처음부터
  `data["sector_per_median"]` 등이 주어지면 그것을 우선 쓰고, 없으면
  `market_per`(시장 전체 중앙값)로 자동 대체하도록 설계돼 있었다(Phase 3).
  즉 소비 측(StockAnalyzer) 계약은 이미 있었고, 이 모듈(생산 측)이 실제
  Sector 중앙값을 계산해 채워주지 않고 있었을 뿐이다.
- `calculate_medians()`에 `group_by` 파라미터 추가(기본값 "market", 하위 호환
  유지) - "market" 대신 "sector"로 그룹핑하면 그대로 Sector별 중앙값이 된다.
  KOSPI/KOSDAQ을 절대 합치지 않는 원칙과 동일하게, Sector도 서로 다른 카테고리를
  하나로 합치지 않는다(그룹 키가 다르면 별도 버킷).
- 각 지표(per/pbr/dividend)별 "유효 표본 수"(0 이하/None 제외하고 실제 중앙값
  계산에 쓰인 개수)를 `sample_size`와 별개로 `{metric}_valid_count`에 노출했다.
  기존 `sample_size`는 하위 호환을 위해 "그룹에 배정된 전체 레코드 수" 의미
  그대로 유지(값 변경 없음) - Sector처럼 그룹이 작을 수 있는 경우 "몇 종목이
  그룹에 속하는가"와 "그중 실제로 PER 값을 가진 게 몇 개인가"는 다를 수 있어서,
  신뢰도 판단에는 후자(valid_count)가 필요하다.
- `build_relative_baseline()` 신규: 종목 하나의 market/sector를 받아 PER/PBR/
  배당 세 지표 각각 독립적으로 "Sector 표본이 충분하면 Sector 중앙값, 아니면
  시장 전체 중앙값"을 고른다(ValuationAnalyzer가 이미 쓰는 "결측 시 제외 후
  재정규화"와 동일한 "조용히 틀린 값 주지 않는다" 원칙을 한 단계 앞에서도
  지킴). 표본 최소 기준(`_MIN_SECTOR_VALID_SAMPLES`)은 `_MARKET_REGIME_SPAN_PCT`/
  `_SUPPLY_DEMAND_SPAN_RATIO`와 같은 성격의 잠정값 - 실측 Sector별 종목 분포를
  보고 조정 필요할 수 있음.
================================================================================
"""

import statistics
from typing import Any, Dict, Iterable, Optional, Tuple

# 이 모듈이 인식하는 시장 구분 (그 외 값은 별도 그룹으로 보존하되 경고 없이 통과)
KOSPI = "KOSPI"
KOSDAQ = "KOSDAQ"

# Sector 중앙값을 신뢰하고 쓸 최소 유효 표본 수(지표별 독립 판정) - 잠정값.
# 이보다 적으면 그 지표만 시장 전체 중앙값으로 대체한다.
_MIN_SECTOR_VALID_SAMPLES = 5


def _median_of(values: Iterable[Optional[float]]) -> Tuple[Optional[float], int]:
    """None/0 이하 값(비정상 PER/PBR 등)을 제외하고 중앙값 계산.
    반환: (중앙값 또는 유효값 없으면 None, 유효값 개수)"""
    clean = [v for v in values if isinstance(v, (int, float)) and v > 0]
    if not clean:
        return None, 0
    return statistics.median(clean), len(clean)


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
    def calculate_medians(
        stock_records: Iterable[Dict[str, Any]], group_by: str = "market"
    ) -> Dict[str, Dict[str, Any]]:
        """
        그룹별(기본: 시장 KOSPI/KOSDAQ, group_by="sector"면 Sector별) PER/PBR/
        배당수익률 중앙값 계산

        Returns:
            {
                "KOSPI": {"per_median": 18.4, "pbr_median": 1.72,
                          "dividend_median": 2.05, "sample_size": 812,
                          "per_valid_count": 780, "pbr_valid_count": 795,
                          "dividend_valid_count": 640},
                "KOSDAQ": {...},
            }
            해당 그룹의 유효 데이터가 하나도 없으면 그 그룹 자체가 결과에서 빠진다.
            group_by 필드 값이 없는 레코드는 건너뛴다.
        """
        grouped: Dict[str, Dict[str, list]] = {}

        for record in stock_records:
            group = record.get(group_by)
            if not group:
                continue
            bucket = grouped.setdefault(group, {"per": [], "pbr": [], "dividend_yield": []})
            bucket["per"].append(record.get("per"))
            bucket["pbr"].append(record.get("pbr"))
            bucket["dividend_yield"].append(record.get("dividend_yield"))

        result: Dict[str, Dict[str, Any]] = {}
        for group, bucket in grouped.items():
            per_median, per_valid_count = _median_of(bucket["per"])
            pbr_median, pbr_valid_count = _median_of(bucket["pbr"])
            dividend_median, dividend_valid_count = _median_of(bucket["dividend_yield"])

            # 기준값이 하나도 계산되지 않으면(전부 결측) 이 그룹은 제외
            if per_median is None and pbr_median is None and dividend_median is None:
                continue

            result[group] = {
                "per_median": per_median,
                "pbr_median": pbr_median,
                "dividend_median": dividend_median,
                "sample_size": len(bucket["per"]),
                "per_valid_count": per_valid_count,
                "pbr_valid_count": pbr_valid_count,
                "dividend_valid_count": dividend_valid_count,
            }

        return result

    @staticmethod
    def get_market_baseline(medians: Dict[str, Dict[str, Any]], market: str) -> Dict[str, Optional[float]]:
        """
        특정 그룹(시장 또는 Sector)의 기준값만 꺼내는 헬퍼 (ValuationAnalyzer 입력용
        market_per/market_pbr/market_dividend_yield 형태로 변환) - group_by가
        "sector"였던 medians에 대해 써도 키 이름(market_per 등)은 그대로다
        (ValuationAnalyzer 입력 계약이 원래 이 이름을 쓰기 때문 - 값의 출처가
        시장 전체 중앙값인지 Sector 중앙값인지는 호출부가 결정).
        """
        m = medians.get(market, {})
        return {
            "market_per": m.get("per_median"),
            "market_pbr": m.get("pbr_median"),
            "market_dividend_yield": m.get("dividend_median"),
        }

    @classmethod
    def get_reliable_sector_medians(
        cls,
        sector_medians: Dict[str, Dict[str, Any]],
        sector: Optional[str],
        min_sector_valid_samples: int = _MIN_SECTOR_VALID_SAMPLES,
    ) -> Dict[str, Optional[float]]:
        """
        종목의 Sector 중앙값 중 "믿고 써도 되는" 것만 지표별로 골라 돌려준다 -
        지표별 유효 표본 수(`*_valid_count`)가 `min_sector_valid_samples` 미만이면
        그 지표는 None으로 돌아온다. 시장 전체 중앙값으로 대체하지 않는다(순수하게
        "이 Sector 중앙값을 신뢰할 수 있는가"만 판단) - DB에 그대로 저장할
        sector_per_median 등의 값이자, build_relative_baseline()의 1차 후보이기도
        하다. 이 함수를 안 거치고 sector_medians[sector]를 직접 읽어서 저장하면
        표본이 1~2개뿐인 Sector의 "중앙값"(사실상 그 종목 자신의 값과 다름없음)이
        그대로 신뢰할 수 있는 기준값처럼 저장되는 함정이 있다(이 세션이 단위테스트로
        직접 잡은 버그 - valuation_pipeline.py 변경이력 참고).

        Returns:
            {"per_median":, "pbr_median":, "dividend_median":} - 표본 부족/Sector
            미상이면 해당 키는 None.
        """
        sector_stats = sector_medians.get(sector, {}) if sector else {}

        def _reliable(median_key: str, count_key: str) -> Optional[float]:
            val = sector_stats.get(median_key)
            count = sector_stats.get(count_key, 0)
            return val if (val is not None and count >= min_sector_valid_samples) else None

        return {
            "per_median": _reliable("per_median", "per_valid_count"),
            "pbr_median": _reliable("pbr_median", "pbr_valid_count"),
            "dividend_median": _reliable("dividend_median", "dividend_valid_count"),
        }

    @classmethod
    def build_relative_baseline(
        cls,
        sector_medians: Dict[str, Dict[str, Any]],
        market_medians: Dict[str, Dict[str, Any]],
        sector: Optional[str],
        market: Optional[str],
        min_sector_valid_samples: int = _MIN_SECTOR_VALID_SAMPLES,
    ) -> Tuple[Dict[str, Optional[float]], str]:
        """
        종목 하나의 PER/PBR/배당 상대평가 기준값을 만든다(문서 5-C절 "같은 Sector
        내 중앙값" 요구사항). PER/PBR/배당 세 지표를 각각 독립적으로 판단해서,
        Sector 중앙값이 있고 유효 표본이 `min_sector_valid_samples` 이상이면 그것을,
        아니면(Sector 미상/표본 부족/그 지표만 결측) 시장 전체 중앙값으로 대체한다.
        신뢰 가능 여부 판단은 get_reliable_sector_medians()에 위임한다(같은 기준을
        DB 저장 값과 여기서 각각 다시 구현하면 둘이 어긋날 위험이 있어 하나로 통일).

        Returns:
            (baseline, source)
            - baseline: ValuationAnalyzer 입력용 {"market_per":, "market_pbr":,
              "market_dividend_yield":} (지표별로 출처가 다를 수 있음)
            - source: "sector"(세 지표 모두 Sector 중앙값) | "market"(세 지표 모두
              시장 중앙값) | "mixed"(지표별로 다름) | "none"(셋 다 기준값 없음) -
              요약 표시용. 지표별 실제 출처가 필요하면 sector_medians/market_medians를
              직접 조회해서 재구성할 수 있다.
        """
        reliable_sector = cls.get_reliable_sector_medians(sector_medians, sector, min_sector_valid_samples)
        market_stats = market_medians.get(market, {}) if market else {}

        def _pick(median_key: str) -> Tuple[Optional[float], str]:
            s_val = reliable_sector.get(median_key)
            if s_val is not None:
                return s_val, "sector"
            m_val = market_stats.get(median_key)
            return m_val, ("market" if m_val is not None else "none")

        per_val, per_src = _pick("per_median")
        pbr_val, pbr_src = _pick("pbr_median")
        div_val, div_src = _pick("dividend_median")

        used_sources = {s for s in (per_src, pbr_src, div_src) if s != "none"}
        if used_sources == {"sector"}:
            overall_source = "sector"
        elif used_sources == {"market"}:
            overall_source = "market"
        elif not used_sources:
            overall_source = "none"
        else:
            overall_source = "mixed"

        baseline = {
            "market_per": per_val,
            "market_pbr": pbr_val,
            "market_dividend_yield": div_val,
        }
        return baseline, overall_source


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
