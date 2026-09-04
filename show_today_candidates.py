"""
오늘(최신 배치) 계층형 랭킹 후보 종목을 보기 좋게 출력하는 조회 전용 스크립트.

================================================================================
【변경 이력】
================================================================================
【2026-08-31】최초 생성
- 배경: 사용자가 "오늘 날짜의 분석 후 추천종목을 볼 수 있는 방법"을 물어봤는데,
  지금까지는 trade_execution_pipeline.py 실행 로그에서 "⏭️ {ticker}: ..." 줄로
  간접적으로만 확인 가능했다(그것도 진입 필터를 통과 못 한 종목만 사유가 남고,
  전체 후보 목록/점수를 한눈에 보는 방법은 없었음). main.py serve(평일 19:00 KST)가
  전날 밤 stock_hierarchical_scores 테이블에 저장해 둔 최신 배치를 그대로 조회만
  하는 읽기 전용 스크립트 - DB에 아무것도 쓰지 않고, KIS API도 호출하지 않는다
  (check_data.py 등 기존 리포지토리 루트의 1회성 점검 스크립트들과 같은 위치/성격).
- build_market_data_and_candidates()(trade_execution_pipeline.py)와 동일하게
  "최신 timestamp 배치 전체"를 가져오되, 그쪽은 상위 config.total_candidates개만
  후보로 쓰는 반면 이 스크립트는 인자로 몇 위까지 볼지 자유롭게 고를 수 있게 했다.
- entry_filter.DEFAULT_CONFIG의 min_final_score/min_sector_score/min_theme_score
  기준선도 같이 표시해서, 각 종목이 "왜 오늘 진입 후보가 됐는지/안 됐는지"를 갭
  판정(장중 실시간 데이터가 필요해 여기선 계산 안 함) 이전 단계까지는 한눈에
  가늠할 수 있게 했다 - 실제 진입 여부의 최종 판정은 여전히
  trade_execution_pipeline.py의 check_entry()(갭 포함) 몫이다.

사용법:
    python3 show_today_candidates.py            # 상위 30종목(기본, total_candidates와 동일)
    python3 show_today_candidates.py 50         # 상위 50종목
================================================================================
"""
import sys

from config.database import SessionLocal
from db.models import StockHierarchicalScore
from market_intelligence.trade_execution.config import DEFAULT_CONFIG


def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_CONFIG.total_candidates

    session = SessionLocal()
    try:
        latest_ts_row = session.query(StockHierarchicalScore.timestamp) \
            .order_by(StockHierarchicalScore.timestamp.desc()).first()
        if not latest_ts_row:
            print("stock_hierarchical_scores 테이블에 데이터가 없습니다 - "
                  "main.py serve의 일마감 분석이 아직 한 번도 안 돌았을 수 있습니다.")
            return

        latest_ts = latest_ts_row[0]
        rows = (
            session.query(StockHierarchicalScore)
            .filter(StockHierarchicalScore.timestamp == latest_ts)
            .order_by(StockHierarchicalScore.overall_rank.asc())
            .limit(limit)
            .all()
        )

        print("=" * 100)
        print(f"계층형 랭킹 최신 배치: {latest_ts} (KST 기준 시각 아님 - DB 저장 시각)")
        print(f"진입 기준선(참고용, 갭 판정 등 나머지 조건은 미포함): "
              f"final_score>={DEFAULT_CONFIG.min_final_score}, "
              f"sector_score>={DEFAULT_CONFIG.min_sector_score}, "
              f"theme_score>={DEFAULT_CONFIG.min_theme_score}")
        print("=" * 100)
        header = f"{'순위':>4} {'종목코드':<8} {'시장':<6} {'섹터':<12} {'테마':<14} " \
                 f"{'final':>7} {'sector':>7} {'theme':>7}  기준충족"
        print(header)
        print("-" * 100)

        for r in rows:
            final = float(r.final_score) if r.final_score is not None else None
            sector = float(r.sector_score) if r.sector_score is not None else None
            theme = float(r.theme_score) if r.theme_score is not None else None

            meets = (
                final is not None and final >= DEFAULT_CONFIG.min_final_score
                and sector is not None and sector >= DEFAULT_CONFIG.min_sector_score
                and theme is not None and theme >= DEFAULT_CONFIG.min_theme_score
            )
            mark = "✅" if meets else ""

            def _fmt(v):
                return f"{v:.1f}" if v is not None else "  -  "

            print(f"{r.overall_rank!s:>4} {r.ticker:<8} {r.market or '-':<6} "
                  f"{(r.sector or '-'):<12} {(r.primary_theme or '-'):<14} "
                  f"{_fmt(final):>7} {_fmt(sector):>7} {_fmt(theme):>7}  {mark}")

        print("-" * 100)
        qualifying = sum(
            1 for r in rows
            if r.final_score is not None and float(r.final_score) >= DEFAULT_CONFIG.min_final_score
            and r.sector_score is not None and float(r.sector_score) >= DEFAULT_CONFIG.min_sector_score
            and r.theme_score is not None and float(r.theme_score) >= DEFAULT_CONFIG.min_theme_score
        )
        print(f"총 {len(rows)}종목 표시, 점수 기준선 충족(✅): {qualifying}종목 "
              f"(갭 판정 등 나머지 조건은 trade_execution_pipeline.py 실행 로그에서 확인)")

    finally:
        session.close()


if __name__ == "__main__":
    main()
