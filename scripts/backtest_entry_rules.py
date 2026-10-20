"""
진입 규칙(섹터 기준/테마 미매핑 처리) 일봉 백테스트 - 조회 전용(RDS는 읽기만, 쓰기 없음).

================================================================================
【변경 이력】
================================================================================
【2026-10-20】최초 생성
- 배경: 10/12 이후 Sector>=65 & Theme>=60을 동시에 만족하는 종목이 0개라 장중 루프가
  진입을 한 건도 못 했다. 사용자가 (A) 테마 미매핑 종목은 Theme 조건 생략,
  (B) Sector 기준 65 -> 60 두 가지의 백테스트를 요청.
- 방식: 실제 매매 파이프라인 함수(run_exit_pipeline/run_pyramiding_pipeline/
  run_entry_pipeline)를 SQLite 메모리 DB + dry_run으로 그대로 돌린다 - 판정/사이징/
  분산/리스크 클리핑 로직을 다시 구현하지 않으므로 라이브와 같은 규칙이 적용된다.
  시세는 RDS stock_price_history 일봉, 랭킹은 stock_hierarchical_scores에서
  거래일 D 이전 마지막 배치(라이브와 동일하게 전날 밤 분석 결과)를 쓴다.
- 장중 1분 루프를 일봉으로 근사(한계 - 결과 해석 시 주의):
  * 손절/긴급청산: 시가가 트리거 이하면 시가 체결, 아니면 저가가 닿으면 트리거 가격 체결.
    (라이브의 "얕은 이탈 3회 연속 확인"으로 걸러지는 휩쏘는 반영 못 함 - 보수적)
  * 신규진입: 시가와 종가 두 시점에서만 검토(라이브는 1분마다 갭을 재평가).
  * 청산(랭킹붕괴/부분익절/10일저가)·피라미딩: 종가 기준 1회.
  * 비용: 매수 0.015%, 매도 0.015%+거래세 0.20%.

사용법:
    venv/bin/python scripts/backtest_entry_rules.py [--start 2026-09-09] [--end 2026-10-19] [--trades]
================================================================================
"""
import argparse
import logging
import os
import sys
from collections import defaultdict
from dataclasses import replace
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db.models import TradePosition, TradingHistory
from market_intelligence.trade_execution import trade_execution_pipeline as pipeline
from market_intelligence.trade_execution.atr import compute_atr
from market_intelligence.trade_execution.config import DEFAULT_CONFIG, DEFAULT_EXIT_CONFIG
from market_intelligence.trade_execution.exit_engine import compute_lowest_low

INITIAL_CASH = 10_000_000.0
BUY_COST = 0.00015
SELL_COST = 0.00015 + 0.0020

SCENARIOS = [
    ("기존 (섹터65, 테마없음=차단)", dict(min_sector_score=65.0, skip_theme_check_if_unmapped=False)),
    ("A: 섹터65, 테마없음=섹터만", dict(min_sector_score=65.0, skip_theme_check_if_unmapped=True)),
    ("B: 섹터60, 테마없음=차단", dict(min_sector_score=60.0, skip_theme_check_if_unmapped=False)),
    ("A+B: 섹터60, 테마없음=섹터만", dict(min_sector_score=60.0, skip_theme_check_if_unmapped=True)),
]


def _f(v):
    return float(v) if v is not None else None


