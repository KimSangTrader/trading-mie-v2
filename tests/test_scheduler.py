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
【2026-09-29】추석 연휴(공휴일) 케이스 추가 - "공휴일에도 평일처럼 분석을 돌려
  직전 거래일과 동일한 데이터가 중복 기록되는" 문제 검증
- 배경: 2026-09-24~25 추석 연휴 이틀 다 실제로 이 문제가 발생해(사용자가 확인),
  main.py의 _should_run_now()/_previous_business_day()가 data.krx_calendar의
  is_krx_trading_day()를 쓰도록 바뀌었다(main.py 변경이력 【2026-09-29】 참고).
  이 테스트는 그 수정이 실제 2026년 추석 연휴에 대해 맞게 동작하는지 고정한다.
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


class TestHolidayAwareness:
    """2026-09-29 추가: 2026 추석 연휴(9/24~25, 실제 KRX 휴장) 관련 회귀 테스트."""

    def test_previous_business_day_skips_chuseok_holiday(self):
        # 2026-09-28(월)의 "그 전 실제 거래일"은 9/24~27(추석 연휴+주말)을
        # 모두 건너뛴 9/23(수, 추석 연휴 시작 전 마지막 정상 거래일)이어야 한다.
        assert _previous_business_day(datetime(2026, 9, 28).date()) == datetime(2026, 9, 23).date()

    def test_should_run_now_skips_on_holiday_regardless_of_time(self):
        # 9/24(추석 연휴, 평일)는 목표 시각(22:00)을 넘겨도 실행하면 안 된다.
        state = {"last_completed_date": "2026-09-23"}
        holiday_evening = datetime(2026, 9, 24, 22, 30)
        assert _should_run_now(state, holiday_evening) is False

    def test_monday_after_chuseok_waits_for_target_not_catchup(self):
        # 연휴 마지막 정상 거래일(9/23) 완료 기록을 들고 연휴 다음 첫 거래일인
        # 월요일(9/28) 새벽을 맞아도, "며칠 밀렸다"고 오판해 즉시 캐치업하면
        # 안 된다 - 9/24~27은 애초에 거래일이 아니었으므로 정상적으로 그날
        # 22:00 목표 시각까지 대기해야 한다.
        state = {"last_completed_date": "2026-09-23"}
        monday_after_chuseok_midnight = datetime(2026, 9, 28, 0, 1)
        assert _should_run_now(state, monday_after_chuseok_midnight) is False

        monday_after_chuseok_evening = datetime(2026, 9, 28, 22, 5)
        assert _should_run_now(state, monday_after_chuseok_evening) is True
