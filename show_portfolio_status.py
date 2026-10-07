"""
계좌 보유종목 + 손익 현황을 한눈에 보는 대시보드형 조회 스크립트.

================================================================================
【변경 이력】
================================================================================
【2026-10-07】최초 생성
- 배경: 사용자가 "로그만 봐서는 보유종목별 증감율/증감금액/최종금액, 계좌 전체
  보유 잔고를 한눈에 알기 불편하다"고 요청. 지금까지는 trade_execution.log에
  흩어진 "⏭️ {ticker}: ..." 줄이나 systemd 로그로만 간접 확인했는데, 그 로그엔
  신규진입 검토 사유만 남고 "지금 뭘 얼마나 들고 있고 얼마 벌고/잃었는지"를
  요약해 보여주는 화면이 없었다.
- show_today_candidates.py(조회 전용, DB만 읽음)와 같은 위치/성격이지만, 이
  스크립트는 계좌 실시간 잔고가 필요해서 KIS API도 함께 호출한다(DB에는 아무것도
  쓰지 않음 - 여전히 읽기 전용).
- data/kis_client.py의 get_balance()가 이미 종목별 평가금액/평가손익금액/
  평가손익율과 계좌 전체 예수금/총평가금액을 다 주므로, 그 응답을 보기 좋게 표로
  찍는 게 핵심이다. 여기에 db.models.TradePosition(OPEN 상태)을 종목코드로
  매칭해서 진입가(최초 매수가, 피라미딩에도 안 바뀜)/진입횟수/현재 손절가처럼
  KIS 응답에는 없는 이 시스템 고유의 맥락을 덧붙였다.
- 【중요, 안전】Phase 6-3에서 주문 클라이언트가 .env의 전역 ENVIRONMENT를 잘못
  물려받아 실전 서버로 연결됐던 사고가 있었다(main.py 변경이력 참고) - 그 이후
  정착된 관례와 동일하게, 이 스크립트도 trade_execution_pipeline.py와 똑같이
  MIE_TRADE_ENVIRONMENT(기본값 development=모의투자)로 클라이언트를 만들고,
  어느 쪽 계좌를 보고 있는지 화면 맨 위에 눈에 띄게 표시한다 - 모의투자 수익을
  실전으로 착각하거나 그 반대로 착각하는 일을 막기 위함.

사용법:
    python3 show_portfolio_status.py
================================================================================
"""
import os
import sys
from datetime import datetime, timezone

from config.database import SessionLocal
from data.kis_client import KISClient
from db.models import TradePosition


def _fmt_money(v) -> str:
    return f"{v:,.0f}"


def main():
    trade_environment = os.getenv("MIE_TRADE_ENVIRONMENT", "development").lower()
    is_production = trade_environment == "production"

    print("=" * 100)
    if is_production:
        print("🔴 실전(운영) 계좌 - 실제 자금입니다! (.env의 MIE_TRADE_ENVIRONMENT=production)")
    else:
        print("🧪 모의투자(개발) 계좌 - 실제 자금 아님 (.env의 MIE_TRADE_ENVIRONMENT가 "
              "'production'이 아니면 항상 이쪽)")
    print(f"조회 시각: {datetime.now().isoformat(timespec='seconds')}")
    print("=" * 100)

    client = KISClient(environment=trade_environment)
    balance = client.get_balance()
    if not balance:
        print("\n❌ 잔고조회에 실패했습니다(위 get_balance() 로그 참고) - 토큰/계좌 설정을 확인하세요.")
        sys.exit(1)

    positions = balance.get("positions", [])
    cash = balance.get("cash", {})

    # DB(trade_positions, OPEN)에서 이 시스템이 기억하는 진입 맥락을 종목코드로 매칭.
    # 이 스크립트는 조회 전용이라 세션을 열고 바로 닫는다 - 아무것도 쓰지 않음.
    session = SessionLocal()
    try:
        db_positions = {
            p.ticker: p
            for p in session.query(TradePosition).filter(TradePosition.status == "OPEN").all()
        }
    finally:
        session.close()

    print(f"\n보유종목 {len(positions)}건")
    print("-" * 100)
    header = (
        f"{'종목코드':<8} {'종목명':<14} {'보유수량':>8} {'평균매입가':>10} {'현재가':>10} "
        f"{'평가금액':>14} {'평가손익':>14} {'손익율':>8} {'진입횟수':>6} {'손절가':>10}"
    )
    print(header)
    print("-" * 100)

    total_evaluation = 0.0
    total_profit_loss = 0.0
    total_purchase = 0.0

    for p in positions:
        ticker = p["ticker"]
        db_pos = db_positions.get(ticker)
        entry_count = db_pos.entry_count if db_pos else "-"
        stop_price = f"{float(db_pos.stop_price):,.0f}" if db_pos and db_pos.stop_price is not None else "-"

        purchase_amount = p["average_price"] * p["quantity"]
        total_evaluation += p["evaluation_amount"]
        total_profit_loss += p["profit_loss_amount"]
        total_purchase += purchase_amount

        print(
            f"{ticker:<8} {(p['name'] or '-'):<14} {p['quantity']:>8,} "
            f"{_fmt_money(p['average_price']):>10} {_fmt_money(p['current_price']):>10} "
            f"{_fmt_money(p['evaluation_amount']):>14} {_fmt_money(p['profit_loss_amount']):>14} "
            f"{p['profit_loss_rate']:>7.2f}% {entry_count!s:>6} {stop_price:>10}"
        )
        if db_pos is None:
            print(f"         ⚠️  trade_positions DB에 OPEN 레코드가 없음 - KIS 계좌에만 있는 보유분(수동 매매 등 가능성)")

    # DB엔 OPEN인데 KIS 잔고에는 없는 경우(수량 0으로 전량매도됐는데 DB가 아직 안 닫혔을 가능성) - 눈에 띄게 경고
    kis_tickers = {p["ticker"] for p in positions}
    for ticker, db_pos in db_positions.items():
        if ticker not in kis_tickers:
            print(f"⚠️  {ticker}: DB는 OPEN이지만 KIS 잔고엔 없음 - exit_engine이 전량청산했는데 "
                  f"상태 갱신이 누락됐을 수 있음, 확인 필요")

    print("-" * 100)
    overall_rate = (total_profit_loss / total_purchase * 100) if total_purchase else 0.0
    print(f"보유종목 평가금액 합계: {_fmt_money(total_evaluation)}원   "
          f"평가손익 합계: {_fmt_money(total_profit_loss)}원 ({overall_rate:+.2f}%)")

    print("\n" + "=" * 100)
    print("계좌 요약")
    print("-" * 100)
    cash_balance = cash.get("cash_balance", 0.0)
    total_evaluation_amount = cash.get("total_evaluation_amount", 0.0)
    print(f"예수금(현금):        {_fmt_money(cash_balance)}원")
    print(f"보유종목 평가금액:    {_fmt_money(total_evaluation)}원")
    print(f"총평가금액(총자산):   {_fmt_money(total_evaluation_amount)}원  (KIS 응답 기준 - 예수금+평가금액)")
    print("=" * 100)


if __name__ == "__main__":
    main()
