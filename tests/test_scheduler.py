"""main.py의 일마감 분석 스케줄러(_should_run_now/_previous_business_day) 테스트.

================================================================================
【변경 이력】
================================================================================
【2026-09-22】최초 생성 - "매주 월요일마다 지난 금요일 데이터로 잘못 캐치업" 버그 수정 검증
- 배경: 9/14, 9/21 EC2 실제 로그에서 두 번 다 월요일 00:25 KST 무렵 "완료" 기록이
  남았는데 Sector/Theme Analysis 수치가 직전 금요일과 소수점까지 완전히 동일했다 -
  캐치업 로직이 "어제"를 항상 `now - 1일`로 계산해서, 주말을 건너뛴 뒤 월요일
  자정 직후 첫 체크에서 `last_completed_date(금요일)` vs `어제(일요일)` 비교가
  매주 무조건 "하루 이상 밀림"으로 오판정되던 것이 원인이었다(main.py 변경이력
  【2026-09-22】 항목 참고). 이 테스트는 그 버그가 재발하지 않는지 고정한다.
================================================================================
"""
from datetime import datetime

from main import _previous_business_day, _should_run_now


class TestPreviousBusinessDay:
    def test_monday_returns_previous_friday(self):
        # 2026-09-21은 월요일, 2026-09-18은 그 전 금요일
        assert _previous_business_day(datetime(2026, 9, 21).date()) == datetime(2026, 9, 18).date()

    def test_tuesday_returns_monday(self):
        assert _previous_business_day(datetime(2026, 9, 22).date()) == datetime(2026, 9, 21).date()

    def test_saturday_returns_friday(self):
        assert _previous_business_day(datetime(2026, 9, 19).date()) == datetime(2026, 9, 18).date()


class TestShouldRunNow:
    def test_monday_midnight_with_friday_completion_waits_for_target(self):
        """핵심 회귀 테스트: 이게 바로 9/14, 9/21에 실제로 터졌던 버그 시나리오.

        월요일 자정 직후(장 시작 전)에 last_completed_date가 지난 금요일이면,
        "다운타임으로 하루 이상 밀렸다"고 오판해 즉시 캐치업하면 안 된다 -
        정상적으로 그날 밤 목표 시각(22:00 KST)까지 대기해야 한다."""
        state = {"last_completed_date": "2026-09-18"}  # 지난 금요일
        monday_midnight = datetime(2026, 9, 21, 0, 1)  # 월요일 00:01
        assert _should_run_now(state, monday_midnight) is False

    def test_monday_after_target_hour_with_friday_completion_runs(self):
        state = {"last_completed_date": "2026-09-18"}
        monday_evening = datetime(2026, 9, 21, 22, 5)  # 월요일 22:05 (목표 시각 이후)
        assert _should_run_now(state, monday_evening) is True

    def test_tuesday_with_friday_completion_catches_up_immediately(self):
        """진짜로 월요일 몫이 통째로 빠진 경우(화요일인데 여전히 지난 금요일
        완료 기록)는 시각과 무관하게 즉시 캐치업해야 한다 - 이 동작은 그대로 유지."""
        state = {"last_completed_date": "2026-09-18"}
        tuesday_morning = datetime(2026, 9, 22, 3, 0)
        assert _should_run_now(state, tuesday_morning) is True

    def test_tuesday_with_monday_completion_waits_for_target(self):
        state = {"last_completed_date": "2026-09-21"}
        tuesday_early = datetime(2026, 9, 22, 3, 0)
        assert _should_run_now(state, tuesday_early) is False

    def test_weekend_always_skips(self):
        state = {"last_completed_date": "2026-09-18"}
        saturday = datetime(2026, 9, 19, 23, 0)
        assert _should_run_now(state, saturday) is False

    def test_same_day_already_completed_waits(self):
        state = {"last_completed_date": "2026-09-21"}
        monday_later = datetime(2026, 9, 21, 23, 0)
        assert _should_run_now(state, monday_later) is False

    def test_no_prior_completion_runs_immediately(self):
        assert _should_run_now({}, datetime(2026, 9, 21, 10, 0)) is True
