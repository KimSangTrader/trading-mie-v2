"""
특정 Sector(기본값: Transportation)에 속한 전종목이 최신 계층형 랭킹 배치에서
실제로 몇 위(overall_rank)에 있는지, 그리고 각 컴포넌트 점수(market/sector/
theme/stock/final)가 얼마인지 그대로 보여주는 조회 전용 스크립트.

show_today_candidates.py는 "상위 N위까지"만 보여주기 때문에, Transportation처럼
sector_score는 기준선(65)을 넘겨도 종목 수가 적어(전체 시장에 2종목뿐) top-30
안에 아예 안 들어올 수 있는 sector는 확인이 안 된다. 이 스크립트는 순위 제한 없이
"그 Sector에 속한 종목 전부"를 뽑아서 실제 overall_rank와 컴포넌트별 점수를 보여줘,
"sector_score는 높은데 왜 후보에 안 뜨는지"를 stock_score(개별 종목 기술적/수급/
밸류에이션+Sector상대강도) 문제인지 아니면 다른 이유인지 구분할 수 있게 한다.

DB에 아무것도 쓰지 않는다(읽기 전용) - show_today_candidates.py와 동일한 위치/성격.

사용법:
    python3 check_sector_candidates.py                  # 기본값: Transportation
    python3 check_sector_candidates.py Nuclear           # Theme 이름을 넣으면 자동으로
                                                          #   primary_theme 기준 조회로 전환
    python3 check_sector_candidates.py Transportation --theme   # Sector 이름이어도
                                                          #   강제로 theme 기준 조회
"""
import sys

from config.database import SessionLocal
from db.models import StockHierarchicalScore
from market_intelligence.trade_execution.config import DEFAULT_CONFIG


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    by_theme = "--theme" in sys.argv[1:]
    name = args[0] if args else "Transportation"

    session = SessionLocal()
    try:
        latest_ts_row = session.query(StockHierarchicalScore.timestamp) \
            .order_by(StockHierarchicalScore.timestamp.desc()).first()
        if not latest_ts_row:
            print("stock_hierarchical_scores 테이블에 데이터가 없습니다.")
            return
        latest_ts = latest_ts_row[0]

        q = session.query(StockHierarchicalScore).filter(
            StockHierarchicalScore.timestamp == latest_ts
        )
        if by_theme:
            q = q.filter(StockHierarchicalScore.primary_theme == name)
        else:
            q = q.filter(StockHierarchicalScore.sector == name)

        rows = q.order_by(StockHierarchicalScore.overall_rank.asc()).all()

        total_in_batch = session.query(StockHierarchicalScore).filter(
            StockHierarchicalScore.timestamp == latest_ts
        ).count()

        print("=" * 100)
        label = "Theme" if by_theme else "Sector"
        print(f"계층형 랭킹 최신 배치: {latest_ts} | {label}='{name}' 소속 종목 전체")
        print(f"이 배치 전체 종목 수: {total_in_batch} | "
              f"후보로 채택되는 상위 순위: config.total_candidates={DEFAULT_CONFIG.total_candidates}위까지")
        print(f"진입 기준선: final_score>={DEFAULT_CONFIG.min_final_score}, "
              f"sector_score>={DEFAULT_CONFIG.min_sector_score}, "
              f"theme_score>={DEFAULT_CONFIG.min_theme_score}")
        print("=" * 100)

        if not rows:
            print(f"'{name}'에 해당하는 종목이 이 배치에 없습니다 (매핑 자체가 없거나 이름 철자 확인 필요).")
            return

        header = f"{'순위':>5} {'종목코드':<8} {'market':>7} {'sector':>7} {'theme':>7} {'stock':>7} {'final':>7}  top30내?"
        print(header)
        print("-" * 100)

        def _fmt(v):
            return f"{v:.1f}" if v is not None else "  -  "

        for r in rows:
            in_top = "✅" if r.overall_rank is not None and r.overall_rank <= DEFAULT_CONFIG.total_candidates else ""
            print(f"{r.overall_rank!s:>5} {r.ticker:<8} "
                  f"{_fmt(float(r.market_score) if r.market_score is not None else None):>7} "
                  f"{_fmt(float(r.sector_score) if r.sector_score is not None else None):>7} "
                  f"{_fmt(float(r.theme_score) if r.theme_score is not None else None):>7} "
                  f"{_fmt(float(r.stock_score) if r.stock_score is not None else None):>7} "
                  f"{_fmt(float(r.final_score) if r.final_score is not None else None):>7}  {in_top}")

        print("-" * 100)
        best_rank = min((r.overall_rank for r in rows if r.overall_rank is not None), default=None)
        print(f"'{name}' 소속 중 최고 순위: {best_rank}위 / 전체 {total_in_batch}종목 "
              f"(top {DEFAULT_CONFIG.total_candidates} 진입 여부: "
              f"{'예' if best_rank is not None and best_rank <= DEFAULT_CONFIG.total_candidates else '아니오'})")

    finally:
        session.close()


if __name__ == "__main__":
    main()
