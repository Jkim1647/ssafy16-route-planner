"""출발 알림: Google 캘린더에 이동 일정을 넣을 때 출발 15분·5분 전 팝업 알림을 함께 넣는다."""
import datetime as dt

from backend.calendar.google import GoogleCalendar
from backend.schemas import PlanOut

NOW = dt.datetime(2026, 11, 19, 9, 0)


class FakeService:
    def __init__(self):
        self.body = None

    def events(self):
        return self

    def insert(self, calendarId, body):
        self.body = body
        return self

    def execute(self):
        return {"id": "evt-1"}


def test_event_has_departure_reminders(monkeypatch):
    svc = FakeService()
    cal = GoogleCalendar()
    monkeypatch.setattr(cal, "_service", lambda: svc)
    plan = PlanOut(id=1, title="첨단동 → 강남역", date=dt.date(2026, 11, 21), leave_at="07:30", arrive_at="10:40",
                   origin_name="첨단동", destination_name="강남역", created_at=NOW, updated_at=NOW)
    assert cal.create_event(plan) == "evt-1"
    assert svc.body["reminders"] == {"useDefault": False,
                                     "overrides": [{"method": "popup", "minutes": 15}, {"method": "popup", "minutes": 5}]}
    assert svc.body["start"]["dateTime"].startswith("2026-11-21T07:30")
