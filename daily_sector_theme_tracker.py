"""
daily_sector_theme_tracker.py - 매일 계층형 Sector/Theme 실계산 결과(최강/최약/평균)를
CSV로 누적 기록하는 조회 전용 스크립트. DB에 아무것도 쓰지 않고, KIS API도 호출하지
않는다(show_today_candidates.py와 동일한 위치/성격 - /var/log/mie-v2/error.log를 읽기만
한다).

================================================================================
【변경 이력】
================================================================================
【2026-09-08】최초 생성
- 배경: 계층형 랭킹을 처음 완주시킨 날(2026-09-08), Sector/Theme 점수가 진입
  기준선(sector>=65/theme>=60 - miev2trading.txt 문서 원문 값, 이 세션이 임의로
  정한 값 아님)에 단 하루도 못 미쳤음을 발견. 다만 원인으로 지목된
  market_intelligence/price_series.py의 scale_symmetric() 스케일링 폭
  (_MOMENTUM_NEUTRAL_SPAN_PCT 등)은 문서에 없는 이 세션의 잠정값이라, 하루치
  데이터만으로 조정하는 건 성급하다고 판단 - 사용자가 "실거래 데이터 며칠 더
  쌓고 판단하겠다"고 결정함에 따라, 매일 자동으로 그 근거 데이터를 CSV에
  쌓아두는 스크립트를 만듦.
- 데이터 출처: main.py의 SectorAnalyzer.analyze()/ThemeAnalyzer.analyze()가 매
  배치마다 정확히 한 번씩 남기는 로그 한 줄("Sector Analysis: N개 Sector,
  Strongest=X(점수), Weakest=Y(점수), Average=점수")을 정규식으로 파싱한다 -
  DB 스키마 변경이나 main.py 수정 없이(실거래 코드 경로를 건드리지 않기 위해)
  이미 존재하는 로그만 읽는 방식을 택했다.
- 날짜 키는 로그 타임스탬프가 아니라 data/state/main_run_state.json의
  last_completed_date를 쓴다 - 그래야 "이 기록이 실제로 어느 거래일자
  배치인지"가 명확하고, 자정을 넘겨 완료된 배치도 올바른 거래일자로 기록된다.
- 멱등성: 이미 같은 date가 CSV에 있으면 다시 추가하지 않는다 - cron/systemd
  timer가 하루 여러 번 돌거나 재실행돼도 중복 행이 안 생긴다.
================================================================================

사용법:
    python3 daily_sector_theme_tracker.py          # 오늘자 기록 추가(멱등)
    python3 daily_sector_theme_tracker.py show      # 누적된 기록을 표로 출력
"""
import csv
import json
import re
import sys
from pathlib import Path

_ERROR_LOG = Path("/var/log/mie-v2/error.log")
_STATE_FILE = Path("/opt/mie-v2/data/state/main_run_state.json")
_OUTPUT_CSV = Path("/opt/mie-v2/data/state/sector_theme_daily_history.csv")

_SECTOR_RE = re.compile(
    r"Sector Analysis: (\d+)개 Sector, Strongest=([^(]+)\(([\d.]+)\), "
    r"Weakest=([^(]+)\(([\d.]+)\), Average=([\d.]+)"
)
_THEME_RE = re.compile(
    r"Theme Analysis: (\d+)개 Theme, Strongest=([^(]+)\(([\d.]+)\), "
    r"Weakest=([^(]+)\(([\d.]+)\), Average=([\d.]+)"
)

_CSV_FIELDS = [
    "date", "sector_count", "sector_strongest_name", "sector_strongest_score",
    "sector_weakest_name", "sector_weakest_score", "sector_average",
    "theme_count", "theme_strongest_name", "theme_strongest_score",
    "theme_weakest_name", "theme_weakest_score", "theme_average",
]

# entry_filter의 진입 기준선(miev2trading.txt 문서 원문 값) - 표 출력 시 참고용으로만 쓴다.
_MIN_SECTOR_SCORE = 65.0
_MIN_THEME_SCORE = 60.0


def _last_match(pattern, lines):
    """패턴에 매칭되는 마지막 줄을 돌려준다 - 로그에 여러 날짜가 섞여 있어도
    가장 최근 완료된 배치(last_completed_date와 짝지어질 항목)를 집는다."""
    match = None
    for line in lines:
        m = pattern.search(line)
        if m:
            match = m
    return match