def load_data(start: str, end: str):
    """RDS에서 랭킹 배치(거래일별 직전 배치)와 일봉을 읽어 메모리에 올린다."""
    from config.database import SessionLocal

    rds = SessionLocal()
    try:
        days = [r[0] for r in rds.execute(text(
            "select distinct trade_date from stock_price_history where trade_date between :s and :e order by 1"),
            {"s": start.replace("-", ""), "e": end.replace("-", "")})]
        batch_ts = [r[0] for r in rds.execute(text(
            "select max(timestamp) from stock_hierarchical_scores group by date(timestamp) order by 1"))]

        batches = {}  # trade_date -> {ticker: row}
        cache = {}
        for d in days:
            day = date(int(d[:4]), int(d[4:6]), int(d[6:]))
            prior = [ts for ts in batch_ts if ts.date() < day]
            if not prior:
                continue
            ts = prior[-1]
            if ts not in cache:
                rows = rds.execute(text(
                    "select ticker, market, sector, primary_theme, sector_score, theme_score, final_score, overall_rank "
                    "from stock_hierarchical_scores where timestamp = :ts"), {"ts": ts}).fetchall()
                cache[ts] = {r.ticker: {
                    "ticker": r.ticker, "market": r.market, "sector": r.sector, "primary_theme": r.primary_theme,
                    "sector_score": _f(r.sector_score), "theme_score": _f(r.theme_score),
                    "final_score": _f(r.final_score), "overall_rank": r.overall_rank,
                } for r in rows}
            batches[d] = cache[ts]

        tickers = set()
        for b in batches.values():
            tickers |= {t for t, r in b.items() if r["overall_rank"] is not None and r["overall_rank"] <= 60}
        prices = defaultdict(dict)  # ticker -> {trade_date: (o,h,l,c)}
        rows = rds.execute(text(
            "select ticker, trade_date, open, high, low, close from stock_price_history "
            "where ticker = any(:t) and trade_date >= '20260601' and trade_date <= :e"),
            {"t": list(tickers), "e": end.replace("-", "")})
        for r in rows:
            if None not in (r.open, r.high, r.low, r.close) and float(r.open) > 0:
                prices[r.ticker][r.trade_date] = (float(r.open), float(r.high), float(r.low), float(r.close))
        return [d for d in days if d in batches], batches, prices
    finally:
        rds.close()


