"""
당일 공식 종가 일봉 수집 (2026-10-30 신규) - 평일 15:41 KST, 애프터마켓(16:00) 시작 전.

================================================================================
【변경 이력】
================================================================================
【2026-10-30】최초 생성
- 배경: 2026-09-14 KRX 애프터마켓(16:00~20:00 실시간 체결) 도입 후 KIS 일봉 API는 "당일" 행을
  20:00 마지막 체결가/애프터마켓 포함 거래량으로 주고, 다음날부터 공식 종가로 고쳐 준다.
  22:00 분석(main.py)이 저장한 당일 행이 그대로 DB에 남아 9/14 이후 종가가 공식 종가와
  ~80% 종목에서 달랐다(10/14·10/20·10/22 KRX CSV 대조). 장중 루프는 이 DB 일봉으로
  ATR20/10일 최저가/전일 종가(대체값)를 계산한다.
- 기본 모드(15:41 타이머): 15:30 종가 단일가 이후 ~ 16:00 애프터마켓 시작 전에 전 종목 당일
  행만 받아 저장한다(15:40~16:00 시간외 종가는 종가와 같은 가격이라 종가에 영향 없음).
  16:00(DEADLINE)이 되면 남은 종목은 수집하지 않고 멈춘다 - 그 종목들은 22:00 분석이 임시
  값으로 넣고 다음날 밤 공식 값으로 고쳐진다(price_history_pipeline update_existing).
  시작 시각이 이미 16:00 이후면 아무것도 쓰지 않는다. 수집률이 MIN_COVERAGE 미만이거나
  예외가 나면 텔레그램으로 알린다.
- --backfill N 모드: 최근 N일(오늘 제외) 행을 받아 기존 DB 행을 공식 값으로 덮어쓴다(1회성 보정).
- 수집 대상은 main.py 22:00 분석과 같은 최신 stock_valuation 배치 종목.

사용법:
    python -m market_intelligence.collectors.daily_close_collector              # 당일 공식 종가 수집
    python -m market_intelligence.collectors.daily_close_collector --backfill 60  # 과거 보정(오늘 제외)
================================================================================
"""
import argparse
import logging
import time
from datetime import datetime, time as dtime
from typing import Any, Callable, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

KST = ZoneInfo("Asia/Seoul")
DEADLINE = dtime(15, 59, 30)   # 이 시각(KST)부터는 당일 행을 쓰지 않는다 - 16:00 애프터마켓 시작 전 여유
MIN_COVERAGE = 0.90            # 당일 행 확보 비율이 이보다 낮으면 알림
RATE_LIMIT_SEC = 0.1           # 종목당 호출 간격 - 15:41 시작 기준 16:00 전에 끝나도록(약 2,600종목)


def load_universe(session) -> List[Tuple[str, Optional[str]]]:
    """main.py 22:00 분석과 같은 대상: 최신 stock_valuation 배치의 (종목코드, 시장)."""
    from sqlalchemy import func
    from db.models import StockValuation

    latest_ts = session.query(func.max(StockValuation.timestamp)).scalar()
    if latest_ts is None:
        return []
    rows = (
        session.query(StockValuation.ticker, StockValuation.market)
        .filter(StockValuation.timestamp == latest_ts)
        .order_by(StockValuation.ticker)
        .all()
    )
    return [(t, m) for t, m in rows]


def collect_rows(
    kis_client,
    universe: List[Tuple[str, Optional[str]]],
    include: Callable[[str], bool],
    days: int,
    deadline: Optional[dtime] = None,
    now_fn: Callable[[], datetime] = lambda: datetime.now(KST),
    rate_limit_sec: float = RATE_LIMIT_SEC,
) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    """종목마다 일봉을 받아 include(date)인 행만 모은다. deadline(KST)이 되면 멈춘다."""
    from data.price_history_collector import chart_to_price_rows

    rows: List[Dict[str, Any]] = []
    stats = {"requested": 0, "with_rows": 0, "stopped_at_deadline": 0}
    for ticker, market in universe:
        if deadline is not None and now_fn().time() >= deadline:
            stats["stopped_at_deadline"] = len(universe) - stats["requested"]
            logger.warning(f"⏰ {deadline:%H:%M:%S} KST 도달 - 남은 {stats['stopped_at_deadline']}종목은 수집하지 않음")
            break
        stats["requested"] += 1
        chart = kis_client.get_stock_daily_chart(ticker, days=days)
        picked = [r for r in chart_to_price_rows(ticker, market, chart) if include(r["date"])] if chart else []
        if picked:
            stats["with_rows"] += 1
            rows.extend(picked)
        time.sleep(rate_limit_sec)
    return rows, stats


