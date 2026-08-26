"""보유 포지션 청산(Exit) 판정 - 손절/긴급청산/부분익절/트레일링스톱/전량청산 (Phase 6-2)

================================================================================
【배경】
================================================================================
사용자가 업로드한 두 번째 문서(miev2tradingsell.txt)의 "11. 가장 추천하는
전체 Exit Engine"(PositionExitAnalyzer.analyze)과 "12. 매일 손절가를 자동으로
업데이트"(StopManager.update_stop)를 그대로 코드로 옮긴 것. 숫자/우선순위는
전부 문서에서 그대로 가져왔다 - 이 세션이 임의로 정한 값이 아니다. 세부 근거와
문서 내부 불일치(§13 Day15 트레일링 스톱 예시 수치)에 대한 설명은
config.py의 ExitConfig 변경 이력 참고.

================================================================================
【기존 pyramiding.check_stop()과의 관계】
================================================================================
pyramiding.py의 check_stop()은 Phase 6-1 시점에 문서에 정확한 전량청산 규칙이
없어서 "손절가 도달"만 보는 단순 버전으로 남겨뒀던 것이다(그 파일의 docstring
참고). 이 모듈의 analyze_exit()이 그 자리를 대체하는 상위 호환 버전이다 -
check_stop()의 손절가 체크 로직을 포함하면서, 긴급청산/분석논리붕괴/부분익절/
터틀청산까지 우선순위대로 전부 판정한다. pyramiding.check_stop()은 하위 호환을
위해 그대로 남겨두되, 실제 파이프라인 배선 시에는 이 모듈의 analyze_exit()을
써야 한다.

================================================================================
【필드명 통합: stop_price 하나로 초기손절/트레일링스톱을 함께 관리】
================================================================================
문서 §11 analyze() 코드는 "② 초기 손절" 단계에서 position.stop_price를,
"⑦ ATR Trailing Stop" 단계에서 별도의 position.trailing_stop_price를
체크한다. 그런데 문서 §12 StopManager.update_stop()은 오직 position.stop_price
하나만 갱신하고(항상 max()로 위로만) 별도 trailing_stop_price 필드를 만들지
않는다 - 즉 문서 스스로 두 필드를 통일하지 않은 것이다.

이 구현은 stop_price 하나로 통합한다: update_stop()이 매일 이 값을
(최초 손절 → 본전 보호 → ATR 트레일링) 순서로 위로만 갱신하고, analyze_exit()은
current_price <= stop_price 하나만 체크한다. 이렇게 해도 의미는 완전히
동일하다 - stop_price가 아직 최초 계산값 그대로면 "초기 손절"이 발동한 것이고,
그 사이에 update_stop()이 한 번이라도 올렸다면 "트레일링 스톱"이 발동한
것이다. 어느 쪽인지는 position["initial_stop_price"](최초 계산되고 이후
절대 바뀌지 않는 값)와 현재 stop_price를 비교해서 구분해 반환한다.

================================================================================
【position / market 딕셔너리 필드】
================================================================================
position (계좌에 보유 중인 포지션):
    entry_price            진입 평균단가
    entry_rank              진입 시점의 계층형 랭킹(overall_rank)
    initial_stop_price      최초 계산된 손절가(진입 시 1회 계산 후 불변)
    stop_price               현재 유효한 손절가(update_stop()이 위로만 갱신)
    initial_risk_per_share  1주당 최초 위험(entry_price - initial_stop_price) - R 배수 계산의 분모
    highest_price            보유 기간 중 최고가(트레일링 스톱 계산용)
    partial_profit_taken    이미 +2R 부분 익절을 실행했는지 여부(bool, 기본 False)

market (오늘자 시세/랭킹 데이터 - 파이프라인이 채워서 전달):
    current_price            오늘 현재가(또는 종가)
    price_change_pct         전일 종가 대비 당일 등락률(%) - 급락 판정용.
                              gap_filter.compute_gap_pct()와 계산식은 같지만
                              용도가 다르므로(시가 갭이 아니라 당일 등락) 이
                              모듈은 재계산하지 않고 호출측이 넘겨준 값을 쓴다.
    current_rank              오늘의 계층형 overall_rank
    sector_score              오늘의 Sector 점수
    theme_score                오늘의 Theme 점수
    lowest_10_days            최근 10일(당일 제외 여부는 호출측 결정) 최저가
                              - compute_lowest_low()로 계산 가능

모든 필드는 없으면(None) 해당 판정 단계를 안전하게 건너뛴다(추측하지 않는다) -
기존 atr.py/entry_filter.py/pyramiding.py와 동일한 원칙.
"""
from typing import Any, Dict, List, Optional, Tuple

