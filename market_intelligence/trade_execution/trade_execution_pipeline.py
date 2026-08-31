"""
TradeExecutionPipeline - 순수 계산기(entry_filter/diversification/position_sizer/
pyramiding/exit_engine) ↔ KIS 주문 API ↔ DB(trade_positions/trading_history) 배선
(Phase 6-3: 실제 매매 프로그램)

================================================================================
【변경 이력】
================================================================================
【2026-08-26】최초 생성
- 배경: Phase 6-1/6-2가 만든 market_intelligence/trade_execution/의 8개 순수
  계산기(analyzers/collectors와 동일한 원칙 - API/DB 호출 없음)는 "판정"만
  하고 실제로 KIS에 주문을 넣거나 DB에 포지션을 기록하지 않았다. 이 모듈이
  market_intelligence/collectors/valuation_pipeline.py 등과 같은 역할(순수
  계산기를 API/DB에 실제로 연결)을 trade_execution 쪽에서 담당한다.
- 하루 1회 실행 순서: **청산(exit) → 피라미딩(pyramid) → 신규진입(entry)**.
  문서(miev2trading.txt/miev2tradingsell.txt) 어디에도 이 세 단계의 실행
  순서가 명시돼 있지 않다 - 이 세션이 상식적인 순서로 정한 것이다(매도를
  먼저 처리해야 거기서 회수되는 현금/위험 예산이 그날의 매수 판단에 반영될
  수 있음). 다음 단계에서 사용자 확인 후 순서를 바꿀 수 있다.
- 세 파이프라인 함수(run_exit_pipeline/run_pyramiding_pipeline/run_entry_pipeline)는
  전부 "이미 준비된 시세/랭킹 데이터"를 인자로 받는다 - KIS API를 직접 호출해서
  이 데이터를 만드는 건 이 함수들 책임이 아니다(price_history_pipeline.py의
  records 파라미터와 동일한 설계 - collector/API 호출과 DB 반영 로직을
  분리해서 테스트에서 Mock 없이 순수 데이터만으로 검증 가능하게 함). 실제 시세
  조회 배선은 이 파일 맨 아래 __main__ 블록(및 build_market_data_and_candidates())
  참고 - 이 부분은 이 세션이 실제 KIS API로 검증할 수 없어 다른 파이프라인들의
  __main__ 블록과 동일하게 "합리적으로 작성했지만 라이브 검증 필요" 수준이다.
- TradePosition(db/models.py, Phase 6-3 신규 테이블) ↔ pure 계산기 dict 변환은
  position_to_dict()가 전담한다 - 계산기 모듈들의 dict 키 이름과 정확히 맞춰야
  하므로 이 파일에서 그 계약이 깨지면 여기서만 고치면 된다.
- diversify_candidates()(Phase 6-1)는 "기존 보유 포지션" 개념이 없는 순수
  함수다(그냥 리스트를 받아 그리디로 고름) - run_entry_pipeline()은 기존 보유
  종목들을 "이미 선택된 것"처럼 후보 리스트 맨 앞에 놓고 같은 함수를 호출해서
  Sector/Theme/슬롯 예산을 실제로 공유하게 만든다(코드에 자세한 설명 주석).
- 각 체결(매수/매도/피라미딩)마다 기존 TradingHistory 테이블(Phase 5 이전부터
  있던 "개별 거래 기록"용 스키마, Phase 6-1 문서가 "재활용 가능"이라고 미리
  판단해뒀던 것)에 1행씩 남긴다 - signal_source에 "ENTRY_*"/"PYRAMID_N"/
  "EXIT_*"(exit_engine의 reason 그대로)를 넣어 나중에 어떤 규칙으로 체결됐는지
  추적 가능하게 했다.
- 시장가 주문 체결가 관련 알려진 한계: place_order()가 즉시 반환하는 시점에는
  실제 체결가를 모른다(시장가 주문은 체결까지 약간의 시간차가 있고, KIS 응답도
  주문 접수 확인이지 체결 통보가 아니다) - 이 파이프라인은 주문 시점의 참조
  가격(candidate/market 딕셔너리의 current_price)을 TradingHistory.price와
  포지션의 entry_price/average_price에 그대로 쓴다. 실제 체결가와 오차가 있을
  수 있다 - 다음 단계에서 get_pending_orders()/체결내역 조회로 사후 대사(재무
  정합성 확인)하는 로직을 추가하는 것을 권장.

【2026-08-27】__main__이 KISClient를 강제로 모의투자(development)로 생성하도록 수정
  (EC2 최초 라이브 실행 로그에서 발견한 안전 문제)
- 배경: 사용자가 EC2에서 이 파일을 수동 실행(`systemctl start`)한 로그를
  공유했는데, 토큰 발급 URL이 PROD_BASE_URL(실전투자)이었다 - EC2 .env의
  ENVIRONMENT=production을 main.py(시세 수집용, 실전 서버 시세가 더 정확해서
  의도적으로 그렇게 설정됨 - 시세 조회는 계정 종류와 무관하게 안전함)뿐 아니라
  이 파일의 `KISClient()`도 그대로 물려받고 있었던 것 - 사용자가 AskUserQuestion
  에서 명시적으로 확정한 "모의투자부터 시작"과 반대. 다행히 그 실행에서는
  잔고조회가 계좌번호 형식 오류로 실패해 available_cash가 0이 되면서 실제 주문
  직전에 전부 걸러졌지만(아래 계좌번호 항목 참고), 그 우연이 없었다면 실전 계정
  으로 진짜 주문이 나갈 뻔한 상황이었다.
- 조치: data/kis_client.py의 KISClient.__init__에 environment 파라미터를
  추가했고(그 파일 변경이력 【2026-08-27】참고), 이 파일의 __main__은 이제
  `.env`의 전역 ENVIRONMENT가 아니라 **별도의 MIE_TRADE_ENVIRONMENT** 환경변수
  (기본값 "development"=모의투자)로 KISClient를 만든다. 즉 EC2의 ENVIRONMENT가
  production으로 남아 있어도(main.py 시세 수집은 그대로 실전 서버 시세를 씀)
  주문 실행 파이프라인은 사용자가 .env에 `MIE_TRADE_ENVIRONMENT=production`을
  **의식적으로 추가하지 않는 한** 항상 모의투자로만 동작한다 - 기본값이 항상
  안전한 쪽(모의투자)이 되도록 설계했다. 실전 전환은 이 한 줄을 .env에 추가하는
  분명한 결정이 되게 함으로써, 다른 목적(시세 품질)으로 설정된 환경변수에
  실수로 끌려가지 않게 했다.

【2026-08-27】build_market_data_and_candidates()의 시세 조회를 quote_client(PROD)로
  분리 - __main__ (모의투자 서버 시세 API 불안정 발견)
- 배경: 위 안전 수정을 반영한 두 번째 EC2 라이브 실행 로그에서, 토큰 발급은
  정상적으로 모의투자(DEV, openapivts.koreainvestment.com:29443) 서버로 갔지만
  (안전 수정이 의도대로 작동), get_stock_daily_chart()(개별 종목 일봉 조회,
  tr_id FHKST03010100)가 총 29종목 중 약 20종목에서 HTTP 500을 반환했다.
  같은 29종목을 첫 번째 로그(PROD 서버)에서 조회했을 때는 1종목만 실패했다.
  즉 모의투자 서버가 이 시세 조회 API를 실전 서버만큼 안정적으로 지원하지
  않는 것으로 보인다(KIS 플랫폼 자체의 동작 차이 - 이 세션의 코드 버그가
  아니다).
- 조치: KISClient 하나로 시세 조회와 주문 실행을 둘 다 처리하던 것을, 역할별로
  분리했다. build_market_data_and_candidates()는 이제 quote_client 인자를 받고
  (환경 인자 없이 만든 기본 KISClient() - main.py와 동일하게 .env의 전역
  ENVIRONMENT를 따름 - EC2에서는 production이므로 PROD 서버로 감), 반면
  run_exit_pipeline/run_pyramiding_pipeline/run_entry_pipeline(및 이들을 묶는
  run_trade_execution_cycle)에 넘기는 클라이언트는 그대로 order_client
  (MIE_TRADE_ENVIRONMENT로 강제된 모의투자 클라이언트)를 유지한다. 즉 "시세는
  읽기 전용이라 실전 서버를 써도 안전하고 실제로 더 안정적"이라는 이유로
  main.py와 동일한 선택을 했고, "주문은 절대 실전 서버로 안 나가야 한다"는
  기존 안전 수정은 그대로 유지된다. __main__ 블록도 quote_client/order_client
  두 인스턴스를 각각 생성하도록 수정했다.
- 알려진 한계: 이 함수(build_market_data_and_candidates)는 이 세션이 실제
  KIS API로 검증할 수 없었고(다른 파이프라인 __main__ 블록들과 동일한 한계),
  기존 tests/test_trade_execution_pipeline.py도 이 함수를 커버하지 않는다
  (MockKISClient가 get_stock_daily_chart()를 흉내내지 않음) - 사용자 환경에서
  라이브 재확인이 필요하다.

【2026-08-28】run_entry_pipeline()에 종목별 제외 사유 로그 추가
- 배경: 계좌번호/DEV 앱키 문제가 모두 해결된 뒤 처음으로 잔고조회가 성공한
  라이브 실행에서(예수금 10,000,000원 정상 조회) "신규진입: {'checked': 7,
  'entered': 0, ...}" 결과가 나왔다. 이번엔 이전처럼 available_cash=0 버그
  때문이 아니라(실제 예수금이 잡혔으므로) check_entry()/calculate_position()/
  split_entry_shares()/clip_shares_to_portfolio_risk() 중 어딘가에서 진짜로
  7종목이 전부 걸러진 것인데, 기존 로그는 "0건 진입"이라는 합계만 보여주고
  종목별로 왜 걸러졌는지(갭 판정? final/sector/theme 점수 미달? ATR 이상?
  사이징 결과 0주?) 전혀 보여주지 않아 이게 정상 동작인지 버그인지 사용자가
  판단할 방법이 없었다.
- 조치: for candidate in to_consider 루프의 각 continue 분기 직전에
  logger.info()로 (ticker, action, reason) 또는 실패 지점과 관련 수치를
  그대로 남기도록 추가했다. 반환값/로직은 전혀 바꾸지 않았다(로그만 추가) -
  tests/test_trade_execution_pipeline.py 17개 시나리오(fake-ORM 검증) 재확인
  결과 전부 그대로 통과.
================================================================================
"""
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from market_intelligence.trade_execution.config import TradingConfig, ExitConfig, DEFAULT_CONFIG, DEFAULT_EXIT_CONFIG
from market_intelligence.trade_execution.entry_filter import check_entry
from market_intelligence.trade_execution.diversification import diversify_candidates
from market_intelligence.trade_execution.position_sizer import calculate_position, split_entry_shares
from market_intelligence.trade_execution.pyramiding import should_add
from market_intelligence.trade_execution.portfolio_risk import clip_shares_to_portfolio_risk
from market_intelligence.trade_execution.exit_engine import analyze_exit, update_stop

