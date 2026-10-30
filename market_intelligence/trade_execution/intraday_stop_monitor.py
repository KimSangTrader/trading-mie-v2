"""
IntradayStopMonitor - 장중 손절 감시 + 장중 매매 (1분 주기: 손절, 청산, 피라미딩, 신규진입)

================================================================================
【변경 이력】
================================================================================
【2026-10-14】최초 생성 (수익구간 보호 보강 1단계, 사용자 결정 C-2)
- 배경: 손절 판정이 하루 1회 사이클(09:05 KST, 장 시작 5분 후) 시세 스냅샷
  한 번으로만 이뤄졌다. 083310(엘오티베큠)은 2026-10-13 09:05 가격 12,030원이
  손절가 12,060원을 0.25% 밑돌아 시장가 전량매도됐는데, 그날 종가는 13,040원
  이었다. 반대로 장중에 손절가를 깨고 내려가도 다음 날 09:05까지는 아무 대응을
  못 한다. 사용자와 논의해 "종가 기준 판정(C-1)" 대신 "장중 감시(C-2)"를 택했고,
  휩쏘에 털리지 않게 아래 보강 장치를 넣었다.
- 판정 규칙(judge_intraday_stop, 순수 함수 - 테스트 대상):
    1) 당일 등락률 <= ExitConfig.emergency_loss_pct(-8%)          -> 즉시 전량매도(EMERGENCY_EXIT)
    2) 현재가 <= 손절가 - ATR20 x deep_breach_atr(0.5)             -> 즉시 전량매도(깊은 이탈)
    3) 시초 quiet 구간(09:00~09:10) 중 얕은 이탈                  -> 보류(카운트 안 함)
    4) 그 외 얕은 이탈이 confirm_polls(3)회 연속 확인되면          -> 전량매도
       (중간에 한 번이라도 손절가 위로 회복하면 카운트 리셋)
  사유 문자열은 exit_engine.analyze_exit()과 같은 INITIAL_STOP/TRAILING_STOP을
  쓴다(close_reason/signal_source 분석 일관성).
- 손절가 상향도 장중에 한다: 매 틱마다 exit_engine.update_stop()에 KIS의 당일
  고가를 넣어 최고가/손절가를 위로만 갱신한다(update_stop()은 같은 날 MFE 기준으로
  바뀜 - exit_engine.py 변경이력 참고). ATR20은 DB(stock_price_history)의 "어제까지"
  완성된 일봉으로 하루 1회만 계산해 캐시한다.
- 하루 1회 사이클(trade_execution_pipeline)과의 역할 분담: 손절(INITIAL/TRAILING)은
  이 모듈이 전담하고(ExitConfig.stop_handled_by_intraday_monitor=True), 하루 1회
  사이클은 긴급청산/논리붕괴/부분익절/터틀청산/피라미딩/신규진입을 계속 맡는다.
  두 프로세스가 같은 포지션을 동시에 매도하지 않도록 포지션 행을
  SELECT ... FOR UPDATE로 잠그고, 잠근 뒤 status가 여전히 OPEN인지 다시 확인한다.
- 실행: systemd 타이머(deploy/mie-v2-intraday-monitor.timer)가 평일 08:55 KST에
  띄우고, 15:20 KST(종가 단일가 직전)에 스스로 종료한다. KRX 휴장일이면 바로
  종료한다. 크래시 시 서비스 Restart=on-failure로 재기동된다(연속 이탈 카운트는
  메모리 상태라 재기동 시 리셋 - 손절을 늦추는 방향이라 안전 쪽).
- --dry-run은 주문도 DB 기록도 하지 않는다(판정/로그만). 최초 구현에서 dry-run이
  주문만 건너뛰고 포지션을 CLOSED로 기록해 실계좌와 어긋난 사고가 있어(2026-10-14
  라이브 점검 중, 수동 복구) 모든 쓰기를 rollback하도록 고쳤다.
- 알려진 한계: 시장가 주문 접수 = 체결로 간주한다(trade_execution_pipeline과 동일한
  한계 - 그 파일 변경이력 참고). 확인 횟수/깊은 이탈 폭/quiet 구간은 이 세션이 정한
  초기값이며 백테스트로 검증되지 않았다 - 운영하며 재검토하기로 사용자와 합의.

【2026-10-14】장중 매매로 확장 - 청산/피라미딩/신규진입도 1분 주기 (사용자 결정)
- 배경: 손절 감시는 1분마다인데 매수/매도(추가매수/신규진입/부분익절 등)는 하루 1회
  09:05뿐이라 주기가 맞지 않는다는 사용자 결정. 한 틱(run_cycle) 순서:
    시세 1회 조회(보유 + 랭킹 상위 total_candidates) -> run_tick(손절) ->
    run_trading_tick(기존 run_exit_pipeline -> run_pyramiding_pipeline -> run_entry_pipeline)
  파이프라인 함수는 그대로 재사용하고 market_data/후보만 장중 시세로 조립한다.
- 장중에 바뀌는 건 현재가/당일 고가/등락률뿐이다. 랭킹/점수(전일 22:00 KST 분석),
  ATR20/10일 최저가/전일 종가(어제까지 일봉)는 하루 1회 계산해 캐시한다.
- 매매 시간대 trade_start~trade_end(09:05~15:15), 손절 감시는 그대로 09:00~15:20.
- 1분 주기라서 새로 생긴 위험과 대응:
    · 당일 매수 대금이 예수금총금액에 결제(D+2) 전까지 반영되지 않아 같은 돈을 또 쓸
      수 있음 -> KISClient.get_balance()의 spendable_cash(D+1/D+2 정산 예수금 중 최소) 사용.
    · 손절된 종목을 다음 틱에 다시 사는 반복 -> reentry_block_hours(16시간) 재진입 금지.
    · 하루 1회 사이클(09:05 타이머)과 동시 신규진입 -> intraday_trading_enabled면 그 사이클은
      스스로 건너뜀(trade_execution_pipeline.py __main__).
    · 같은 보류 사유가 1분마다 로그에 쌓임 -> 사유가 바뀔 때만 기록, 파이프라인 요약 로그는
      실제 매매/오류가 있을 때만 기록.
- --dry-run에서는 파이프라인이 내부에서 commit해도 바깥 트랜잭션을 rollback해 DB에 남지 않는다.

【2026-10-30】잔고조회 캐싱 (_available_cash) - KIS 원장 초당 한도 회피
- 배경: 실전 전환(10/28) 후 시세/잔고/주문이 같은 실전 앱키를 쓰면서 잔고조회 EGW00215
  (원장 초당 거래건수 초과)가 10/29 하루 62건, 재시도 후에도 실패 12건. 주문(POST)은
  재시도하지 않으므로 원장 호출 자체를 줄여 주문이 한도에 걸릴 여지를 줄인다.
- 잔고(spendable_cash)는 balance_cache_seconds(5분) 동안 재사용. 조회 실패 시 마지막
  성공값을 쓰고, 성공값이 한 번도 없으면 기존처럼 0(신규진입 안 함).
- 매수(피라미딩/신규진입) 직후엔 캐시를 버려 다음 틱에 재조회하되, "매수 직전 잔고 -
  매수 대금"을 상한(_cash_ceiling)으로 둔다. KIS 조회값이 상한 이하로 내려오면(매수 반영
  확인) 상한을 해제 - spendable_cash가 당일 매수를 즉시 반영하는지 아직 실거래로 검증되지
  않아 같은 돈을 두 번 쓰지 않도록 보수적으로 막는 것. 매도 대금은 장중에 더하지 않는다.
- 같은 날 함께: 시세/주문 환경이 같으면 KISClient 하나를 공유(__main__) - 토큰 1분당 1회 제한 회피.

【2026-10-30】텔레그램 알림 (market_intelligence/utils/notifier.py)
- 실전 전환 후 주문 실패/예외가 로그에만 남던 문제. 알림 대상:
    · 손절 매도 주문 실패(가장 위험 - 1분마다 재시도 중임을 함께 알림)
    · 청산/피라미딩/신규진입 주문 실패(파이프라인 errors)
    · 손절 감시 틱/매매 틱 처리 중 예외(그 1분 동안 손절 점검이 멈춤)
    · 장중 루프 프로세스 비정상 종료(__main__)
- 같은 종류·종목 알림은 10분에 한 번만(notifier 쿨다운). notifier=None(테스트 기본)이면 보내지 않는다.
- 같은 날 추가(사용자 요청): 체결 알림 + 장 마감 요약.
    · 체결 알림: 손절 매도/청산/부분익절/추가매수/신규진입 주문이 접수될 때마다 1건(쿨다운 없음).
      시장가 주문 "접수"까지만 확인하고 실제 체결가는 조회하지 않으므로, 가격은 "기록가(주문 시점
      현재가)"로 표시한다. dry_run에서는 보내지 않는다.
    · 장 마감 요약(send_daily_summary): 15:20 종료 시 1건 - 당일 매매/주문실패/예외 건수, 보유 종목
      (현재가/손절가/여유), 계좌 총평가와 장 시작 대비 증감, DB OPEN 포지션과 실제 계좌 보유수량
      대조(불일치 시 ⚠️). 휴장일에도 1건 보내서 "알림이 안 온 날 = 루프가 안 돈 날"이 되게 한다.

사용법:
    python -m market_intelligence.trade_execution.intraday_stop_monitor            # 장중 상시 감시+매매
    python -m market_intelligence.trade_execution.intraday_stop_monitor --once     # 1틱만 실행(점검용)
    python -m market_intelligence.trade_execution.intraday_stop_monitor --dry-run  # 주문 없이 판정만
================================================================================
"""
import argparse
import logging
import os
import time
from datetime import datetime, time as dtime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

