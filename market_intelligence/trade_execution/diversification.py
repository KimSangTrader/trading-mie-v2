"""
Sector/Theme 집중도 제한 (Phase 6-1)

================================================================================
【변경 이력】
================================================================================
【2026-08-25】최초 생성 (Phase 6-1) - 업로드 문서(miev2trading.txt) §6 그대로 구현.
- 계층형 랭킹 상위 종목을 그대로 다 사면 겉보기엔 분산투자여도 실제로는
  같은 Sector/Theme에 집중될 수 있다는 문제를 막는다. 랭킹 순서대로 훑으며
  Sector/Theme별 카운트가 한도를 넘으면 건너뛰는 그리디(greedy) 방식 -
  문서의 diversify_candidates() 그대로.
================================================================================
"""

from typing import List, Dict, Any


def diversify_candidates(
    ranked_stocks: List[Dict[str, Any]],
    max_positions: int,
    max_per_sector: int,
    max_per_theme: int,
) -> List[Dict[str, Any]]:
    """랭킹 순서(ranked_stocks의 입력 순서를 그대로 신뢰함 - 호출부가 이미
    final_score/overall_rank 기준으로 정렬해서 넘겨야 한다)대로 훑으며,
    Sector/Theme 집중 한도를 넘지 않는 선에서 max_positions개까지 고른다.

    Args:
        ranked_stocks: 각 원소는 최소 "sector"(str|None)와
            "primary_theme"(str|None) 키를 가져야 한다. sector/primary_theme이
            None인 종목(매핑 안 된 종목)은 그 축의 집중도 제한에서 제외하고
            통과시킨다(결측을 이유로 부당하게 탈락시키지 않음 - 이 프로젝트의
            "결측 시 재정규화" 원칙과 같은 맥락).
        max_positions: 최종적으로 고를 최대 종목 수.
        max_per_sector: Sector 하나당 허용하는 최대 종목 수.
        max_per_theme: Theme(primary_theme 기준) 하나당 허용하는 최대 종목 수.

    Returns:
        선정된 종목 리스트(입력 순서 유지, 최대 max_positions개).
    """
    selected: List[Dict[str, Any]] = []
    sector_count: Dict[str, int] = {}
    theme_count: Dict[str, int] = {}

    for stock in ranked_stocks:
        if len(selected) >= max_positions:
            break

        sector = stock.get("sector")
        theme = stock.get("primary_theme")

        if sector is not None and sector_count.get(sector, 0) >= max_per_sector:
            continue
        if theme is not None and theme_count.get(theme, 0) >= max_per_theme:
            continue

        selected.append(stock)
        if sector is not None:
            sector_count[sector] = sector_count.get(sector, 0) + 1
        if theme is not None:
            theme_count[theme] = theme_count.get(theme, 0) + 1

    return selected
