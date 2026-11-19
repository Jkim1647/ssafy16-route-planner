"""캘린더 일정으로 경로 제안: 앞으로 이틀 안의 장소 있는 일정을 찾아 장소 좌표를 붙인다(LLM 없음, 누르기 전엔 경로 계산 안 함)."""
import datetime as dt

import pytest

from backend.agent.suggest import calendar_suggestions
from backend.calendar.google import GoogleCalendar
from backend.tools import registry
from backend.tools.base import Tool, fail, ok
from tests.api.test_auth import make_client  # noqa: F401

NOW = dt.datetime(2026, 11, 19, 10, 0)


class FakeCal:
    def __init__(self, events):
        self.events = events
        self.asked = None

    def upcoming_events(self, start, days=2):
        self.asked = (start, days)
        return self.events


def ev(title, start, location=None, minutes=60):
    s = dt.datetime.fromisoformat(start)
    return {"title": title, "start": s, "end": s + dt.timedelta(minutes=minutes), "location": location}


@pytest.fixture
def places(monkeypatch):
    calls = []

    def search(query, near_x=None, near_y=None):
        calls.append(query)
        if query == "없는곳":
            return fail("NO_DATA", "없음")
        return ok({"places": [{"name": query + "(검색)", "address": "주소", "x": 127.0, "y": 37.5}]})
    monkeypatch.setattr(registry, "_TOOLS", {"search_places": Tool("search_places", "s", {}, search, "external")})
    return calls


def test_suggests_events_with_location(places):
    cal = FakeCal([ev("팀 회의", "2026-11-20T14:00", "강남역"), ev("점심", "2026-11-19T12:00"),
                   ev("이동: 첨단동 → 강남역", "2026-11-20T09:00", "강남역"), ev("지난 일", "2026-11-19T09:00", "광주역")])
    out = calendar_suggestions(cal, NOW)
    assert [s["title"] for s in out] == ["팀 회의"]  # 장소 없음·우리 이동 일정·이미 시작한 일정 제외
    s = out[0]
    assert s["date"] == "2026-11-20" and s["arrive_by"] == "14:00" and s["location"] == "강남역"
    assert s["place"] == {"name": "강남역(검색)", "address": "주소", "x": 127.0, "y": 37.5}
    assert cal.asked == (NOW, 2)


def test_unknown_location_kept_without_place(places):
    out = calendar_suggestions(FakeCal([ev("모임", "2026-11-20T18:00", "없는곳")]), NOW)
    assert out[0]["place"] is None


def test_at_most_five_and_calendar_failure(places):
    many = [ev(f"일정{i}", f"2026-11-20T{9 + i:02d}:00", "강남역") for i in range(8)]
    assert len(calendar_suggestions(FakeCal(many), NOW)) == 5

    class Broken:
        def upcoming_events(self, start, days=2):
            raise RuntimeError("down")
    assert calendar_suggestions(Broken(), NOW) == []


def test_google_upcoming_events_reads_location(monkeypatch):
    class Svc:
        params = None

        def events(self):
            return self

        def list(self, **kw):
            Svc.params = kw
            return self

        def execute(self):
            return {"items": [{"summary": "팀 회의", "location": "강남역",
                               "start": {"dateTime": "2026-11-20T14:00:00+09:00"}, "end": {"dateTime": "2026-11-20T15:00:00+09:00"}},
                              {"summary": "하루 종일", "start": {"date": "2026-11-21"}, "end": {"date": "2026-11-22"}}]}
    cal = GoogleCalendar()
    monkeypatch.setattr(cal, "_service", lambda: Svc())
    out = cal.upcoming_events(NOW, days=2)
    assert out == [{"title": "팀 회의", "start": dt.datetime(2026, 11, 20, 14, 0), "end": dt.datetime(2026, 11, 20, 15, 0),
                    "location": "강남역"}]  # 종일 일정은 도착 시각이 없어 뺀다
    assert Svc.params["singleEvents"] is True and Svc.params["orderBy"] == "startTime"


def test_suggestions_api_local_calendar(make_client, monkeypatch, places):
    monkeypatch.setenv("CALENDAR_BACKEND", "local")
    c = make_client(required=False)
    r = c.get("/api/suggestions/calendar")
    assert r.status_code == 200 and r.json() == []  # 로컬 캘린더에는 장소가 없다