from market_intelligence.trade_execution.config import (
    ExitConfig, DEFAULT_EXIT_CONFIG,
    IntradayMonitorConfig, DEFAULT_INTRADAY_MONITOR_CONFIG,
    TradingConfig, DEFAULT_CONFIG,
)
from market_intelligence.trade_execution.exit_engine import update_stop

logger = logging.getLogger(__name__)

KST = ZoneInfo("Asia/Seoul")


def _parse_hhmm(value: str) -> dtime:
    hour, minute = value.split(":")
    return dtime(int(hour), int(minute))


def _stop_reason(position: Dict[str, Any]) -> str:
    stop_price = position.get("stop_price")
    initial_stop_price = position.get("initial_stop_price")
    if initial_stop_price is not None and stop_price == initial_stop_price:
        return "INITIAL_STOP"
    return "TRAILING_STOP"


def judge_intraday_stop(
    position: Dict[str, Any],
    quote: Dict[str, Any],
    atr20: Optional[float],
    breach_count: int,
    now_time: dtime,
    monitor_config: IntradayMonitorConfig = DEFAULT_INTRADAY_MONITOR_CONFIG,
    exit_config: ExitConfig = DEFAULT_EXIT_CONFIG,
) -> Tuple[str, str, int]:
    """장중 한 틱의 손절 판정(순수 함수). 규칙은 파일 상단 변경이력 참고.

    Returns:
        (action, reason, new_breach_count). action: "HOLD" | "SELL_ALL".
        reason이 STOP_BREACH_*면 HOLD 중 관찰 상태(로그용).
    """
    current_price = quote.get("current_price")
    if current_price is None:
        return "HOLD", "MISSING_QUOTE", breach_count

    change_pct = quote.get("change_pct")
    if change_pct is not None and change_pct <= exit_config.emergency_loss_pct:
        return "SELL_ALL", "EMERGENCY_EXIT", 0

    stop_price = position.get("stop_price")
    if stop_price is None or current_price > stop_price:
        return "HOLD", "ABOVE_STOP", 0

    reason = _stop_reason(position)

    if atr20 is not None and atr20 > 0 and current_price <= stop_price - atr20 * monitor_config.deep_breach_atr:
        return "SELL_ALL", reason, 0

    if now_time < _parse_hhmm(monitor_config.opening_quiet_until):
        return "HOLD", "STOP_BREACH_QUIET", 0

    breach_count += 1
    if breach_count >= monitor_config.confirm_polls:
        return "SELL_ALL", reason, 0
    return "HOLD", "STOP_BREACH_PENDING", breach_count


