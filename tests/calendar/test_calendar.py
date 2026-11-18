import datetime as dt

import pytest

from backend.calendar.base import get_calendar
from backend.calendar.local import LocalCalendar
from backend.db.database import init_db
from backend.db.repositories import PlanRepo
from backend.schemas import PlanIn
from backend.tools import calendar_tools
from backend.tools.calendar_tools import get_free_busy, register_calendar


@pytest.fixture
def db(tmp_path, monkeypatch):
    path = str(tmp_path / "app.db")
    init_db(path)
    monkeypatch.setenv("DB_PATH", path)
    monkeypatch.setenv("CALENDAR_BACKEND", "local")
    return path


def add_plan(db, date="2026-11-21", leave="07:45", arrive="10:52"):
    return PlanRepo(db).create(PlanIn(title="첨단동 → 강남역", date=dt.date.fromisoformat(date), leave_at=leave,
                                      arrive_at=arrive, origin_name="첨단동", destination_name="강남역")).plan


def test_local_free_busy_roundtrip(db):
    cal = LocalCalendar(db)
    cal.add("팀 회의", dt.datetime(2026, 11, 21, 7, 0), dt.datetime(2026, 11, 21, 8, 0))
    cal.add("다른 날", dt.datetime(2026, 11, 22, 7, 0), dt.datetime(2026, 11, 22, 8, 0))
    busy = cal.get_free_busy(dt.date(2026, 11, 21))
    assert [(b.title, b.start.hour) for b in busy] == [("팀 회의", 7)]


def test_get_free_busy_tool_shape(db):
    LocalCalendar(db).add("팀 회의", dt.datetime(2026, 11, 21, 7, 0), dt.datetime(2026, 11, 21, 8, 0))
    r = get_free_busy("2026-11-21")
    assert r["ok"] and r["data"]["busy"] == [{"title": "팀 회의", "start": "2026-11-21T07:00", "end": "2026-11-21T08:00"}]
    assert r["data"]["backend"] == "local"


def test_register_reads_plan_from_repo(db):
    p = add_plan(db)
    r = register_calendar(p.id)
    assert r["ok"] and r["data"]["event_id"]
    busy = get_free_busy("2026-11-21")["data"]["busy"]
    assert busy == [{"title": "이동: 첨단동 → 강남역", "start": "2026-11-21T07:45", "end": "2026-11-21T10:52"}]
    assert PlanRepo(db).get(p.id).calendar_event_id == r["data"]["event_id"]


def test_register_overnight_plan(db):
    p = add_plan(db, leave="23:40", arrive="02:10")
    register_calendar(p.id)
    b = get_free_busy("2026-11-21")["data"]["busy"][0]
    assert b["end"] == "2026-11-22T02:10"


def test_register_schema_only_plan_id():
    from backend.tools.registry import get_tool
    assert list(get_tool("register_calendar").parameters["properties"]) == ["plan_id"]


def test_register_unknown_plan_not_found(db):
    assert register_calendar(999)["error"]["code"] == "NOT_FOUND"


def test_free_busy_bad_date(db):
    assert get_free_busy("내일")["error"]["code"] == "BAD_ARGUMENT"


def test_backend_swap_same_shape(db, monkeypatch):
    class FakeGoogle:
        name = "google"

        def get_free_busy(self, day):
            from backend.agent.judge import Busy
            return [Busy("일정", dt.datetime(2026, 11, 21, 9), dt.datetime(2026, 11, 21, 10))]

        def create_event(self, plan):
            return "g-1"
    monkeypatch.setattr(calendar_tools, "get_calendar", lambda s: FakeGoogle())
    r = get_free_busy("2026-11-21")
    assert set(r["data"]) == {"busy", "backend"} and set(r["data"]["busy"][0]) == {"title", "start", "end"}
    assert register_calendar(add_plan(db).id)["data"] == {"event_id": "g-1", "backend": "google"}


def test_get_calendar_local(db):
    from backend.settings import get_settings
    assert get_calendar(get_settings()).name == "local"