from market_intelligence.trade_execution.config import ExitConfig, DEFAULT_EXIT_CONFIG


def compute_lowest_low(price_rows: List[Dict[str, Any]], period: int = 10) -> Optional[float]:
    """최근 `period`일 최저가(터틀식 전량청산 판정용).

    price_rows는 과거->최근 순으로 정렬된 {"low": ...} 딕셔너리 리스트라고
    가정한다(atr.compute_atr()과 동일한 순서 가정). 데이터가 period개
    미만이거나 최근 period개 중 low가 하나라도 결측이면 None을 반환한다 -
    일부만으로 "최저가"를 추측하지 않는다."""
    if not price_rows or len(price_rows) < period:
        return None
    recent = price_rows[-period:]
    lows = [row.get("low") for row in recent]
    if any(low is None for low in lows):
        return None
    return min(lows)


def analyze_exit(
    position: Dict[str, Any],
    market: Dict[str, Any],
    config: ExitConfig = DEFAULT_EXIT_CONFIG,
) -> Tuple[str, str, float]:
    """문서 §11 PositionExitAnalyzer.analyze()를 그대로 이식.

    반환값: (action, reason, fraction)
      action: "HOLD" | "PARTIAL_SELL" | "SELL_ALL"
      reason: 판정 사유 문자열(문서의 ExitReason과 1:1 대응, 단 이 코드베이스의
              다른 모듈(check_entry/should_add 등)과 스타일을 맞추기 위해
              Enum이 아닌 일반 문자열로 반환한다)
      fraction: 매도할 보유 수량 비율(SELL_ALL=1.0, PARTIAL_SELL=config.partial_sell_ratio,
                HOLD=0.0) - 호출측이 quantity * fraction으로 매도 수량을 계산

    우선순위(문서 §2/§11과 동일, 위에서부터 순서대로 최초로 만족하는 조건 하나만
    적용):
      1순위 긴급 청산(EMERGENCY_EXIT)
      2순위 손절(INITIAL_STOP 또는 TRAILING_STOP - stop_price 통합, 위 docstring 참고)
      3순위 MIE 분석 논리 붕괴(RANK_COLLAPSE / SECTOR_THEME_COLLAPSE)
      4순위 +2R 부분 익절(TAKE_PROFIT_2R)
      5순위 터틀 10일 최저가 이탈(TURTLE_10DAY_EXIT)
      6순위 정상 보유(HOLD/NONE)
    """
    current_price = market.get("current_price")
    if current_price is None:
        return "HOLD", "MISSING_CURRENT_PRICE", 0.0

    # 1순위: 긴급 청산 (급락)
    price_change_pct = market.get("price_change_pct")
    if price_change_pct is not None and price_change_pct <= config.emergency_loss_pct:
        return "SELL_ALL", "EMERGENCY_EXIT", 1.0

    # 2순위: 손절 (초기 손절 또는 트레일링 스톱 - stop_price 하나로 통합)
    stop_price = position.get("stop_price")
    if stop_price is not None and current_price <= stop_price:
        initial_stop_price = position.get("initial_stop_price")
        if initial_stop_price is not None and stop_price == initial_stop_price:
            return "SELL_ALL", "INITIAL_STOP", 1.0
        return "SELL_ALL", "TRAILING_STOP", 1.0

    # 3순위: MIE 분석 논리 붕괴
    entry_rank = position.get("entry_rank")
    current_rank = market.get("current_rank")
    if entry_rank is not None and current_rank is not None:
        if (current_rank - entry_rank) >= config.max_rank_drop:
            return "SELL_ALL", "RANK_COLLAPSE", 1.0

    sector_score = market.get("sector_score")
    theme_score = market.get("theme_score")
    if sector_score is not None and theme_score is not None:
        if sector_score < config.minimum_sector_score and theme_score < config.minimum_theme_score:
            return "SELL_ALL", "SECTOR_THEME_COLLAPSE", 1.0

    # 4순위: +2R 부분 익절 (이미 실행했으면 재실행하지 않음)
    entry_price = position.get("entry_price")
    initial_risk_per_share = position.get("initial_risk_per_share")
    partial_profit_taken = position.get("partial_profit_taken", False)
    if (
        not partial_profit_taken
        and entry_price is not None
        and initial_risk_per_share is not None
        and initial_risk_per_share > 0
    ):
        profit_r = (current_price - entry_price) / initial_risk_per_share
        if profit_r >= config.partial_take_profit_r:
            return "PARTIAL_SELL", "TAKE_PROFIT_2R", config.partial_sell_ratio

    # 5순위: 터틀 10일 최저가 이탈
    lowest_10_days = market.get("lowest_10_days")
    if lowest_10_days is not None and current_price < lowest_10_days:
        return "SELL_ALL", "TURTLE_10DAY_EXIT", 1.0

    # 6순위: 정상 보유
    return "HOLD", "NONE", 0.0


