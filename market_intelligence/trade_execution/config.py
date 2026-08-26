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
