"""
1회성 마이그레이션: stock_valuation 테이블에 Sector 밸류에이션 중앙값 컬럼 추가
(Phase 5-19: Sector별 PER/PBR/배당 중앙값 계산)

================================================================================
【변경 이력】
================================================================================
【2026-08-24】최초 생성
- 배경: stock_valuation 테이블이 이미 실제 RDS에 존재하고 데이터가 쌓여 있어서,
  create_tables.py(Base.metadata.create_all())로는 새 컬럼이 추가되지 않는다
  (create_all은 "없는 테이블"만 만들고 기존 테이블은 건드리지 않음 - Phase 5
  라이브 검증 때 stock_price_history/stock_hierarchical_scores 신규 테이블을
  만들 때도 이미 확인된 동작). 이 프로젝트엔 별도 마이그레이션 도구(alembic 등)가
  없으므로, db/models.py의 StockValuation에 추가한 컬럼과 짝을 맞추는 단순
  ALTER TABLE 스크립트를 직접 만든다.
- ADD COLUMN IF NOT EXISTS를 써서 여러 번 실행해도 안전(idempotent)하다 -
  이미 컬럼이 있으면 그냥 건너뛴다.
- 새 컬럼은 전부 nullable이라 기존 행에는 NULL로 채워지고, 기존 컬럼(market_per
  등)은 전혀 건드리지 않는다 - 기존 데이터/조회에 영향 없음.
================================================================================
"""

from sqlalchemy import text

from config.database import engine

_STATEMENTS = [
    "ALTER TABLE stock_valuation ADD COLUMN IF NOT EXISTS sector VARCHAR(50)",
    "ALTER TABLE stock_valuation ADD COLUMN IF NOT EXISTS sector_per_median DECIMAL(10, 2)",
    "ALTER TABLE stock_valuation ADD COLUMN IF NOT EXISTS sector_pbr_median DECIMAL(10, 2)",
    "ALTER TABLE stock_valuation ADD COLUMN IF NOT EXISTS sector_dividend_median DECIMAL(5, 2)",
]

if __name__ == "__main__":
    print("stock_valuation 테이블에 Sector 밸류에이션 컬럼 추가 중...")
    try:
        with engine.begin() as conn:
            for stmt in _STATEMENTS:
                print(f"  실행: {stmt}")
                conn.execute(text(stmt))
        print("✅ 마이그레이션 완료 (sector, sector_per_median, sector_pbr_median, "
              "sector_dividend_median 컬럼 추가/확인됨)")
    except Exception as e:
        print(f"❌ Error: {e}")
