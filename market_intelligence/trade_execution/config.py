"""
매매 실행 엔진 설정값 (Phase 6-1)

================================================================================
【변경 이력】
================================================================================
【2026-08-25】최초 생성 (Phase 6-1)
- 배경: 사용자가 업로드한 "MIE V2 매매기준 및 1회 매매한도" 검토 문서
  (miev2trading.txt, 실질적으로 컨설턴트/다른 AI가 작성한 Turtle Trading
  하이브리드 실행 엔진 설계)를 그대로 코드로 옮긴 것. 숫자는 전부 그 문서에서
  그대로 가져왔다 - 이 세션이 임의로 정한 값이 아니다.
- 사용자가 AskUserQuestion으로 확정한 것: (1) 모의투자(KIS_DEV)부터 시작,
  (2) 주문 실행은 완전 자동(사람 승인 없이 시스템이 직접 매수/매도),
  (3) 계층형 랭킹 상위 30종목을 "후보"로 삼음(TOTAL_CANDIDATES=30),
  (4) 매도 기준은 "특이사항 없음"으로 답해서 업로드 문서의 규칙을 그대로 채택.
  (5) 리밸런싱/신호 재계산은 매일(기존 main.py serve의 19:00 KST 일마감
  분석 직후 흐름과 자연스럽게 맞물림).
- TOTAL_CAPITAL(700만원)은 문서에 나온 예시 계좌 규모를 그대로 기본값으로
  둔 것 - 실제 매매 파이프라인(다음 단계)에서는 이 상수 대신 KIS 잔고조회
  API로 읽은 실제 계좌 평가금액을 우선 사용하고, API 조회가 실패했을 때만
  이 기본값으로 폴백하도록 설계할 예정(아직 그 배선은 안 함 - 이 파일은
  순수 설정값과 파생 계산만 담당).
- 【미확정 - 다음 단계에서 반드시 확인 필요】업로드 문서는 매수 진입/추가매수
  (피라미딩)/손절 규칙은 구체적 숫자까지 명시했지만, "손절가 도달 이외의
  이유로 포지션 전체를 청산하는 규칙"(문서의 ExitManager, "추세 이탈 시
  전량 또는 단계적 청산")은 모듈 이름만 언급하고 정확한 수치 규칙을 안
  줬다. 이 세션이 임의로 수치를 정하지 않고, pyramiding.py의
  PositionManager에는 문서에 있는 그대로(손절가 도달 시 SELL, 그 외에는
  추가매수 차단 조건만)만 구현했다 - 전량 청산 규칙은 다음 단계에서
  사용자에게 다시 확인 후 추가한다.

【2026-08-26】ExitConfig 추가 (Phase 6-2, miev2tradingsell.txt 반영)
- 배경: 사용자가 두 번째 문서(miev2tradingsell.txt - 손절/익절/전량청산 매도
  규칙 설계)를 업로드하고 "문서를 확인해서 손절 및 익절, 전량청산등의
  매도부분을 확인해주세요"라고 요청. 문서는 5단계 Exit Engine(①초기손절
  ②긴급청산 ③부분익절 ④트레일링스톱 ⑤전량청산)과 우선순위, 그리고
  "11. 가장 추천하는 전체 Exit Engine"(PositionExitAnalyzer.analyze) +
  "12. 매일 손절가를 자동으로 업데이트"(StopManager.update_stop) +
  "14. 제가 추천하는 최종 청산 파라미터"(EXIT_CONFIG)까지 구체적 숫자를
  전부 명시했다. 위 미확정 사항이 이 문서로 해소되어, 이 세션이 숫자를
  임의로 정하지 않고 아래 ExitConfig 필드에 문서 §14의 EXIT_CONFIG를
  그대로 옮겼다.
- initial_stop_atr는 별도 필드를 새로 만들지 않고 기존 TradingConfig의
  stop_atr_multiple(이미 2.0)을 그대로 재사용한다 - 같은 개념이라 중복
  필드를 두지 않았다.
- 문서 자체가 "다만 -8% 같은 숫자는 고정 정답이 아닙니다. 실제 MIE 과거
  성과를 이용해 백테스트로 조정해야 합니다"라고 명시한 부분(emergency_loss_pct)
  과 "따라서 반드시 VERSION A/B/C(전량 익절 vs 부분 익절 vs 익절 없음)를
  비교해야 합니다"(§15)라고 명시한 부분은 그대로 미검증 상태로 남겨둔다 -
  이 세션은 문서 §14의 최종 추천값(부분 익절 방식, VERSION B)을 기본값으로
  구현했을 뿐, 백테스트로 검증된 값이 아니다. 실거래 투입 전 반드시 과거
  데이터로 백테스트할 것.
- 문서 자체의 내부 불일치 발견(§13 Day15 예시): "최고가 14,000원, ATR20
  500원 → Trailing Stop = 14,000-(500×3)=12,500원"이라고 서술했지만,
  같은 문서 §8/§12의 공식(수익 +4R 이상이면 ATR 2.5배 사용)을 그대로
  적용하면 이 시점 profit_r=(14,000-10,000)/1,000=4.0로 +4R 구간이라
  2.5배가 맞아 12,000-1,250(원 손절가는 최고가 기준 14,000-1,250)=12,750원이
  되어야 한다(3배를 쓴 12,500원과 다름). Phase 6-1의 E종목 14주/21주
  불일치와 같은 유형의 오탈자로 판단 - 이 구현은 문서가 명시한 공식(§8/§12
  코드)을 그대로 따르고, 서술형 예시의 숫자(12,500원)는 따라가지 않는다.
  자세한 근거는 tests/test_exit_engine.py의 관련 테스트 주석 참고.
- 문서 §11의 analyze() 코드에서 "② 초기 손절"(position.stop_price 체크)과
  "⑦ ATR Trailing Stop"(position.trailing_stop_price 체크)이 서로 다른
  필드명을 쓰고 있지만, §12 StopManager.update_stop()은 오직
  position.stop_price 하나만 갱신한다(별도 trailing_stop_price 필드가
  존재하지 않음) - 즉 문서 자체가 필드명을 통일하지 않은 것으로 판단해,
  이 구현은 stop_price 하나로 통합했다(exit_engine.py의 analyze_exit()
  docstring에 상세 설명). 초기 손절인지 트레일링 손절인지는
  position["initial_stop_price"](최초 계산된 손절가, 절대 바뀌지 않음)와
  현재 stop_price를 비교해서 구분한다.
================================================================================
"""