logger = logging.getLogger(__name__)


def position_to_dict(position: Any) -> Dict[str, Any]:
    """TradePosition ORM 행을 pure 계산기(should_add/analyze_exit/update_stop)가
    요구하는 딕셔너리로 변환한다. Numeric 컬럼은 사용 환경에 따라 Decimal로 올 수
    있어(psycopg2) 전부 float로 캐스팅한다(hierarchical_ranking_pipeline.py의
    _to_float()와 동일한 이유 - DB 드라이버 타입이 계산기 안에서 섞이는 걸 방지)."""
    def _f(value):
        return float(value) if value is not None else None

    return {
        "entry_price": _f(position.entry_price),
        "entry_rank": position.entry_rank,
        "initial_stop_price": _f(position.initial_stop_price),
        "initial_risk_per_share": _f(position.initial_risk_per_share),
        "stop_price": _f(position.stop_price),
        "highest_price": _f(position.highest_price),
        "average_price": _f(position.average_price),
        "quantity": position.quantity,
        "entry_count": position.entry_count,
        "last_entry_price": _f(position.last_entry_price),
        "partial_profit_taken": bool(position.partial_profit_taken),
    }


def _place_order_or_dry_run(kis_client, dry_run: bool, ticker: str, side: str, quantity: int) -> Dict[str, Any]:
    """dry_run=True면 실제 KIS 호출 없이 성공을 가장한다 - 백테스트/리허설/
    테스트에서 실제 주문 없이 판정 로직만 검증하고 싶을 때 쓴다."""
    if dry_run:
        return {"success": True, "order_no": "DRY_RUN", "message": "dry_run"}
    return kis_client.place_order(ticker, side, quantity, order_type="market")