def load_atr20(session, ticker: str, today_yyyymmdd: str, config: TradingConfig = DEFAULT_CONFIG) -> Optional[float]:
    """DB stock_price_history에서 오늘 이전(어제까지) 완성된 일봉으로 ATR20을 계산한다.
    데이터가 부족하면 None - 그 종목은 깊은 이탈/손절가 상향 없이 얕은 이탈 규칙만 적용된다."""
    from db.models import StockPriceHistory
    from market_intelligence.trade_execution.atr import compute_atr

    rows = (
        session.query(StockPriceHistory)
        .filter(StockPriceHistory.ticker == ticker, StockPriceHistory.trade_date < today_yyyymmdd)
        .order_by(StockPriceHistory.trade_date.desc())
        .limit(config.atr_period + 5)
        .all()
    )
    rows.reverse()
    price_rows = [
        {"high": float(r.high) if r.high is not None else None,
         "low": float(r.low) if r.low is not None else None,
         "close": float(r.close) if r.close is not None else None}
        for r in rows
    ]
    return compute_atr(price_rows, period=config.atr_period)


class IntradayStopMonitor:
    def __init__(
        self,
        session_factory,
        quote_client,
        order_client,
        monitor_config: IntradayMonitorConfig = DEFAULT_INTRADAY_MONITOR_CONFIG,
        exit_config: ExitConfig = DEFAULT_EXIT_CONFIG,
        trading_config: TradingConfig = DEFAULT_CONFIG,
        dry_run: bool = False,
        notifier=None,
    ):
        self.session_factory = session_factory
        self.quote_client = quote_client
        self.order_client = order_client
        self.monitor_config = monitor_config
        self.exit_config = exit_config
        self.trading_config = trading_config
        self.dry_run = dry_run
        self.notifier = notifier  # 【2026-10-30】TelegramNotifier 또는 None(알림 없음)
        self._stats: Dict[str, int] = {}               # 【2026-10-30】장 마감 요약용 당일 집계
        self._opening_total: Optional[float] = None    # 장 시작 시 계좌 총평가(요약의 증감 기준)
        self._last_quotes: Dict[str, Dict[str, Any]] = {}
        self.breach_counts: Dict[int, int] = {}
        self.atr_cache: Dict[Tuple[str, str], Optional[float]] = {}
        self.last_heartbeat: Optional[datetime] = None
        self._ranking_cache: List[Any] = []
        self._ranking_cache_day: Optional[str] = None
        self._daily_cache: Dict[Tuple[str, str], Dict[str, Optional[float]]] = {}
        self._last_skip: Dict[str, str] = {}
        self._cash: Optional[float] = None             # 【2026-10-30】잔고 캐시(spendable_cash)
        self._cash_at: Optional[datetime] = None       # 마지막 조회 성공 시각(None이면 다음에 재조회)
        self._cash_ceiling: Optional[float] = None     # 매수 직후 KIS 반영 전까지 쓸 수 있는 현금 상한

    def _alert(self, text: str, key: Optional[str]) -> None:
        """텔레그램 알림(설정 없으면 무시). notifier.send()는 예외를 올리지 않는다."""
        if self.notifier is not None:
            self.notifier.send(text, key=key)

    def _count(self, name: str, n: int = 1) -> None:
        self._stats[name] = self._stats.get(name, 0) + n

    def _fill_alerts(self, session, history_id: int) -> List[str]:
        """이번 틱 매매 파이프라인이 남긴 TradingHistory로 체결(주문 접수) 알림 문구를 만든다."""
        from db.models import TradePosition, TradingHistory

        labels = {"ENTRY": "신규진입 매수", "PYRAMID": "추가매수", "EXIT": "매도"}
        texts = []
        rows = session.query(TradingHistory).filter(TradingHistory.id > history_id).order_by(TradingHistory.id).all()
        for h in rows:
            source = h.signal_source or ""
            label = labels.get(source.split("_", 1)[0], h.trade_type)
            if source == "EXIT_TAKE_PROFIT_2R":
                label = "부분익절 매도"
            price = float(h.price) if h.price is not None else None
            text = (f"✅ {label} 주문 접수: {h.ticker} {h.quantity}주\n"
                    f"기록가 {price:,.0f}원 (주문 시점 현재가, 실제 체결가는 계좌에서 확인)\n사유: {source}")
            if h.trade_type == "BUY":
                pos = session.query(TradePosition).filter(TradePosition.ticker == h.ticker, TradePosition.status == "OPEN").first()
                if pos is not None and pos.stop_price is not None:
                    text += f"\n보유 {pos.quantity}주 · 손절가 {float(pos.stop_price):,.0f}원"
            texts.append(text)
        return texts

    def _atr20(self, session, ticker: str, today: str) -> Optional[float]:
        key = (ticker, today)
        if key not in self.atr_cache:
            self.atr_cache[key] = load_atr20(session, ticker, today, self.trading_config)
        return self.atr_cache[key]

    def _commit(self, session) -> None:
        """dry_run이면 DB에 아무것도 남기지 않는다(판정/로그만) - 주문을 건너뛴 채
        포지션만 CLOSED로 바뀌어 실계좌와 DB가 어긋나는 일을 막기 위함."""
        if self.dry_run:
            session.rollback()
        else:
            session.commit()

    def run_tick(self, now: datetime, quotes: Optional[Dict[str, Dict[str, Any]]] = None) -> Dict[str, int]:
        """보유 중인 모든 OPEN 포지션의 손절을 한 번씩 점검한다. quotes를 주면 그 시세를
        쓰고(run_cycle()이 이번 틱에 한 번만 조회해 공유), 없으면 직접 조회한다."""
        from db.models import TradePosition
        from market_intelligence.trade_execution.trade_execution_pipeline import (
            position_to_dict, close_position_all, _place_order_or_dry_run,
        )

        today = now.strftime("%Y%m%d")
        result = {"checked": 0, "sold_all": 0, "stops_raised": 0, "quote_failed": 0}
        heartbeat_lines = []

        session = self.session_factory()
        try:
            position_ids = [
                pid for (pid,) in
                session.query(TradePosition.id).filter(TradePosition.status == "OPEN").all()
            ]
            for position_id in position_ids:
                # 잠금 전에 시세부터 받는다 - 네트워크 대기 동안 행 잠금을 잡고 있지 않기 위함
                ticker = session.query(TradePosition.ticker).filter(TradePosition.id == position_id).scalar()
                quote = quotes.get(ticker) if quotes is not None else self.quote_client.get_current_quote(ticker)
                if not quote:
                    result["quote_failed"] += 1
                    continue

                position = (
                    session.query(TradePosition)
                    .filter(TradePosition.id == position_id)
                    .with_for_update()
                    .one()
                )
                if position.status != "OPEN":
                    session.rollback()  # 하루 1회 사이클이 먼저 청산함 - 잠금 해제
                    self.breach_counts.pop(position_id, None)
                    continue

                result["checked"] += 1
                pos_dict = position_to_dict(position)
                atr20 = self._atr20(session, ticker, today)
                current_price = quote["current_price"]

                action, reason, count = judge_intraday_stop(
                    pos_dict, quote, atr20, self.breach_counts.get(position_id, 0),
                    now.time(), self.monitor_config, self.exit_config,
                )
                self.breach_counts[position_id] = count

                if action == "SELL_ALL":
                    qty = position.quantity
                    order = _place_order_or_dry_run(self.order_client, self.dry_run, ticker, "sell", qty)
                    if order.get("success"):
                        close_position_all(session, position, qty, current_price, reason)
                        self._commit(session)
                        self.breach_counts.pop(position_id, None)
                        result["sold_all"] += 1
                        self._count("stop_sold")
                        if not self.dry_run:
                            self._alert(
                                f"🛑 손절 매도 주문 접수: {ticker} {qty}주 ({reason})\n"
                                f"기록가 {current_price:,.0f}원 / 손절가 {pos_dict['stop_price']:,.0f}원\n"
                                f"주문번호 {order.get('order_no')} (실제 체결가는 계좌에서 확인)",
                                key=None,
                            )
                        logger.info(
                            f"🛑 {ticker}: 장중 손절 전량매도 {qty}주 - {reason} "
                            f"(현재가 {current_price:,.0f} / 손절가 {pos_dict['stop_price']:,.0f} / "
                            f"주문번호 {order.get('order_no')})"
                        )
                    else:
                        session.rollback()
                        logger.error(f"❌ {ticker}: 장중 손절 매도 주문 실패 - {order.get('message')} (다음 틱 재시도)")
                        self._count("order_failures")
                        self._alert(
                            f"🚨 손절 매도 주문 실패: {ticker} {qty}주 ({reason})\n"
                            f"현재가 {current_price:,.0f} / 손절가 {pos_dict['stop_price']:,.0f}\n"
                            f"사유: {order.get('message')}\n1분마다 자동 재시도 중 - 계좌를 직접 확인하세요.",
                            key=f"stop_fail:{ticker}",
                        )
                    continue

                if reason == "STOP_BREACH_PENDING":
                    logger.info(
                        f"⚠️  {ticker}: 손절가 이탈 확인 중 {count}/{self.monitor_config.confirm_polls} "
                        f"(현재가 {current_price:,.0f} / 손절가 {pos_dict['stop_price']:,.0f})"
                    )
                elif reason == "STOP_BREACH_QUIET":
                    logger.info(
                        f"⏳ {ticker}: 시초 변동 구간 손절가 얕은 이탈 - 관망 "
                        f"(현재가 {current_price:,.0f} / 손절가 {pos_dict['stop_price']:,.0f})"
                    )

                # 보유 유지 - 당일 고가로 최고가/손절가를 위로만 갱신
                new_stop = update_stop(
                    pos_dict, current_high=quote.get("high") or current_price, atr20=atr20,
                    current_price=current_price, config=self.exit_config,
                )
                if new_stop is not None:
                    old_stop = pos_dict["stop_price"]
                    position.highest_price = new_stop["highest_price"]
                    if new_stop["stop_price"] > old_stop:
                        position.stop_price = new_stop["stop_price"]
                        result["stops_raised"] += 1
                        logger.info(f"⬆️  {ticker}: 손절가 상향 {old_stop:,.0f} -> {new_stop['stop_price']:,.0f} "
                                    f"(최고가 {new_stop['highest_price']:,.0f}, ATR20 {atr20:,.1f})")
                stop_now = float(position.stop_price)
                self._commit(session)

                heartbeat_lines.append(
                    f"{ticker} 현재가 {current_price:,.0f} 손절가 {stop_now:,.0f} "
                    f"(여유 {(current_price - stop_now) / current_price * 100:+.1f}%)"
                )
        except Exception as e:
            session.rollback()
            logger.exception("❌ 장중 감시 틱 처리 중 예외 - 다음 틱에 재시도")
            self._count("exceptions")
            self._alert(f"⚠️ 장중 손절 감시 처리 중 예외 - 이번 1분 손절 점검 중단, 다음 틱 재시도\n{type(e).__name__}: {e}",
                        key="exception:stop_tick")
        finally:
            session.close()

        if self.last_heartbeat is None or now - self.last_heartbeat >= timedelta(minutes=self.monitor_config.heartbeat_minutes):
            self.last_heartbeat = now
            summary = " | ".join(heartbeat_lines) if heartbeat_lines else "보유 포지션 없음"
            logger.info(f"💓 장중 감시 중 ({now:%H:%M} KST) - {summary}")

        return result

    # ------------------------------------------------------------------
    # 【2026-10-14】장중 매매 - 청산(손절 외)/피라미딩/신규진입을 1분 주기로
    # ------------------------------------------------------------------
    def _trading_session(self):
        """(session, cleanup). dry_run이면 이 세션의 commit()을 flush()로 바꿔치기하고 끝에
        rollback한다 - 파이프라인 함수들이 내부에서 commit()해도 DB에 아무것도 남지 않는다
        (파이프라인 자체 dry_run은 주문만 건너뛰고 DB는 바꾸기 때문 - 위 _commit() 참고)."""
        session = self.session_factory()
        if not self.dry_run:
            return session, session.close

        session.commit = session.flush

        def cleanup():
            session.rollback()
            session.close()
        return session, cleanup

    def _ranking(self, session, today: str) -> List[Any]:
        """최신 계층형 랭킹 배치(전일 장마감 분석 결과)를 하루 1회만 읽어 캐시."""
        if self._ranking_cache_day != today:
            from db.models import StockHierarchicalScore

            latest_ts = (
                session.query(StockHierarchicalScore.timestamp)
                .order_by(StockHierarchicalScore.timestamp.desc()).first()
            )
            rows = []
            if latest_ts:
                rows = (
                    session.query(StockHierarchicalScore)
                    .filter(StockHierarchicalScore.timestamp == latest_ts[0])
                    .order_by(StockHierarchicalScore.overall_rank.asc())
                    .all()
                )
                session.expunge_all()
            self._ranking_cache = rows
            self._ranking_cache_day = today
        return self._ranking_cache

    def _daily_stats(self, session, ticker: str, today: str) -> Dict[str, Optional[float]]:
        """어제까지 완성된 일봉으로 ATR20/10일 최저가/전일 종가를 종목당 하루 1회 계산.
        (하루 1회 사이클은 당일 미완성 캔들까지 섞어 10일 최저가를 계산해 장중에는
        현재가가 그보다 낮아질 수 없었다 - 여기서는 전일까지만 쓴다.)"""
        key = (ticker, today)
        if key not in self._daily_cache:
            from db.models import StockPriceHistory
            from market_intelligence.trade_execution.atr import compute_atr
            from market_intelligence.trade_execution.exit_engine import compute_lowest_low

            rows = (
                session.query(StockPriceHistory)
                .filter(StockPriceHistory.ticker == ticker, StockPriceHistory.trade_date < today)
                .order_by(StockPriceHistory.trade_date.desc())
                .limit(self.trading_config.atr_period + 5)
                .all()
            )
            rows.reverse()
            price_rows = [
                {"high": float(r.high) if r.high is not None else None,
                 "low": float(r.low) if r.low is not None else None,
                 "close": float(r.close) if r.close is not None else None}
                for r in rows
            ]
            self._daily_cache[key] = {
                "atr20": compute_atr(price_rows, period=self.trading_config.atr_period),
                "lowest_10_days": compute_lowest_low(price_rows, period=self.exit_config.turtle_exit_days),
                "previous_close": price_rows[-1]["close"] if price_rows else None,
            }
            self.atr_cache[key] = self._daily_cache[key]["atr20"]
        return self._daily_cache[key]

    def _recently_closed(self, session, now: datetime) -> set:
        """reentry_block_hours 안에 청산된 종목(당일 재진입 금지). closed_at은 DB/드라이버에
        따라 UTC 또는 서버 현지시각으로 저장돼 있어(naive), 둘 중 이른 기준으로 넉넉하게 자른다."""
        from datetime import timezone
        from db.models import TradePosition

        hours = timedelta(hours=self.monitor_config.reentry_block_hours)
        local_naive = datetime.now()
        utc_naive = datetime.now(timezone.utc).replace(tzinfo=None)
        cutoff = min(local_naive, utc_naive) - hours
        rows = (
            session.query(TradePosition.ticker)
            .filter(TradePosition.status == "CLOSED", TradePosition.closed_at >= cutoff)
            .all()
        )
        return {t for (t,) in rows}

    def _log_skip(self, message: str) -> None:
        """진입 보류 사유는 종목별로 내용이 바뀔 때만 남긴다(1분마다 같은 줄 반복 방지)."""
        ticker = message.split(":", 1)[0]
        if self._last_skip.get(ticker) != message:
            self._last_skip[ticker] = message
            logger.info(message.strip())

    def _available_cash(self, now: datetime) -> float:
        """잔고조회 캐시(변경이력 【2026-10-30】). balance_cache_seconds 안이면 재조회하지 않는다."""
        cached = self._cash_at is not None and (now - self._cash_at).total_seconds() < self.monitor_config.balance_cache_seconds
        if not cached:
            balance = self.order_client.get_balance(verbose=False)
            fresh = (balance or {}).get("cash", {}).get("spendable_cash")
            if fresh is not None:
                fresh = float(fresh)
                if self._cash_ceiling is not None and fresh <= self._cash_ceiling:
                    self._cash_ceiling = None  # KIS가 당일 매수를 반영함 - 상한 해제
                self._cash, self._cash_at = fresh, now
            elif self._cash is None:
                return 0.0  # 조회 실패 + 성공값 없음 - 기존 동작(신규진입 안 함)
        if self._cash_ceiling is not None:
            self._cash = min(self._cash, self._cash_ceiling)
        return self._cash

    def _record_spend(self, spent: float, base: Optional[float]) -> None:
        """매수 대금 반영: 다음 틱에 재조회하되 base - spent를 상한으로 둔다."""
        if spent <= 0:
            return
        self._cash_at = None
        if base is None:
            return  # 기준 잔고를 모름 - 다음 조회값을 그대로 쓴다
        self._cash_ceiling = max(base - spent, 0.0)
        self._cash = self._cash_ceiling

    @staticmethod
    def _last_history_id(session) -> int:
        from sqlalchemy import func
        from db.models import TradingHistory
        return session.query(func.max(TradingHistory.id)).scalar() or 0

    @staticmethod
    def _buy_amount_since(session, history_id: int) -> float:
        from db.models import TradingHistory
        rows = session.query(TradingHistory).filter(TradingHistory.id > history_id, TradingHistory.trade_type == "BUY").all()
        return float(sum((r.quantity or 0) * float(r.price or 0) for r in rows))

    def run_trading_tick(self, now: datetime, quotes: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        """현재가 + 전일 기준 일간 데이터로 market_data/후보를 조립해 기존 파이프라인
        (청산 -> 피라미딩 -> 신규진입)을 그대로 실행한다. 손절은 run_tick()이 이미 처리했으므로
        여기서는 ExitConfig.stop_handled_by_intraday_monitor=True로 건너뛴다."""
        from db.models import TradePosition
        from market_intelligence.trade_execution import trade_execution_pipeline as pipeline

        today = now.strftime("%Y%m%d")
        result: Dict[str, Any] = {}
        session, cleanup = self._trading_session()
        pipeline_logger = logging.getLogger(pipeline.__name__)
        previous_level = pipeline_logger.level
        pipeline_logger.setLevel(logging.WARNING)  # 파이프라인의 1분마다 반복되는 요약 로그 억제
        fill_texts: List[str] = []
        try:
            tick_history_id = self._last_history_id(session)
            ranking = self._ranking(session, today)
            open_tickers = {t for (t,) in session.query(TradePosition.ticker).filter(TradePosition.status == "OPEN").all()}
            excluded = self._recently_closed(session, now)
            top = ranking[:self.trading_config.total_candidates]
            rank_by_ticker = {r.ticker: r for r in ranking}

            def _f(v):
                return float(v) if v is not None else None

            market_data: Dict[str, Dict[str, Any]] = {}
            for ticker in open_tickers | {r.ticker for r in top}:
                quote = quotes.get(ticker)
                if not quote:
                    continue
                daily = self._daily_stats(session, ticker, today)
                rank_row = rank_by_ticker.get(ticker)
                market_data[ticker] = {
                    "current_price": quote["current_price"],
                    "current_high": quote.get("high") or quote["current_price"],
                    "previous_close": daily["previous_close"] or quote.get("base_price"),
                    "price_change_pct": quote.get("change_pct"),
                    "atr20": daily["atr20"],
                    "lowest_10_days": daily["lowest_10_days"],
                    "current_rank": rank_row.overall_rank if rank_row else None,
                    "sector_score": _f(rank_row.sector_score) if rank_row else None,
                    "theme_score": _f(rank_row.theme_score) if rank_row else None,
                    "final_score": _f(rank_row.final_score) if rank_row else None,
                }

            ranked_candidates = []
            for r in top:
                data = market_data.get(r.ticker)
                if not data:
                    continue
                ranked_candidates.append({
                    "ticker": r.ticker, "market": r.market, "sector": r.sector,
                    "primary_theme": r.primary_theme, "overall_rank": r.overall_rank,
                    "final_score": data["final_score"], "sector_score": data["sector_score"],
                    "theme_score": data["theme_score"], "previous_close": data["previous_close"],
                    "current_price": data["current_price"], "atr20": data["atr20"],
                })

            result["exit"] = pipeline.run_exit_pipeline(
                session, self.order_client, market_data, self.trading_config, self.exit_config, dry_run=self.dry_run)
            history_id = self._last_history_id(session)
            result["pyramiding"] = pipeline.run_pyramiding_pipeline(
                session, self.order_client, market_data, self.trading_config, dry_run=self.dry_run)
            self._record_spend(self._buy_amount_since(session, history_id), base=self._cash)

            open_count = session.query(TradePosition).filter(TradePosition.status == "OPEN").count()
            if ranked_candidates and open_count < self.trading_config.max_positions:
                available_cash = self._available_cash(now)
                history_id = self._last_history_id(session)
                result["entry"] = pipeline.run_entry_pipeline(
                    session, self.order_client, ranked_candidates, available_cash, self.trading_config,
                    dry_run=self.dry_run, excluded_tickers=excluded, skip_log=self._log_skip,
                )
                self._record_spend(self._buy_amount_since(session, history_id), base=available_cash)
            fill_texts = self._fill_alerts(session, tick_history_id)
        except Exception as e:
            session.rollback()
            logger.exception("❌ 장중 매매 틱 처리 중 예외 - 다음 틱에 재시도")
            self._count("exceptions")
            self._alert(f"⚠️ 장중 매매 처리 중 예외 - 다음 틱 재시도\n{type(e).__name__}: {e}", key="exception:trading_tick")
        finally:
            pipeline_logger.setLevel(previous_level)
            cleanup()

        exit_r, pyr_r, entry_r = result.get("exit", {}), result.get("pyramiding", {}), result.get("entry", {})
        acted = exit_r.get("sold_all", 0) + exit_r.get("partial_sold", 0) + pyr_r.get("added", 0) + entry_r.get("entered", 0)
        errors = exit_r.get("errors", []) + pyr_r.get("errors", []) + entry_r.get("errors", [])
        if acted or errors:
            logger.info(
                f"🔁 장중 매매 ({now:%H:%M} KST) - 전량청산 {exit_r.get('sold_all', 0)}, 부분익절 {exit_r.get('partial_sold', 0)}, "
                f"추가매수 {pyr_r.get('added', 0)}, 신규진입 {entry_r.get('entered', 0)}"
                + (f", 오류 {errors}" if errors else "")
            )
        self._count("entered", entry_r.get("entered", 0))
        self._count("pyramid_added", pyr_r.get("added", 0))
        self._count("exit_sold", exit_r.get("sold_all", 0))
        self._count("partial_sold", exit_r.get("partial_sold", 0))
        self._count("order_failures", len(errors))
        if not self.dry_run:
            for text in fill_texts:
                self._alert(text, key=None)
        for label, errs in (("청산 매도", exit_r.get("errors", [])), ("추가매수", pyr_r.get("errors", [])),
                            ("신규진입 매수", entry_r.get("errors", []))):
            for err in errs:
                ticker = err.get("ticker")
                self._alert(f"🚨 {label} 주문 실패: {ticker} {err.get('action', '')}\n사유: {err.get('message')}",
                            key=f"order_fail:{label}:{ticker}")
        return result

    def _fetch_quotes(self, session_tickers: set) -> Dict[str, Dict[str, Any]]:
        quotes = {}
        for ticker in sorted(session_tickers):
            quote = self.quote_client.get_current_quote(ticker)
            if quote:
                quotes[ticker] = quote
        return quotes

    def run_cycle(self, now: datetime, include_trading: bool) -> Dict[str, Any]:
        """1분 주기 한 번: 시세를 한 번만 조회해 손절 틱 -> (매매 시간대면) 매매 틱."""
        from db.models import TradePosition

        session = self.session_factory()
        try:
            tickers = {t for (t,) in session.query(TradePosition.ticker).filter(TradePosition.status == "OPEN").all()}
            if include_trading:
                ranking = self._ranking(session, now.strftime("%Y%m%d"))
                tickers |= {r.ticker for r in ranking[:self.trading_config.total_candidates]}
        finally:
            session.close()

        quotes = self._fetch_quotes(tickers)
        self._last_quotes.update(quotes)
        result = {"stop": self.run_tick(now, quotes)}
        if include_trading:
            result["trading"] = self.run_trading_tick(now, quotes)
        return result

    def daily_summary_text(self, now: datetime, balance: Optional[Dict[str, Any]], holiday: bool = False) -> str:
        """장 마감 요약 문구(순수 조립 - 조회는 호출측). balance는 get_balance() 결과 또는 None/{}."""
        from db.models import TradePosition

        weekday = "월화수목금토일"[now.weekday()]
        head = f"📊 장 마감 요약 {now:%Y-%m-%d}({weekday})"
        if holiday:
            return f"{head}\nKRX 휴장일 - 장중 감시·매매 없음 (루프는 정상 기동)"

        st = self._stats.get
        lines = [
            head,
            f"매매: 신규진입 {st('entered', 0)} · 추가매수 {st('pyramid_added', 0)} · 청산 {st('exit_sold', 0)} · "
            f"부분익절 {st('partial_sold', 0)} · 손절 {st('stop_sold', 0)}",
            f"주문 실패 {st('order_failures', 0)} · 처리 예외 {st('exceptions', 0)}",
        ]

        session = self.session_factory()
        try:
            positions = session.query(TradePosition).filter(TradePosition.status == "OPEN").order_by(TradePosition.ticker).all()
            db_qty = {p.ticker: p.quantity or 0 for p in positions}
            lines.append(f"보유 {len(positions)}종목")
            for p in positions:
                price = (self._last_quotes.get(p.ticker) or {}).get("current_price")
                stop = float(p.stop_price) if p.stop_price is not None else None
                avg = float(p.average_price) if p.average_price is not None else None
                gap = f" (여유 {(price - stop) / price * 100:+.1f}%)" if price and stop else ""
                lines.append(
                    f"  {p.ticker} {p.quantity}주 평균 {avg:,.0f} 현재 {price:,.0f} 손절 {stop:,.0f}{gap}"
                    if price and avg and stop else f"  {p.ticker} {p.quantity}주 (시세/손절가 없음)"
                )
        finally:
            session.close()

        if not balance:
            lines.append("⚠️ 계좌 잔고 조회 실패 - 계좌를 직접 확인하세요")
            return "\n".join(lines)

        total = (balance.get("cash") or {}).get("total_evaluation_amount")
        if total is not None:
            change = f" (장 시작 대비 {total - self._opening_total:+,.0f}원)" if self._opening_total is not None else ""
            lines.append(f"계좌 총평가 {total:,.0f}원{change}")

        kis_qty = {b.get("ticker"): int(b.get("quantity") or 0) for b in balance.get("positions") or []}
        mismatches = [
            f"{t} DB {db_qty.get(t, 0)}주 / 계좌 {kis_qty.get(t, 0)}주"
            for t in sorted(set(db_qty) | set(kis_qty)) if db_qty.get(t, 0) != kis_qty.get(t, 0)
        ]
        if mismatches:
            lines.append("⚠️ DB-계좌 보유 불일치: " + ", ".join(mismatches))
        else:
            lines.append("DB-계좌 보유수량 일치 ✅")
        return "\n".join(lines)

    def send_daily_summary(self, now: datetime, holiday: bool = False) -> None:
        balance = None if holiday else self.order_client.get_balance(verbose=False)
        self._alert(self.daily_summary_text(now, balance, holiday=holiday), key=None)

    def run_forever(self) -> None:
        from data.krx_calendar import is_krx_trading_day

        open_t = _parse_hhmm(self.monitor_config.market_open)
        close_t = _parse_hhmm(self.monitor_config.market_close)

        now = datetime.now(KST)
        if not is_krx_trading_day(now.date()):
            logger.info(f"ℹ️  {now:%Y-%m-%d}는 KRX 휴장일 - 장중 감시 없이 종료")
            self.send_daily_summary(now, holiday=True)
            return

        opening = self.order_client.get_balance(verbose=False)
        self._opening_total = ((opening or {}).get("cash") or {}).get("total_evaluation_amount")

        logger.info(
            f"🚀 장중 손절 감시 시작 ({'DRY-RUN' if self.dry_run else '실주문'}) - "
            f"{self.monitor_config.market_open}~{self.monitor_config.market_close} KST, "
            f"{self.monitor_config.poll_interval_sec}초 간격, 얕은 이탈 {self.monitor_config.confirm_polls}회 연속 확인, "
            f"깊은 이탈 손절가-{self.monitor_config.deep_breach_atr}ATR 즉시, "
            f"~{self.monitor_config.opening_quiet_until} 시초 관망"
            + (f" | 장중 매매(청산/피라미딩/신규진입) {self.monitor_config.trade_start}~{self.monitor_config.trade_end} 1분 주기"
               if self.monitor_config.intraday_trading_enabled else " | 장중 매매 꺼짐(손절 감시만)")
        )

        trade_start = _parse_hhmm(self.monitor_config.trade_start)
        trade_end = _parse_hhmm(self.monitor_config.trade_end)

        while True:
            now = datetime.now(KST)
            if now.time() >= close_t:
                logger.info(f"✅ 장중 감시 종료 ({now:%H:%M} KST)")
                self.send_daily_summary(now)
                return
            if now.time() < open_t:
                time.sleep(min(30, self.monitor_config.poll_interval_sec))
                continue
            started = time.monotonic()
            include_trading = (
                self.monitor_config.intraday_trading_enabled and trade_start <= now.time() < trade_end
            )
            self.run_cycle(now, include_trading)
            # 틱 처리 시간(시세 조회 수십 건)을 빼고 잠들어 주기가 밀리지 않게 한다
            time.sleep(max(1.0, self.monitor_config.poll_interval_sec - (time.monotonic() - started)))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")

    parser = argparse.ArgumentParser(description="MIE V2.0 장중 손절 감시 + 장중 매매")
    parser.add_argument("--once", action="store_true", help="1틱만 실행하고 종료(점검용, 시간 제한 무시)")
    parser.add_argument("--dry-run", action="store_true", help="주문 없이 판정/로그만")
    args = parser.parse_args()

    from config.database import SessionLocal
    from data.kis_client import KISClient

    # trade_execution_pipeline.py __main__과 동일한 안전 원칙: 시세는 전역 ENVIRONMENT
    # (실전 서버 시세, 읽기 전용), 주문은 MIE_TRADE_ENVIRONMENT(기본 모의투자)로 분리.
    trade_environment = os.getenv("MIE_TRADE_ENVIRONMENT", "development").lower()
    print(f"⚠️  매매 실행 환경: {trade_environment} "
          f"({'실전투자 - 진짜 주문' if trade_environment == 'production' else '모의투자'})")
    quote_client = KISClient()
    # 【2026-10-30】실전 전환 후 시세/주문 환경이 같으면(같은 앱키) 클라이언트를 공유한다 - 따로 만들면
    # 두 번째 토큰 발급이 KIS 1분당 1회 제한(EGW00133, 403)에 걸려 10/29 09:05 첫 매매 틱에 주문용
    # 클라이언트가 토큰 없이 시작했다. 환경이 다르면(모의투자 주문) 기존처럼 별도 인스턴스.
    order_client = quote_client if quote_client.environment == trade_environment else KISClient(environment=trade_environment)

    from market_intelligence.utils.notifier import TelegramNotifier
    env_label = "DRY-RUN" if args.dry_run else ("실전" if trade_environment == "production" else "모의")
    notifier = TelegramNotifier(prefix=f"[MIE {env_label}] ")

    monitor = IntradayStopMonitor(SessionLocal, quote_client, order_client, dry_run=args.dry_run, notifier=notifier)
    try:
        if args.once:
            print(monitor.run_cycle(datetime.now(KST), include_trading=DEFAULT_INTRADAY_MONITOR_CONFIG.intraday_trading_enabled))
        else:
            monitor.run_forever()
    except BaseException as e:  # KeyboardInterrupt/systemd 종료 포함 - 알리고 그대로 다시 올린다
        if not isinstance(e, SystemExit) or e.code not in (0, None):
            notifier.send(f"🛑 장중 루프 비정상 종료 - 오늘 남은 시간 손절 감시/매매 없음\n{type(e).__name__}: {e}",
                          key="process_crash")
        raise