from dataclasses import dataclass, field
from typing import Dict


@dataclass(frozen=True)
class TradingConfig:
    """매매 실행 엔진 전체 설정. 기본값은 전부 업로드 문서의 "700만원 계좌
    보수형" 설정을 그대로 옮긴 것이다. 실전 배선 시에는 계좌 실제 평가금액을
    total_capital에 넣어 인스턴스를 새로 만들어 쓰면 된다(불변 dataclass라
    필드를 직접 고치지 않고 dataclasses.replace()로 새 인스턴스를 만든다)."""

    # ---------- 계좌/자금 ----------
    total_capital: float = 7_000_000.0          # 계좌 총액(문서 예시값, 실전에는 KIS 잔고조회로 대체 권장)
    cash_reserve_ratio: float = 0.10             # 항상 남겨둘 현금 비율
    max_investment_ratio: float = 0.90           # 총 계좌에서 실제 주식에 투입할 최대 비율

    # ---------- 위험 관리 ----------
    risk_per_stock_ratio: float = 0.005          # 종목 1개가 손절될 때 허용하는 최대 손실 비율(0.5%)
    max_portfolio_risk_ratio: float = 0.05       # 모든 종목이 동시에 손절될 경우 목표 최대 손실 비율(5%)
    max_position_ratio: float = 0.15             # 종목당 최대 투자 비중(15%)

    # ---------- 포지션 구조 ----------
    max_positions: int = 7                       # 최대 동시 보유 종목 수(700만원 계좌 권장치)
    max_per_sector: int = 2                       # Sector당 최대 보유 종목 수
    max_per_theme: int = 2                        # Theme(주 테마 기준)당 최대 보유 종목 수
    max_entries: int = 3                          # 종목 1개당 최대 분할매수(피라미딩 포함) 횟수
    entry_weights: Dict[int, float] = field(
        default_factory=lambda: {1: 0.50, 2: 0.25, 3: 0.25}
    )                                              # 1차/2차/3차 매수 비중(보수형) - 목표 수량에 곱해서 사용

    # ---------- ATR 기반 손절/피라미딩 ----------
    atr_period: int = 20                          # ATR 계산 기간(일)
    stop_atr_multiple: float = 2.0                # 손절폭 = entry_price - ATR20 * 이 배수
    pyramid_atr_multiple: float = 1.0              # 추가매수 트리거 = last_entry_price + ATR20 * 이 배수

    # ---------- 진입 필터(다음날 실행 재검증) ----------
    min_final_score: float = 75.0                  # 계층형 final_score 최소 기준(진입)
    min_sector_score: float = 65.0                  # Sector 점수 최소 기준(진입/추가매수 공통)
    min_theme_score: float = 60.0                   # Theme 점수 최소 기준(진입/추가매수 공통)
    max_rank_for_add: int = 30                      # 추가매수를 허용하는 현재 랭킹 하한(이보다 나쁘면 추가매수 금지)

    # ---------- 후보 풀 ----------
    total_candidates: int = 30                      # 계층형 랭킹에서 뽑아올 후보 수(사용자 확정값)

    # ---------- 【2026-08-26, Phase 6-3】진입 시 실행 파이프라인 전용 값 ----------
    # entry_filter.check_entry()가 갭 +7~+12%에서 반환하는 "REDUCE"는 문서(§4)가
    # "매수 비중 축소"라고만 서술하고 구체적 축소 비율은 주지 않았다(entry_filter.py
    # docstring "실제 축소는 호출부/포지션사이저 몫" 참고) - trade_execution_pipeline.py가
    # target_shares에 이 배수를 곱해서 축소한다. 문서에 없는 값이라 이 세션이 임의로
    # 0.5(절반)를 골랐다 - 백테스트/실거래 경험으로 조정이 필요할 수 있는 값.
    reduce_position_ratio: float = 0.5


