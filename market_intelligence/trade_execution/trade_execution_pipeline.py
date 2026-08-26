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
            continue

        entry_price = candidate.get("current_price")
        atr20 = candidate.get("atr20")
        sized = calculate_position(entry_price, atr20, available_cash, config)
        if sized is None:
            continue

        target_shares = sized["target_shares"]
        if action == "REDUCE":
            target_shares = int(target_shares * config.reduce_position_ratio)
        if target_shares <= 0:
            continue

        first_tranche = split_entry_shares(target_shares, 1, config)
        if first_tranche <= 0:
            continue

        risk_per_share = sized["risk_per_share"]
        buy_qty = clip_shares_to_portfolio_risk(first_tranche, risk_per_share, risk_positions, config)
        if buy_qty <= 0:
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


def build_market_data_and_candidates(session, kis_client, config: TradingConfig = DEFAULT_CONFIG):
    """실제 KIS 시세 + DB(StockPriceHistory/StockHierarchicalScore)로
    market_data_by_ticker/ranked_candidates를 조립하는 라이브 배선 헬퍼.

    【주의】이 함수는 이 세션이 실제 KIS API/RDS로 검증할 수 없었다(다른 파일들의
    __main__ 블록과 동일한 한계 - price_history_pipeline.py 상단 변경이력 참고).
    run_exit_pipeline()/run_pyramiding_pipeline()/run_entry_pipeline() 자체는
    이 함수에 의존하지 않고 SQLite로 단위테스트가 끝났지만, 이 함수는 사용자
    환경에서 반드시 라이브 확인이 필요하다.

    - 보유 중(OPEN) 포지션 + 최신 계층형 랭킹(StockHierarchicalScore, 상위
      config.total_candidates개)의 종목마다 kis_client.get_stock_daily_chart()로
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
        chart = kis_client.get_stock_daily_chart(ticker, days=config.atr_period + 15)
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
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")

    from config.database import SessionLocal
    from data.kis_client import KISClient

    session = SessionLocal()
    try:
        kis_client = KISClient()
        market_data_by_ticker, ranked_candidates = build_market_data_and_candidates(session, kis_client)
        result = run_trade_execution_cycle(session, kis_client, market_data_by_ticker, ranked_candidates)
        print(f"\n청산: {result['exit']}")
        print(f"피라미딩: {result['pyramiding']}")
        print(f"신규진입: {result['entry']}")
    finally:
        session.close()