def run_exit_pipeline(
    session,
    kis_client,
    market_data_by_ticker: Dict[str, Dict[str, Any]],
    config: TradingConfig = DEFAULT_CONFIG,
    exit_config: ExitConfig = DEFAULT_EXIT_CONFIG,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """보유 중인 모든 OPEN 포지션에 exit_engine.analyze_exit()을 적용하고, SELL_ALL/
    PARTIAL_SELL이면 실제로 매도 주문을 낸다. 매도 후(또는 HOLD여서 그대로 보유
    중인) 포지션은 exit_engine.update_stop()으로 손절가를 당일 기준으로 갱신한다.

    Args:
        market_data_by_ticker: {ticker: {"current_price", "price_change_pct",
            "current_rank", "sector_score", "theme_score", "lowest_10_days",
            "current_high", "atr20"}} - exit_engine.analyze_exit()/update_stop()이
            요구하는 필드를 모두 포함해야 한다(호출부가 미리 준비 - 이 함수는
            시세 조회를 모른다). 포지션의 ticker가 이 딕셔너리에 없으면 그
            포지션은 이번 실행에서 건너뛴다(추측으로 청산 판정을 하지 않음).

    Returns:
        {"checked", "sold_all", "partial_sold", "stops_updated",
         "skipped_no_market_data", "errors": [{"ticker","action","message"}]}
    """
    from db.models import TradePosition, TradingHistory

    positions = session.query(TradePosition).filter(TradePosition.status == "OPEN").all()
    result = {
        "checked": 0, "sold_all": 0, "partial_sold": 0, "stops_updated": 0,
        "skipped_no_market_data": 0, "errors": [],
    }

    for position in positions:
        result["checked"] += 1
        market = market_data_by_ticker.get(position.ticker)
        if not market:
            result["skipped_no_market_data"] += 1
            continue

        pos_dict = position_to_dict(position)
        action, reason, fraction = analyze_exit(pos_dict, market, exit_config)
        current_price = market.get("current_price")

        if action == "SELL_ALL":
            qty = position.quantity
            order_result = _place_order_or_dry_run(kis_client, dry_run, position.ticker, "sell", qty)
            if order_result.get("success"):
                position.status = "CLOSED"
                position.closed_at = datetime.now(timezone.utc)
                position.close_price = current_price
                position.close_reason = reason
                session.add(TradingHistory(
                    ticker=position.ticker, trade_type="SELL", quantity=qty,
                    price=current_price,
                    total_amount=int(qty * current_price) if current_price else None,
                    signal_source=f"EXIT_{reason}", result="executed",
                ))
                result["sold_all"] += 1
            else:
                result["errors"].append({"ticker": position.ticker, "action": "SELL_ALL", "message": order_result.get("message")})

        elif action == "PARTIAL_SELL":
            sell_qty = int(position.quantity * fraction)
            if sell_qty <= 0 and position.quantity > 0:
                sell_qty = 1  # 반올림으로 0이 되면 최소 1주는 실행(방향성을 무효화하지 않기 위함)
            sell_qty = min(sell_qty, position.quantity)

            if sell_qty > 0:
                order_result = _place_order_or_dry_run(kis_client, dry_run, position.ticker, "sell", sell_qty)
                if order_result.get("success"):
                    session.add(TradingHistory(
                        ticker=position.ticker, trade_type="SELL", quantity=sell_qty,
                        price=current_price,
                        total_amount=int(sell_qty * current_price) if current_price else None,
                        signal_source=f"EXIT_{reason}", result="executed",
                    ))
                    remaining = position.quantity - sell_qty
                    if remaining <= 0:
                        position.status = "CLOSED"
                        position.closed_at = datetime.now(timezone.utc)
                        position.close_price = current_price
                        position.close_reason = reason
                    else:
                        position.quantity = remaining
                        position.partial_profit_taken = True
                    result["partial_sold"] += 1
                else:
                    result["errors"].append({"ticker": position.ticker, "action": "PARTIAL_SELL", "message": order_result.get("message")})

        # HOLD였거나, 부분매도 후에도 포지션이 남아있으면 손절가를 당일 기준으로 갱신한다.
        # (전량 청산됐으면 더 이상 손절가를 관리할 포지션이 없으므로 건너뜀)
        if position.status == "OPEN":
            atr20 = market.get("atr20")
            current_high = market.get("current_high", current_price)
            new_stop = update_stop(pos_dict, current_high=current_high, atr20=atr20, current_price=current_price, config=exit_config)
            if new_stop is not None:
                position.stop_price = new_stop["stop_price"]
                position.highest_price = new_stop["highest_price"]
                result["stops_updated"] += 1

    session.commit()
    logger.info(
        f"✅ 청산 파이프라인 완료: {result['checked']}건 점검, "
        f"전량청산 {result['sold_all']}건, 부분익절 {result['partial_sold']}건, "
        f"손절가 갱신 {result['stops_updated']}건"
    )
    return result


def run_pyramiding_pipeline(
    session,
    kis_client,
    market_data_by_ticker: Dict[str, Dict[str, Any]],
    config: TradingConfig = DEFAULT_CONFIG,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """보유 중인 모든 OPEN 포지션에 pyramiding.should_add()를 적용하고, ADD면
    추가매수 주문을 낸다. run_exit_pipeline()과 같은 market_data_by_ticker
    형식을 그대로 받는다(should_add()가 쓰는 current_price/atr20/current_rank/
    sector_score/theme_score만 읽고 나머지 키는 무시 - 굳이 별도 딕셔너리를
    안 만들어도 되도록).

    회차별 매수 수량은 position.target_shares(최초 진입 시 계산해 고정해 둔
    목표 총수량)를 split_entry_shares()로 나눠서 정한다 - 매번 새로
    calculate_position()을 부르지 않는다(문서의 설계: 위험 예산은 최초 진입
    시점에 확정되고, 피라미딩은 그 예산을 회차별로 "풀어주는" 것이지 위험을
    추가로 늘리는 게 아니다).

    Returns:
        {"checked", "added", "skipped_no_candidate_data", "errors": [{"ticker","message"}]}
    """
    from db.models import TradePosition, TradingHistory

    positions = session.query(TradePosition).filter(TradePosition.status == "OPEN").all()
    result = {"checked": 0, "added": 0, "skipped_no_candidate_data": 0, "errors": []}

    for position in positions:
        result["checked"] += 1
        candidate = market_data_by_ticker.get(position.ticker)
        if not candidate:
            result["skipped_no_candidate_data"] += 1
            continue

        pos_dict = position_to_dict(position)
        action, reason = should_add(pos_dict, candidate, config)
        if action != "ADD":
            continue

        next_seq = position.entry_count + 1
        add_qty = split_entry_shares(position.target_shares or 0, next_seq, config)
        if add_qty <= 0:
            continue

        current_price = candidate.get("current_price")
        order_result = _place_order_or_dry_run(kis_client, dry_run, position.ticker, "buy", add_qty)
        if order_result.get("success"):
            old_qty = position.quantity or 0
            old_avg = float(position.average_price) if position.average_price is not None else float(position.entry_price)
            new_qty = old_qty + add_qty
            new_avg = ((old_avg * old_qty) + (current_price * add_qty)) / new_qty if new_qty > 0 else old_avg

            position.quantity = new_qty
            position.average_price = new_avg
            position.entry_count = next_seq
            position.last_entry_price = current_price

            session.add(TradingHistory(
                ticker=position.ticker, trade_type="BUY", quantity=add_qty,
                price=current_price,
                total_amount=int(add_qty * current_price) if current_price else None,
                signal_source=f"PYRAMID_{next_seq}", result="executed",
            ))
            result["added"] += 1
        else:
            result["errors"].append({"ticker": position.ticker, "message": order_result.get("message")})

    session.commit()
    logger.info(f"✅ 피라미딩 파이프라인 완료: {result['checked']}건 점검, {result['added']}건 추가매수")
    return result


def run_entry_pipeline(
    session,
    kis_client,
    ranked_candidates: List[Dict[str, Any]],
    available_cash: Optional[float] = None,
    config: TradingConfig = DEFAULT_CONFIG,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """계층형 랭킹 후보 리스트에서 신규 진입 대상을 골라 매수하고 TradePosition을
    새로 만든다.

    Args:
        ranked_candidates: final_score/overall_rank 내림차순(좋은 순)으로 이미
            정렬된 리스트. 각 원소는 최소 ticker, market, sector, primary_theme,
            final_score, sector_score, theme_score, overall_rank, previous_close,
            current_price, atr20 키를 가져야 한다(entry_filter.check_entry() +
            diversify_candidates() + position_sizer.calculate_position()이
            요구하는 필드를 합친 것). 이미 config.total_candidates개로 잘려있지
            않아도 이 함수가 앞에서부터 그만큼만 본다.
        available_cash: None이면 kis_client.get_balance()로 예수금을 조회한다.
            테스트/시뮬레이션에서는 직접 넘긴다.

    이미 보유 중인 종목은 diversify_candidates() 호출 시 "이미 선택된 것"으로
    앞세워 넣어서 Sector/Theme/최대보유종목수 예산을 실제로 나눠 쓰게 만든다
    (diversify_candidates() 자체는 기존 포지션을 모르는 순수 함수 - 자세한 설명은
    파일 상단 변경이력 참고). 이번 실행에서 새로 승인한 포지션도 즉시
    risk_positions에 누적해서, 뒤에 나오는 후보의 포트폴리오 위험 클리핑에
    반영되게 한다(그렇지 않으면 여러 종목을 한 번에 승인할 때 위험 총합이
    한도를 넘을 수 있음).

    Returns:
        {"checked", "entered", "skipped_no_slot", "errors": [{"ticker","message"}]}
    """
    from db.models import TradePosition, TradingHistory

    open_positions = session.query(TradePosition).filter(TradePosition.status == "OPEN").all()
    open_tickers = {p.ticker for p in open_positions}

    result = {"checked": 0, "entered": 0, "skipped_no_slot": 0, "errors": []}

    remaining_slots = config.max_positions - len(open_positions)
    if remaining_slots <= 0:
        result["skipped_no_slot"] = len(ranked_candidates)
        logger.info("ℹ️  최대 보유 종목 수에 도달해 신규 진입을 건너뜁니다")
        return result

    if available_cash is None:
        balance = kis_client.get_balance()
        available_cash = balance.get("cash", {}).get("cash_balance", 0.0)

    existing_as_stocks = [
        {"ticker": p.ticker, "sector": p.sector, "primary_theme": p.primary_theme, "_existing": True}
        for p in open_positions
    ]
    new_candidates = [
        dict(c, _existing=False) for c in ranked_candidates[:config.total_candidates]
        if c.get("ticker") not in open_tickers
    ]
    combined = existing_as_stocks + new_candidates
    selected = diversify_candidates(combined, config.max_positions, config.max_per_sector, config.max_per_theme)
    to_consider = [s for s in selected if not s.get("_existing")]

    risk_positions = [
        {"quantity": p.quantity, "average_price": float(p.average_price), "stop_price": float(p.stop_price)}
        for p in open_positions
        if p.quantity and p.average_price is not None and p.stop_price is not None
    ]

    for candidate in to_consider:
        result["checked"] += 1
        ticker = candidate.get("ticker")

        action, reason = check_entry(candidate, config)
        if action in ("WAIT", "NO_ENTRY"):
            # 【2026-08-28 추가, print()로 작성】entered=0이 "진짜 필터링"인지 "숨은
            # 버그"인지 사용자가 로그만 보고 구분할 방법이 없어 종목별 사유를 남기기로
            # 했다. kis_client.py가 이미 print()로 안정적으로 로그를 남기고 있어서
            # 같은 방식을 따랐다.
            # 【2026-08-31 정정】당시엔 "logger.info()가 로그 파일에 전혀 안 찍힌다"고
            # (잘못) 결론 내렸었는데, 2026-08-31 00:05 라이브 로그를 다시 보니 실제
            # 원인은 그게 아니라 **stdout 블록 버퍼링으로 인한 순서 뒤섞임**이었다 -
            # print()가 파일로 리다이렉트되면 버퍼링돼 한참 늦게(또는 프로세스 종료
            # 시점에) flush되는 반면, logging의 기본 StreamHandler(stderr)는 즉시
            # flush되어, 실제로는 나중에 실행된 logger.info() 줄이 로그 파일에는 더
            # 먼저 찍히는 것처럼 보였다(tail -100/-150으로 볼 때 원하는 줄이 있는
            # 근처가 아니었을 뿐 - 아예 안 찍힌 게 아니었음). 근본 수정은
            # deploy/*.service 전체에 Environment="PYTHONUNBUFFERED=1"을 추가하는
            # 것으로 처리(각 서비스 파일 변경이력 참고) - 이 print() 문들은 여전히
            # 유효하고 정상 동작하므로 되돌리지 않는다.
            print(f"⏭️  {ticker}: 진입 보류/제외 - {action} ({reason})")
            continue

        entry_price = candidate.get("current_price")
        atr20 = candidate.get("atr20")
        sized = calculate_position(entry_price, atr20, available_cash, config)
        if sized is None:
            print(f"⏭️  {ticker}: 포지션 사이징 실패(calculate_position=None) - "
                  f"entry_price={entry_price}, atr20={atr20}, available_cash={available_cash}")
            continue

        target_shares = sized["target_shares"]
        if action == "REDUCE":
            target_shares = int(target_shares * config.reduce_position_ratio)
        if target_shares <= 0:
            print(f"⏭️  {ticker}: target_shares<=0 ({target_shares}) - 사이징 결과 0주")
            continue

        first_tranche = split_entry_shares(target_shares, 1, config)
        if first_tranche <= 0:
            print(f"⏭️  {ticker}: 1차 진입 수량<=0 ({first_tranche}, target_shares={target_shares})")
            continue

        risk_per_share = sized["risk_per_share"]
        buy_qty = clip_shares_to_portfolio_risk(first_tranche, risk_per_share, risk_positions, config)
        if buy_qty <= 0:
            print(f"⏭️  {ticker}: 포트폴리오 리스크 클리핑 후 매수 수량<=0 "
                  f"(1차수량={first_tranche}, risk_per_share={risk_per_share})")
            continue

        order_result = _place_order_or_dry_run(kis_client, dry_run, ticker, "buy", buy_qty)
        if not order_result.get("success"):
            result["errors"].append({"ticker": ticker, "message": order_result.get("message")})
            continue

        stop_price = sized["stop_price"]
        session.add(TradePosition(
            ticker=ticker, market=candidate.get("market"), sector=candidate.get("sector"),
            primary_theme=candidate.get("primary_theme"), status="OPEN",
            entry_price=entry_price, entry_rank=candidate.get("overall_rank"),
            initial_stop_price=stop_price, initial_risk_per_share=risk_per_share,
            stop_price=stop_price, highest_price=entry_price,
            average_price=entry_price, quantity=buy_qty, target_shares=target_shares,
            entry_count=1, last_entry_price=entry_price, partial_profit_taken=False,
        ))
        session.add(TradingHistory(
            ticker=ticker, trade_type="BUY", quantity=buy_qty, price=entry_price,
            total_amount=int(buy_qty * entry_price) if entry_price else None,
            signal_source=f"ENTRY_{reason}",
            confidence=(candidate.get("final_score") / 100.0) if candidate.get("final_score") is not None else None,
            result="executed",
        ))

        available_cash -= buy_qty * entry_price
        risk_positions.append({"quantity": buy_qty, "average_price": entry_price, "stop_price": stop_price})
        result["entered"] += 1

        if len(open_tickers) + result["entered"] >= config.max_positions:
            break

    session.commit()
    logger.info(f"✅ 신규진입 파이프라인 완료: {result['checked']}건 검토, {result['entered']}건 진입")
    return result


def run_trade_execution_cycle(
    session,
    kis_client,
    market_data_by_ticker: Dict[str, Dict[str, Any]],
    ranked_candidates: List[Dict[str, Any]],
    available_cash: Optional[float] = None,
    config: TradingConfig = DEFAULT_CONFIG,
    exit_config: ExitConfig = DEFAULT_EXIT_CONFIG,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """하루 1회 실행되는 전체 사이클 - 청산 → 피라미딩 → 신규진입 순서로 세
    파이프라인을 그대로 이어붙인다(순서를 정한 이유는 파일 상단 변경이력 참고)."""
    exit_result = run_exit_pipeline(session, kis_client, market_data_by_ticker, config, exit_config, dry_run)
    pyramid_result = run_pyramiding_pipeline(session, kis_client, market_data_by_ticker, config, dry_run)
    entry_result = run_entry_pipeline(session, kis_client, ranked_candidates, available_cash, config, dry_run)
    return {"exit": exit_result, "pyramiding": pyramid_result, "entry": entry_result}


def build_market_data_and_candidates(session, quote_client, config: TradingConfig = DEFAULT_CONFIG):
    """실제 KIS 시세 + DB(StockPriceHistory/StockHierarchicalScore)로
    market_data_by_ticker/ranked_candidates를 조립하는 라이브 배선 헬퍼.

    Args:
        quote_client: **시세 조회 전용** KISClient. 【2026-08-27 발견, 아래
            변경이력 참고】모의투자(DEV) 서버는 get_stock_daily_chart() 같은
            개별 종목 일봉 조회 API를 실전(PROD) 서버만큼 안정적으로 지원하지
            않는다(사용자의 실제 라이브 실행에서 29종목 중 20종목이 HTTP 500으로
            실패 - 같은 종목들이 PROD에서는 1종목만 빼고 전부 성공했었음).
            그래서 이 함수는 반드시 environment="production"(또는 인자 없이
            생성한 기본 KISClient - main.py와 동일한 설정)으로 만든 클라이언트를
            받아야 한다. 주문 실행(place_order/get_balance)에 쓰는 클라이언트
            (모의투자로 강제된 것)와는 별개의 인스턴스여야 한다 - __main__ 블록
            참고.

    【주의】이 함수는 이 세션이 실제 KIS API/RDS로 검증할 수 없었다(다른 파일들의
    __main__ 블록과 동일한 한계 - price_history_pipeline.py 상단 변경이력 참고).
    run_exit_pipeline()/run_pyramiding_pipeline()/run_entry_pipeline() 자체는
    이 함수에 의존하지 않고 SQLite로 단위테스트가 끝났지만, 이 함수는 사용자
    환경에서 반드시 라이브 확인이 필요하다.

    - 보유 중(OPEN) 포지션 + 최신 계층형 랭킹(StockHierarchicalScore, 상위
      config.total_candidates개)의 종목마다 quote_client.get_stock_daily_chart()로
      최근 시세를 받아 atr.compute_atr()/exit_engine.compute_lowest_low()를
      계산한다.
    - current_rank/sector_score/theme_score는 최신 StockHierarchicalScore 배치에서
      가져온다 - 보유 포지션인데 오늘 랭킹에 아예 없는 종목(상장폐지/거래정지 등)은
      market_data에서 빠지므로 run_exit_pipeline()이 자동으로 건너뛴다(추측하지 않음).
    - price_change_pct(긴급청산 판정용)는 최근 2일 종가로 계산한다
      ((오늘종가-어제종가)/어제종가*100) - 문서가 "당일 등락률"이라고만 하고
      계산식을 안 줘서 이 세션이 가장 일반적인 정의를 골랐다.
    """
    from db.models import TradePosition, StockHierarchicalScore
    from market_intelligence.trade_execution.atr import compute_atr
    from market_intelligence.trade_execution.exit_engine import compute_lowest_low

    latest_ts = session.query(StockHierarchicalScore.timestamp).order_by(StockHierarchicalScore.timestamp.desc()).first()
    ranking_rows = []
    if latest_ts:
        ranking_rows = (
            session.query(StockHierarchicalScore)
            .filter(StockHierarchicalScore.timestamp == latest_ts[0])
            .order_by(StockHierarchicalScore.overall_rank.asc())
            .all()
        )
    ranking_by_ticker = {r.ticker: r for r in ranking_rows}

    open_positions = session.query(TradePosition).filter(TradePosition.status == "OPEN").all()
    open_tickers = {p.ticker for p in open_positions}
    candidate_tickers = [r.ticker for r in ranking_rows[:config.total_candidates]]

    all_tickers = sorted(open_tickers | set(candidate_tickers))

    market_data_by_ticker: Dict[str, Dict[str, Any]] = {}
    for ticker in all_tickers:
        chart = quote_client.get_stock_daily_chart(ticker, days=config.atr_period + 15)
        closes = chart.get("closes") or []
        highs = chart.get("highs") or []
        lows = chart.get("lows") or []
        if len(closes) < config.atr_period + 1:
            continue  # ATR 계산에 필요한 최소 데이터가 없음 - 추측하지 않고 건너뜀

        price_rows = [{"high": h, "low": l, "close": c} for h, l, c in zip(highs, lows, closes)]
        atr20 = compute_atr(price_rows, period=config.atr_period)
        lowest_10 = compute_lowest_low(price_rows, period=10)
        current_price = closes[-1]
        previous_close = closes[-2] if len(closes) >= 2 else None
        price_change_pct = ((current_price - previous_close) / previous_close * 100) if previous_close else None

        rank_row = ranking_by_ticker.get(ticker)

        market_data_by_ticker[ticker] = {
            "current_price": current_price,
            "current_high": highs[-1] if highs else current_price,
            "previous_close": previous_close,
            "price_change_pct": price_change_pct,
            "atr20": atr20,
            "lowest_10_days": lowest_10,
            "current_rank": rank_row.overall_rank if rank_row else None,
            "sector_score": float(rank_row.sector_score) if rank_row and rank_row.sector_score is not None else None,
            "theme_score": float(rank_row.theme_score) if rank_row and rank_row.theme_score is not None else None,
            "final_score": float(rank_row.final_score) if rank_row and rank_row.final_score is not None else None,
        }

    ranked_candidates = []
    for r in ranking_rows[:config.total_candidates]:
        data = market_data_by_ticker.get(r.ticker)
        if not data:
            continue
        ranked_candidates.append({
            "ticker": r.ticker, "market": r.market, "sector": r.sector,
            "primary_theme": r.primary_theme, "overall_rank": r.overall_rank,
            "final_score": data["final_score"], "sector_score": data["sector_score"],
            "theme_score": data["theme_score"], "previous_close": data["previous_close"],
            "current_price": data["current_price"], "atr20": data["atr20"],
        })

    return market_data_by_ticker, ranked_candidates


if __name__ == "__main__":
    import os

    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")

    from config.database import SessionLocal
    from data.kis_client import KISClient

    # 【안전 기본값 - 2026-08-27】.env의 전역 ENVIRONMENT(main.py 시세 수집용,
    # EC2에서 production으로 설정돼 있음)를 그대로 물려받지 않는다. 이 파이프라인은
    # 실제 주문을 내므로 별도의 MIE_TRADE_ENVIRONMENT를 쓰고, 이 변수가 없으면
    # 항상 "development"(모의투자)로 시작한다 - 실전 전환은 .env에
    # MIE_TRADE_ENVIRONMENT=production을 명시적으로 추가해야만 일어난다.
    # 자세한 경위는 파일 상단 변경이력 【2026-08-27】참고.
    trade_environment = os.getenv("MIE_TRADE_ENVIRONMENT", "development").lower()
    print(f"⚠️  매매 실행 환경: {trade_environment} "
          f"({'실전투자 - 진짜 주문' if trade_environment == 'production' else '모의투자'})")

    # 【2026-08-27 추가】시세 조회용 quote_client와 주문 실행용 order_client를
    # 분리한다. 사용자의 두 번째 라이브 실행 로그에서 모의투자(DEV) 서버가
    # get_stock_daily_chart()의 약 20/29종목에서 HTTP 500을 반환한 반면(같은
    # 종목이 PROD에서는 1종목만 실패), 시세 조회는 계속 PROD로 보내는 것이
    # 안전하고 검증된 경로다. environment 인자 없이 KISClient()를 만들면
    # main.py와 동일하게 기존 .env의 전역 ENVIRONMENT(=production)를 따르므로
    # quote_client는 항상 PROD를 향한다. 반면 order_client는 위에서 계산한
    # trade_environment(기본값 development=모의투자)를 명시적으로 강제해
    # 실주문은 사용자가 MIE_TRADE_ENVIRONMENT=production을 직접 추가하기 전엔
    # 절대 실전 서버로 가지 않는다.
    quote_client = KISClient()
    order_client = KISClient(environment=trade_environment)

    session = SessionLocal()
    try:
        market_data_by_ticker, ranked_candidates = build_market_data_and_candidates(session, quote_client)
        result = run_trade_execution_cycle(session, order_client, market_data_by_ticker, ranked_candidates)
        print(f"\n청산: {result['exit']}")
        print(f"피라미딩: {result['pyramiding']}")
        print(f"신규진입: {result['entry']}")
    finally:
        session.close()
