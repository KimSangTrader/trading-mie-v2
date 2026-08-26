# 【2026-08-25, Phase 6-1】매매 실행 엔진 - 순수 계산기 모음
#
# 이 패키지는 market_intelligence/analyzers/와 동일한 원칙을 따른다:
# "analyzers/collectors는 순수 계산기다(API/DB 호출 없음). 실제 KIS
# 주문 API/DB 연동은 별도 pipeline이 이 계산기들을 조립해서 담당한다"
# (아직 그 pipeline은 없음 - 다음 단계에서 trade_execution_pipeline.py로
# 추가 예정, market_intelligence/collectors/valuation_pipeline.py와 같은
# 위치의 역할).
#
# 각 모듈의 역할:
#   config.py          - 모든 설정값(계좌/위험/포지션 구조) 한 곳에 모음
#   atr.py              - ATR(20일) 계산
#   gap_filter.py        - 시초가 갭 5단계 판정
#   entry_filter.py       - 1차 진입 가능 여부(갭+점수 종합 판정)
#   diversification.py    - Sector/Theme 집중도 제한
#   position_sizer.py     - ATR/위험 기준 매수 수량 계산 + 회차별 분할
#   pyramiding.py         - 추가매수(피라미딩) 판정 + (구버전) 손절 판정
#   portfolio_risk.py     - 포트폴리오 전체 위험 한도 관리
#   exit_engine.py         - 【Phase 6-2】청산 판정(긴급청산/손절/트레일링/
#                             부분익절/터틀청산 통합) + 손절가 일일 갱신
#
# 원본: 사용자가 업로드한 miev2trading.txt(매매기준/1회 매매한도 검토 문서) +
# miev2tradingsell.txt(손절/익절/전량청산 매도 규칙 문서, Phase 6-2). 숫자와
# 판정 로직은 전부 그 문서들에서 그대로 가져왔다 - docs/hierarchical_
# scoring_plan.md의 Phase 6-1/6-2 섹션에 전체 맥락 정리.

from market_intelligence.trade_execution.config import (
    TradingConfig,
    DEFAULT_CONFIG,
    GAP_BANDS,
    ExitConfig,
    DEFAULT_EXIT_CONFIG,
)
from market_intelligence.trade_execution.atr import compute_atr, compute_true_range
from market_intelligence.trade_execution.gap_filter import compute_gap_pct, classify_gap, check_gap
from market_intelligence.trade_execution.entry_filter import check_entry
from market_intelligence.trade_execution.diversification import diversify_candidates
from market_intelligence.trade_execution.position_sizer import calculate_position, split_entry_shares
from market_intelligence.trade_execution.pyramiding import should_add, check_stop
from market_intelligence.trade_execution.portfolio_risk import (
    position_risk,
    total_portfolio_risk,
    remaining_risk_budget,
    clip_shares_to_portfolio_risk,
)
from market_intelligence.trade_execution.exit_engine import (
    analyze_exit,
    update_stop,
    get_trailing_atr_multiple,
    calculate_trailing_stop,
    compute_lowest_low,
)

__all__ = [
    "TradingConfig",
    "DEFAULT_CONFIG",
    "GAP_BANDS",
    "ExitConfig",
    "DEFAULT_EXIT_CONFIG",
    "compute_atr",
    "compute_true_range",
    "compute_gap_pct",
    "classify_gap",
    "check_gap",
    "check_entry",
    "diversify_candidates",
    "calculate_position",
    "split_entry_shares",
    "should_add",
    "check_stop",
    "position_risk",
    "total_portfolio_risk",
    "remaining_risk_budget",
    "clip_shares_to_portfolio_risk",
    "analyze_exit",
    "update_stop",
    "get_trailing_atr_multiple",
    "calculate_trailing_stop",
    "compute_lowest_low",
]