def get_trailing_atr_multiple(profit_r: float, config: ExitConfig = DEFAULT_EXIT_CONFIG) -> Optional[float]:
    """문서 §8 get_trailing_atr_multiple() 그대로. 수익 R배수에 따라 트레일링
    스톱에 쓸 ATR 배수를 결정한다 - 수익이 클수록(4R 이상) 더 타이트하게
    좁혀서(2.5배) 이미 확보한 수익을 더 강하게 보호한다.

    trailing_start_r 미만이면 아직 ATR 트레일링을 적용하지 않으므로 None."""
    if profit_r < config.trailing_start_r:
        return None
    elif profit_r < config.tight_trailing_trigger_r:
        return config.trailing_atr_multiple
    else:
        return config.tight_trailing_atr_multiple


def calculate_trailing_stop(current_stop: float, highest_price: float, atr20: float, atr_multiple: float) -> float:
    """문서 §7 calculate_trailing_stop() 그대로. 후보 손절가(최고가 - ATR*배수)를
    계산하되, 반드시 max(기존 손절가, 후보 손절가)로 절대 손절가를 낮추지
    않는다 - 문서가 "이 max()가 매우 중요합니다"라고 강조한 부분."""
    candidate_stop = highest_price - atr20 * atr_multiple
    return max(current_stop, candidate_stop)


def update_stop(
    position: Dict[str, Any],
    current_high: Optional[float],
    atr20: Optional[float],
    current_price: Optional[float],
    config: ExitConfig = DEFAULT_EXIT_CONFIG,
) -> Optional[Dict[str, float]]:
    """문서 §12 StopManager.update_stop()을 그대로 이식. 매일 장 마감 후(또는
    파이프라인 실행 시점) 호출해 손절가를 위로만 갱신한다.

    순서(문서 그대로): 최고가 갱신 -> profit_r 계산 -> (+1R 이상이면 본전 보호)
    -> (+2R/+4R 이상이면 ATR 트레일링, get_trailing_atr_multiple()로 배수 결정).
    문서 원본 코드는 +2R 단계와 +4R 단계를 별도의 두 if문으로 순차 적용하지만,
    +4R 이상 구간에서는 2.5배 후보 손절가가 3배 후보 손절가보다 항상 더
    높다(같은 highest_price에서 빼는 배수가 작을수록 결과가 크다) - 즉 두
    번째 max()가 항상 첫 번째를 덮어쓰므로, get_trailing_atr_multiple()로
    구간별 배수 하나만 골라 한 번에 적용해도 수학적으로 동일한 결과다.

    이 함수는 position을 변형하지 않는 순수 함수다 - 새 stop_price/highest_price를
    담은 dict를 반환하고, 호출측(파이프라인)이 DB에 반영해야 한다.

    필수 입력이 없거나 유효하지 않으면(위험 데이터 없음, ATR<=0 등) None을
    반환한다 - 추측으로 손절가를 만들지 않는다(atr.py와 동일한 원칙)."""
    entry_price = position.get("entry_price")
    initial_risk_per_share = position.get("initial_risk_per_share")
    current_stop = position.get("stop_price")
    previous_highest = position.get("highest_price")

    if (
        entry_price is None
        or initial_risk_per_share is None
        or initial_risk_per_share <= 0
        or current_stop is None
        or current_high is None
        or current_price is None
        or atr20 is None
        or atr20 <= 0
    ):
        return None

    highest_price = max(previous_highest, current_high) if previous_highest is not None else current_high

    profit_r = (current_price - entry_price) / initial_risk_per_share

    new_stop = current_stop

    # +1R 이상 -> 최소 본전(진입가) 보호
    if profit_r >= config.breakeven_trigger_r:
        new_stop = max(new_stop, entry_price)

    # +2R(트레일링 시작) / +4R(더 타이트한 트레일링) -> ATR 트레일링, 위로만
    atr_multiple = get_trailing_atr_multiple(profit_r, config)
    if atr_multiple is not None:
        new_stop = calculate_trailing_stop(new_stop, highest_price, atr20, atr_multiple)

    return {"stop_price": new_stop, "highest_price": highest_price}
