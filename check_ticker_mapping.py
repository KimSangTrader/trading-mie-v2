"""
특정 종목코드들의 Sector/Theme 매핑 원본 상태(needs_review 여부 포함)를 그대로
보여주는 조회 전용 스크립트.

배경(2026-09-15): trade_execution.log/error.log를 보면 그날 final_score 상위
후보(예: 82점대) 여러 개가 "Sector=결측 Theme=결측"으로 나오고, entry_filter가
sector_score가 None이면 무조건 WEAK_SECTOR로 처리한다(값이 낮아서가 아니라
아예 없어서). 이게 실제로 "Other"/needs_review=True로 걸려 SectorAnalyzer가
애초에 sector_score를 안 주는 종목들(2026-09-08에 확인한 819종목/약 30%)인지,
아니면 sector_theme_importer의 매핑 자체가 없는 종목인지 구분하기 위한
1회성 점검 스크립트. DB에 아무것도 쓰지 않는다.

사용법:
    python3 check_ticker_mapping.py 005160 066360 285800 019680 003200 115570
"""
import sys

from config.database import SessionLocal
from db.models import StockSectorMapping, StockThemeMapping


def main():
    tickers = sys.argv[1:]
    if not tickers:
        print("사용법: python3 check_ticker_mapping.py <종목코드1> <종목코드2> ...")
        return

    session = SessionLocal()
    try:
        print("=" * 100)
        print(f"{'종목코드':<10} {'Sector':<22} {'needs_review':<14} {'Theme(primary)':<20} {'비고'}")
        print("-" * 100)

        for ticker in tickers:
            sector_row = (
                session.query(StockSectorMapping)
                .filter(StockSectorMapping.ticker == ticker)
                .order_by(StockSectorMapping.timestamp.desc())
                .first()
            )
            theme_rows = (
                session.query(StockThemeMapping)
                .filter(StockThemeMapping.ticker == ticker)
                .order_by(StockThemeMapping.timestamp.desc())
                .all()
            )
            primary_theme = next((t.theme for t in theme_rows if t.is_primary), None)

            if sector_row is None:
                sector_str, review_str, note = "(매핑 없음)", "-", "stock_sector_mapping에 이 종목 행 자체가 없음"
            else:
                sector_str = sector_row.sector or "(sector 컬럼 NULL)"
                review_str = str(sector_row.needs_review)
                note = "needs_review=True -> SectorAnalyzer가 기본 설정상 제외" if sector_row.needs_review else ""

            theme_str = primary_theme or "(매핑 없음)"

            print(f"{ticker:<10} {sector_str:<22} {review_str:<14} {theme_str:<20} {note}")

        print("=" * 100)
    finally:
        session.close()


if __name__ == "__main__":
    main()