class Backtest:
    def __init__(self, config, days, batches, prices):
        self.config, self.exit_config = config, DEFAULT_EXIT_CONFIG
        self.days, self.batches, self.prices = days, batches, prices
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        TradePosition.__table__.create(engine)
        TradingHistory.__table__.create(engine)
        self.session = sessionmaker(bind=engine)()
        self.cash = INITIAL_CASH
        self.fills = []  # (date, ticker, side, qty, price, reason)
        self.equity = []
        self._last_hist_id = 0

    # ---------- 시세 헬퍼 ----------
    def _history(self, ticker, day, n=30):
        bars = self.prices.get(ticker, {})
        prior = sorted(d for d in bars if d < day)[-n:]
        return [{"high": bars[d][1], "low": bars[d][2], "close": bars[d][3]} for d in prior]

    def _daily(self, ticker, day):
        rows = self._history(ticker, day, self.config.atr_period + 5)
        return {
            "atr20": compute_atr(rows, period=self.config.atr_period),
            "lowest_10_days": compute_lowest_low(rows, period=self.exit_config.turtle_exit_days),
            "previous_close": rows[-1]["close"] if rows else None,
        }

    def _sync_fills(self, day):
        """파이프라인이 남긴 TradingHistory 신규 행을 체결 로그/현금에 반영."""
        rows = self.session.query(TradingHistory).filter(TradingHistory.id > self._last_hist_id).order_by(TradingHistory.id).all()
        for h in rows:
            self._record(day, h.ticker, h.trade_type, h.quantity, float(h.price), h.signal_source)
            self._last_hist_id = h.id

    def _record(self, day, ticker, side, qty, price, reason):
        amount = qty * price
        if side == "BUY":
            self.cash -= amount * (1 + BUY_COST)
        else:
            self.cash += amount * (1 - SELL_COST)
        self.fills.append((day, ticker, side, qty, price, reason))

    def _open_positions(self):
        return self.session.query(TradePosition).filter(TradePosition.status == "OPEN").all()

    # ---------- 하루 시뮬레이션 ----------
    def _stop_check(self, day, phase, closed_today):
        """phase="open": 시가 체결, phase="intraday": 저가 터치 시 트리거 가격 체결."""
        for p in self._open_positions():
            bar = self.prices.get(p.ticker, {}).get(day)
            if not bar:
                continue
            o, h, l, c = bar
            prev = self._daily(p.ticker, day)["previous_close"]
            emergency = prev * (1 + self.exit_config.emergency_loss_pct / 100.0) if prev else None
            stop = float(p.stop_price)
            trigger = max(stop, emergency) if emergency else stop
            reason = "EMERGENCY_EXIT" if emergency and emergency >= stop else (
                "INITIAL_STOP" if stop == float(p.initial_stop_price) else "TRAILING_STOP")
            fill = None
            if phase == "open" and o <= trigger:
                fill = o
            elif phase == "intraday" and l <= trigger:
                fill = trigger  # 시가가 트리거 위였던 종목만 남아 있음 - 트리거 가격 체결
            if fill is not None:
                pipeline.close_position_all(self.session, p, p.quantity, fill, reason)
                self.session.commit()
                closed_today.add(p.ticker)
        self._sync_fills(day)

    def _entry(self, day, price_idx, batch, closed_today):
        candidates = []
        ranked = sorted((r for r in batch.values() if r["overall_rank"] is not None), key=lambda r: r["overall_rank"])
        for r in ranked[:self.config.total_candidates]:
            bar = self.prices.get(r["ticker"], {}).get(day)
            daily = self._daily(r["ticker"], day)
            if not bar or not daily["previous_close"]:
                continue
            candidates.append(dict(r, previous_close=daily["previous_close"], current_price=bar[price_idx], atr20=daily["atr20"]))
        if not candidates or len(self._open_positions()) >= self.config.max_positions:
            return set()
        before = {p.ticker for p in self._open_positions()}
        pipeline.run_entry_pipeline(self.session, None, candidates, self.cash, self.config, dry_run=True,
                                    excluded_tickers=closed_today, skip_log=lambda m: None)
        self._sync_fills(day)
        return {p.ticker for p in self._open_positions()} - before

    def _close_phase(self, day, batch, closed_today):
        market = {}
        for p in self._open_positions():
            bar = self.prices.get(p.ticker, {}).get(day)
            if not bar:
                continue
            daily = self._daily(p.ticker, day)
            r = batch.get(p.ticker, {})
            prev = daily["previous_close"]
            market[p.ticker] = {
                "current_price": bar[3], "current_high": bar[1],
                "price_change_pct": (bar[3] - prev) / prev * 100 if prev else None,
                "atr20": daily["atr20"], "lowest_10_days": daily["lowest_10_days"],
                "current_rank": r.get("overall_rank"), "sector_score": r.get("sector_score"),
                "theme_score": r.get("theme_score"), "final_score": r.get("final_score"),
            }
        pipeline.run_exit_pipeline(self.session, None, market, self.config, self.exit_config, dry_run=True)
        self._sync_fills(day)
        closed_today |= {t for t in market if t not in {p.ticker for p in self._open_positions()}}
        pipeline.run_pyramiding_pipeline(self.session, None, market, self.config, dry_run=True)
        self._sync_fills(day)

    def run(self):
        for day in self.days:
            batch = self.batches[day]
            closed_today = set()
            self._stop_check(day, "open", closed_today)
            self._entry(day, 0, batch, closed_today)                    # 시가 진입
            self._stop_check(day, "intraday", closed_today)             # 장중 손절(저가 터치)
            self._close_phase(day, batch, closed_today)                 # 종가: 청산/손절가 갱신/피라미딩
            self._entry(day, 3, batch, closed_today)                    # 종가 부근 진입(갭 재평가 근사)
            value = sum(p.quantity * self._last_close(p.ticker, day) for p in self._open_positions())
            self.equity.append((day, self.cash + value, len(self._open_positions())))
        return self

    def _last_close(self, ticker, day):
        bars = self.prices.get(ticker, {})
        return bars[max(d for d in bars if d <= day)][3]

    # ---------- 결과 ----------
    def round_trips(self):
        """종목별 매수~전량청산 단위 손익(비용 포함). 기간 말 미청산은 종가 평가."""
        trips, openq = [], {}
        for day, t, side, qty, price, reason in self.fills:
            trip = openq.setdefault(t, {"ticker": t, "entry_day": day, "qty": 0, "cost": 0.0, "proceeds": 0.0,
                                        "buys": 0, "exit_reason": None, "exit_day": None})
            if side == "BUY":
                trip["qty"] += qty
                trip["cost"] += qty * price * (1 + BUY_COST)
                trip["buys"] += 1
            else:
                trip["qty"] -= qty
                trip["proceeds"] += qty * price * (1 - SELL_COST)
                if trip["qty"] <= 0:
                    trip.update(exit_reason=reason.replace("EXIT_", ""), exit_day=day)
                    trips.append(openq.pop(t))
        last = self.days[-1]
        for t, trip in openq.items():
            trip["proceeds"] += trip["qty"] * self._last_close(t, last) * (1 - SELL_COST)
            trip.update(exit_reason="(보유중)", exit_day=last)
            trips.append(trip)
        for trip in trips:
            trip["pnl"] = trip["proceeds"] - trip["cost"]
            trip["ret_pct"] = trip["pnl"] / trip["cost"] * 100 if trip["cost"] else 0.0
        return trips

    def summary(self):
        eq = [e for _, e, _ in self.equity]
        peak, mdd = INITIAL_CASH, 0.0
        for e in eq:
            peak = max(peak, e)
            mdd = min(mdd, (e - peak) / peak * 100)
        trips = self.round_trips()
        closed = [t for t in trips if t["exit_reason"] != "(보유중)"]
        wins = [t for t in closed if t["pnl"] > 0]
        gross_win = sum(t["pnl"] for t in trips if t["pnl"] > 0)
        gross_loss = -sum(t["pnl"] for t in trips if t["pnl"] < 0)
        return {
            "final": eq[-1], "ret_pct": (eq[-1] / INITIAL_CASH - 1) * 100, "mdd_pct": mdd,
            "trades": len(trips), "closed": len(closed), "win_rate": len(wins) / len(closed) * 100 if closed else None,
            "profit_factor": gross_win / gross_loss if gross_loss else None,
            "avg_positions": sum(n for _, _, n in self.equity) / len(self.equity),
            "invested_days": sum(1 for _, _, n in self.equity if n > 0),
            "trips": trips,
        }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2026-09-09")
    parser.add_argument("--end", default="2026-10-19")
    parser.add_argument("--trades", action="store_true", help="시나리오별 매매 내역 출력")
    args = parser.parse_args()
    logging.disable(logging.INFO)

    days, batches, prices = load_data(args.start, args.end)
    print(f"기간: {days[0]} ~ {days[-1]} ({len(days)}거래일), 시작자금 {INITIAL_CASH:,.0f}원, "
          f"KOSPI/KOSDAQ 일봉 근사(상단 docstring 한계 참고)\n")
    header = f"{'시나리오':<30} {'최종자산':>12} {'수익률':>8} {'MDD':>7} {'거래':>4} {'청산':>4} {'승률':>6} {'PF':>5} {'평균보유':>6} {'보유일':>5}"
    print(header)
    print("-" * len(header.encode("euc-kr", "ignore")))
    results = []
    for name, overrides in SCENARIOS:
        s = Backtest(replace(DEFAULT_CONFIG, **overrides), days, batches, prices).run().summary()
        results.append((name, s))
        wr = f"{s['win_rate']:.0f}%" if s["win_rate"] is not None else "-"
        pf = f"{s['profit_factor']:.2f}" if s["profit_factor"] is not None else "-"
        print(f"{name:<30} {s['final']:>12,.0f} {s['ret_pct']:>+7.2f}% {s['mdd_pct']:>6.2f}% {s['trades']:>4} "
              f"{s['closed']:>4} {wr:>6} {pf:>5} {s['avg_positions']:>6.1f} {s['invested_days']:>5}")
    if args.trades:
        for name, s in results:
            print(f"\n== {name}")
            for t in sorted(s["trips"], key=lambda t: t["entry_day"]):
                print(f"  {t['ticker']} {t['entry_day']}→{t['exit_day']} 매수{t['buys']}회 "
                      f"{t['pnl']:>+10,.0f}원 ({t['ret_pct']:+.1f}%) {t['exit_reason']}")


if __name__ == "__main__":
    main()