def _record_today() -> int:
    if not _STATE_FILE.exists():
        print(f"❌ {_STATE_FILE} 없음 - main.py serve가 아직 한 번도 완료 안 됐을 수 있습니다.")
        return 1
    try:
        state = json.loads(_STATE_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"❌ {_STATE_FILE} 읽기 실패: {e}")
        return 1

    completed_date = state.get("last_completed_date")
    if not completed_date:
        print("❌ main_run_state.json에 last_completed_date가 없습니다.")
        return 1

    if not _ERROR_LOG.exists():
        print(f"❌ {_ERROR_LOG} 없음")
        return 1
    lines = _ERROR_LOG.read_text(encoding="utf-8", errors="replace").splitlines()

    sector_match = _last_match(_SECTOR_RE, lines)
    theme_match = _last_match(_THEME_RE, lines)
    if not sector_match or not theme_match:
        print("❌ 로그에서 Sector Analysis / Theme Analysis 줄을 찾지 못했습니다 "
              "(로그가 로테이션됐거나, 아직 오늘자 배치가 완료 전일 수 있습니다).")
        return 1

    existing_dates = set()
    if _OUTPUT_CSV.exists():
        with _OUTPUT_CSV.open("r", encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                existing_dates.add(row["date"])

    if completed_date in existing_dates:
        print(f"ℹ️  {completed_date} 기록이 이미 있습니다 - 건너뜁니다 (멱등 처리).")
        return 0

    row = {
        "date": completed_date,
        "sector_count": sector_match.group(1),
        "sector_strongest_name": sector_match.group(2),
        "sector_strongest_score": sector_match.group(3),
        "sector_weakest_name": sector_match.group(4),
        "sector_weakest_score": sector_match.group(5),
        "sector_average": sector_match.group(6),
        "theme_count": theme_match.group(1),
        "theme_strongest_name": theme_match.group(2),
        "theme_strongest_score": theme_match.group(3),
        "theme_weakest_name": theme_match.group(4),
        "theme_weakest_score": theme_match.group(5),
        "theme_average": theme_match.group(6),
    }

    is_new = not _OUTPUT_CSV.exists()
    _OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with _OUTPUT_CSV.open("a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=_CSV_FIELDS)
        if is_new:
            writer.writeheader()
        writer.writerow(row)

    print(f"✅ {completed_date} 기록 추가 완료 -> {_OUTPUT_CSV}")
    print(f"   Sector: {row['sector_count']}개, 최강={row['sector_strongest_name']}"
          f"({row['sector_strongest_score']}), 평균={row['sector_average']} "
          f"(기준선 {_MIN_SECTOR_SCORE})")
    print(f"   Theme:  {row['theme_count']}개, 최강={row['theme_strongest_name']}"
          f"({row['theme_strongest_score']}), 평균={row['theme_average']} "
          f"(기준선 {_MIN_THEME_SCORE})")
    return 0


def _show() -> int:
    if not _OUTPUT_CSV.exists():
        print(f"아직 기록이 없습니다 ({_OUTPUT_CSV} 파일 없음) - "
              "먼저 인자 없이 실행해서 오늘자를 기록하세요.")
        return 1

    with _OUTPUT_CSV.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))

    if not rows:
        print("기록이 비어 있습니다.")
        return 0

    header = f"{'날짜':<12} {'Sector최강':<26} {'Sector평균':>10} {'Theme최강':<22} {'Theme평균':>10}"
    print(header)
    print("-" * len(header))
    for r in rows:
        sector_top = f"{r['sector_strongest_name']}({r['sector_strongest_score']})"
        sector_top += " ✅" if float(r["sector_strongest_score"]) >= _MIN_SECTOR_SCORE else ""
        theme_top = f"{r['theme_strongest_name']}({r['theme_strongest_score']})"
        theme_top += " ✅" if float(r["theme_strongest_score"]) >= _MIN_THEME_SCORE else ""
        print(f"{r['date']:<12} {sector_top:<26} {r['sector_average']:>10} "
              f"{theme_top:<22} {r['theme_average']:>10}")

    print("-" * len(header))
    print(f"총 {len(rows)}일 누적. ✅ = 그날 최강 Sector/Theme가 진입 기준선"
          f"(sector>={_MIN_SECTOR_SCORE}/theme>={_MIN_THEME_SCORE})을 넘긴 경우.")
    return 0


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "show":
        return _show()
    return _record_today()


if __name__ == "__main__":
    sys.exit(main())
