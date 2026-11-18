import datetime as dt

from backend.agent.ko_time import fix_changes, parse_when

TODAY = dt.date(2026, 11, 18)  # 수요일


def test_weekday_and_pm_deadline():
    assert parse_when("토요일 오후 2시까지 강남역", TODAY) == {"date": "2026-11-21", "arrive_by": "14:00"}


def test_relative_days_and_depart_after():
    assert parse_when("모레 오전 10시 이후 출발", TODAY) == {"date": "2026-11-20", "depart_after": "10:00"}
    assert parse_when("내일 9시 반부터 출발할게", TODAY) == {"date": "2026-11-19", "depart_after": "09:30"}


def test_evening_and_minutes():
    assert parse_when("오늘 저녁 7시 30분까지", TODAY) == {"date": "2026-11-18", "arrive_by": "19:30"}


def test_hhmm_and_explicit_date():
    assert parse_when("11월 25일 14:30까지 도착", TODAY) == {"date": "2026-11-25", "arrive_by": "14:30"}


def test_next_week_weekday():
    assert parse_when("다음주 월요일 오전 9시까지", TODAY) == {"date": "2026-11-23", "arrive_by": "09:00"}


def test_today_weekday_means_today():
    assert parse_when("수요일 오후 3시까지", TODAY)["date"] == "2026-11-18"


def test_nothing_found():
    assert parse_when("강남역 가는 법", TODAY) == {}


def test_fix_changes_moves_date_out_of_time_field():
    fixed = fix_changes({"arrive_by": "2026-11-21", "budget": 60000}, "토요일 오후 2시까지", TODAY)
    assert fixed == {"date": "2026-11-21", "arrive_by": "14:00", "budget": 60000}


def test_fix_changes_does_not_override_llm():
    fixed = fix_changes({"date": "2026-11-22", "arrive_by": "15:00"}, "토요일 오후 2시까지", TODAY)
    assert fixed["date"] == "2026-11-22" and fixed["arrive_by"] == "15:00"


def test_fix_changes_drops_bad_time():
    assert "arrive_by" not in fix_changes({"arrive_by": "오후"}, "가야 해", TODAY)