# 문서의 갭 필터 5단계 판정표(check_opening_gap() 원문 그대로) - GapFilter가
# 이 순서로 그대로 사용한다. (하한, 상한, 판정] 형태. 상한 없음은 None으로 표시.
# 문서 원문 라벨을 그대로 따름: <=-5%는 "NO_ENTRY"가 아니라 "WAIT"(즉시 매수
# 금지하되 재평가 대상 - 완전히 후보 탈락시키는 +12% 이상의 "NO_ENTRY"와는
# 의미가 다름).
GAP_BANDS = (
    (None, -5.0, "WAIT"),                    # -5% 이하: 즉시 매수 금지, 재평가
    (-5.0, 3.0, "NORMAL_ENTRY"),             # -5% ~ +3%: 정상 진입 가능
    (3.0, 7.0, "WAIT_CONFIRMATION"),         # +3% ~ +7%: 15~30분 확인 후 진입
    (7.0, 12.0, "REDUCE_POSITION"),          # +7% ~ +12%: 매수 비중 축소
    (12.0, None, "NO_ENTRY"),                # +12% 이상: 원칙적으로 추격 매수 금지
)

DEFAULT_CONFIG = TradingConfig()


@dataclass(frozen=True)
class ExitConfig:
    """청산(Exit) 엔진 설정값 (Phase 6-2). 전부 miev2tradingsell.txt §14
    "제가 추천하는 최종 청산 파라미터"(EXIT_CONFIG)를 그대로 옮긴 것 - 이
    세션이 임의로 정한 값이 아니다. initial_stop은 TradingConfig.stop_atr_multiple
    (기존 2.0)을 그대로 재사용하므로 여기 별도 필드가 없다."""

    # ---------- ① 긴급 청산 ----------
    emergency_loss_pct: float = -8.0             # 당일 등락률(%)이 이 이하로 급락하면 즉시 전량 청산(문서 자체가 "백테스트로 조정 필요"라고 명시한 값)

    # ---------- ③ 부분 익절 ----------
    partial_take_profit_r: float = 2.0            # 이 R배수 이상 수익이면 부분 익절 트리거
    partial_sell_ratio: float = 0.25              # 부분 익절 시 매도할 보유 수량 비율(25%)

    # ---------- 손절가 자동 상향(StopManager) ----------
    breakeven_trigger_r: float = 1.0              # 이 R배수 이상이면 손절가를 최소 진입가(본전)까지 상향
    trailing_start_r: float = 2.0                 # 이 R배수부터 ATR 트레일링 스톱 시작
    trailing_atr_multiple: float = 3.0            # trailing_start_r ~ tight_trailing_trigger_r 구간의 트레일링 ATR 배수
    tight_trailing_trigger_r: float = 4.0         # 이 R배수 이상이면 더 타이트한 트레일링으로 전환(큰 수익 보호)
    tight_trailing_atr_multiple: float = 2.5      # tight_trailing_trigger_r 이상 구간의 트레일링 ATR 배수

    # ---------- ⑤ 터틀식 전량 청산 ----------
    turtle_exit_days: int = 10                    # 이 기간 최저가를 하향 이탈하면 전량 청산

    # ---------- MIE 특화 "분석 논리 붕괴" 청산 ----------
    max_rank_drop: int = 80                       # 진입 시점 대비 현재 랭킹이 이만큼 나빠지면 전량 청산
    minimum_sector_score: float = 45.0            # Sector 점수가 이 미만이고 Theme도 미달이면(둘 다) 전량 청산
    minimum_theme_score: float = 45.0             # Theme 점수 기준(위와 동시 충족 조건)


DEFAULT_EXIT_CONFIG = ExitConfig()