def run_close_snapshot(session, kis_client, notifier=None, now_fn: Callable[[], datetime] = lambda: datetime.now(KST),
                       rate_limit_sec: float = RATE_LIMIT_SEC) -> Dict[str, Any]:
    """당일 공식 종가 수집(15:41). 16:00 이후 시작이면 쓰지 않는다."""
    from data.krx_calendar import is_krx_trading_day
    from market_intelligence.collectors.price_history_pipeline import run_full_price_history_pipeline

    now = now_fn()
    today = now.strftime("%Y%m%d")
    if not is_krx_trading_day(now.date()):
        logger.info(f"ℹ️  {today} KRX 휴장일 - 수집 없음")
        return {"status": "holiday"}
    if now.time() >= DEADLINE:
        logger.warning(f"⚠️  {now:%H:%M} KST - 애프터마켓 시작 이후라 당일 공식 종가를 받을 수 없어 수집하지 않음")
        if notifier is not None:
            notifier.send(f"⚠️ 당일 공식 종가 수집 건너뜀({now:%H:%M} KST 시작) - 오늘 일봉은 22:00 임시 값, 내일 밤 자동 보정",
                          key="daily_close_late")
        return {"status": "too_late"}

    universe = load_universe(session)
    rows, stats = collect_rows(kis_client, universe, include=lambda d: d == today, days=5,
                               deadline=DEADLINE, now_fn=now_fn, rate_limit_sec=rate_limit_sec)
    saved = run_full_price_history_pipeline(session, records=rows, update_existing=True) if rows else \
        {"rows_saved": 0, "rows_updated": 0}
    coverage = stats["with_rows"] / len(universe) if universe else 0.0
    logger.info(
        f"✅ {today} 공식 종가 수집: {stats['with_rows']}/{len(universe)}종목 ({coverage:.1%}), "
        f"신규 {saved['rows_saved']}행, 갱신 {saved['rows_updated']}행, 마감시각 미수집 {stats['stopped_at_deadline']}종목"
    )
    if notifier is not None and coverage < MIN_COVERAGE:
        notifier.send(
            f"⚠️ 당일 공식 종가 수집률 낮음: {stats['with_rows']}/{len(universe)}종목 ({coverage:.0%})\n"
            f"16:00 마감으로 못 받은 종목 {stats['stopped_at_deadline']}개 - 22:00 임시 값, 내일 밤 자동 보정",
            key="daily_close_coverage",
        )
    return {"status": "ok", "universe": len(universe), **stats, **saved, "coverage": coverage}


def run_backfill(session, kis_client, days: int, now_fn: Callable[[], datetime] = lambda: datetime.now(KST),
                 rate_limit_sec: float = 0.15) -> Dict[str, Any]:
    """최근 days일(오늘 제외)을 다시 받아 기존 DB 행을 공식 값으로 덮어쓴다."""
    from market_intelligence.collectors.price_history_pipeline import run_full_price_history_pipeline

    today = now_fn().strftime("%Y%m%d")
    universe = load_universe(session)
    rows, stats = collect_rows(kis_client, universe, include=lambda d: d < today, days=days,
                               rate_limit_sec=rate_limit_sec)
    saved = run_full_price_history_pipeline(session, records=rows, update_existing=True) if rows else \
        {"rows_saved": 0, "rows_updated": 0}
    logger.info(f"✅ 백필 완료: {stats['with_rows']}/{len(universe)}종목, 신규 {saved['rows_saved']}행, 갱신 {saved['rows_updated']}행")
    return {"universe": len(universe), **stats, **saved}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
    parser = argparse.ArgumentParser(description="당일 공식 종가 일봉 수집 / 과거 일봉 보정")
    parser.add_argument("--backfill", type=int, metavar="DAYS", help="최근 DAYS일(오늘 제외)을 공식 값으로 덮어쓰기")
    args = parser.parse_args()

    from config.database import SessionLocal
    from data.kis_client import KISClient
    from market_intelligence.utils.notifier import TelegramNotifier

    client = KISClient()  # 시세 조회 전용 - main.py와 같은 전역 ENVIRONMENT
    notifier = TelegramNotifier(prefix="[MIE 데이터] ")
    session = SessionLocal()
    try:
        if args.backfill:
            print(run_backfill(session, client, args.backfill))
        else:
            print(run_close_snapshot(session, client, notifier=notifier))
    except Exception as e:
        logger.exception("❌ 일봉 수집 중 예외")
        notifier.send(f"🚨 일봉 수집 작업 실패\n{type(e).__name__}: {e}", key="daily_close_crash")
        raise
    finally:
        session.close()
