"""저장한 계획 당일 재확인: 시간표·날씨·캘린더·행사·출발 시각을 다시 보고 '그대로 괜찮음/주의'를 알려 준다(LLM 없음)."""
import datetime as dt

import pytest

from backend.agent.judge import Busy
from backend.agent.recheck import recheck_plan
from backend.schemas import PlanOut
from backend.tools import registry
from backend.tools.base import Tool, fail, ok
from tests.api.test_auth import make_client  # noqa: F401

DAY = dt.date(2026, 11, 21)
NOW = dt.datetime(2026, 11, 20, 20, 0)


def plan(**kw):
    base = dict(id=7, title="첨단동 → 강남역", date=DAY, leave_at="07:30", arrive_at="10:40", origin_name="첨단동",
                destination_name="강남역", total_fare=43700, created_at=NOW, updated_at=NOW,
                legs=[{"mode": "walk", "minutes": 12}, {"mode": "train", "name": "KTX 00406", "source": "tago_train"},
                      {"mode": "subway", "name": "2호선", "minutes": 20}],
                points=[{"kind": "origin", "name": "첨단동", "x": 126.84, "y": 35.22},
                        {"kind": "dep_station", "name": "광주송정", "x": 126.79, "y": 35.13},
                        {"kind": "arr_station", "name": "용산", "x": 126.96, "y": 37.53},
                        {"kind": "destination", "name": "강남역", "x": 127.03, "y": 37.50}])
    base.update(kw)
    return PlanOut(**base)


class FakeCal:
    def __init__(self, busy=()):
        self.busy = list(busy)

    def get_free_busy(self, day, days=1):
        return self.busy


@pytest.fixture
def tools(monkeypatch):
    state = {"trains": [{"train_no": "00406", "dep_at": f"{DAY}T07:41"}], "pop": 20, "festivals": [], "calls": []}

    def stations(x, y, radius_km=20):
        name = "광주송정" if y < 36 else "용산"
        return ok({"stations": [{"station_id": "S-" + name, "name": name, "x": x, "y": y, "distance_km": 1}]})

    def trains(dep_station_id, arr_station_id, date=None):
        state["calls"].append(("trains", dep_station_id, arr_station_id, date))
        return ok({"trains": state["trains"], "estimated": False})

    def weather(lat, lon, at):
        return ok({"pop": state["pop"]}) if state["pop"] is not None else fail("OUT_OF_RANGE", "범위 밖")

    def festivals(x, y, date, radius_km=1.0):
        return ok({"festivals": state["festivals"]})

    fake = {n: Tool(n, n, {"type": "object", "properties": {}}, f, "external") for n, f in
            [("find_stations", stations), ("search_trains", trains), ("get_weather", weather), ("get_festivals", festivals)]}
    monkeypatch.setattr(registry, "_TOOLS", fake)
    return state


def kinds(r, level):
    return {i["kind"] for i in r["items"] if i["level"] == level}


def test_all_fine(tools):
    r = recheck_plan(plan(), calendar=FakeCal(), now=NOW)
    assert r["status"] == "ok"
    assert {"train", "weather", "calendar"} <= kinds(r, "ok")
    assert ("trains", "S-광주송정", "S-용산", "2026-11-21") in tools["calls"]


def test_train_gone_from_timetable(tools):
    tools["trains"] = [{"train_no": "00410", "dep_at": f"{DAY}T08:10"}]
    r = recheck_plan(plan(), calendar=FakeCal(), now=NOW)
    assert r["status"] == "warn" and "train" in kinds(r, "warn")
    assert any("KTX 00406" in i["text"] for i in r["items"])


def test_new_calendar_event_overlaps(tools):
    busy = [Busy("팀 회의", dt.datetime(2026, 11, 21, 9, 0), dt.datetime(2026, 11, 21, 10, 0)),
            Busy("이동: 첨단동 → 강남역", dt.datetime(2026, 11, 21, 7, 30), dt.datetime(2026, 11, 21, 10, 40))]
    r = recheck_plan(plan(), calendar=FakeCal(busy), now=NOW)
    assert "calendar" in kinds(r, "warn")
    assert any("팀 회의" in i["text"] for i in r["items"]) and not any("이동: 첨단동" in i["text"] for i in r["items"])


def test_rain_with_long_walk(tools):
    tools["pop"] = 70
    r = recheck_plan(plan(), calendar=FakeCal(), now=NOW)
    assert "weather" in kinds(r, "warn") and any("70%" in i["text"] for i in r["items"])


def test_weather_out_of_range_is_info(tools):
    tools["pop"] = None
    r = recheck_plan(plan(), calendar=FakeCal(), now=NOW)
    assert "weather" in kinds(r, "info") and r["status"] == "ok"


def test_festival_near_destination(tools):
    tools["festivals"] = [{"title": "강남 페스티벌", "start": "2026-11-20", "end": "2026-11-22", "distance_km": 0.3}]
    r = recheck_plan(plan(), calendar=FakeCal(), now=NOW)
    assert "festival" in kinds(r, "warn")


def test_departure_passed(tools):
    r = recheck_plan(plan(), calendar=FakeCal(), now=dt.datetime(2026, 11, 21, 8, 0))
    assert r["status"] == "past" and "time" in kinds(r, "warn")


def test_calendar_failure_is_info_not_crash(tools):
    class Broken:
        def get_free_busy(self, day, days=1):
            raise RuntimeError("down")
    r = recheck_plan(plan(), calendar=Broken(), now=NOW)
    assert "calendar" in kinds(r, "info")


def test_old_plan_without_points_skips_train_check(tools):
    r = recheck_plan(plan(points=[]), calendar=FakeCal(), now=NOW)
    assert "train" in kinds(r, "info") and not tools["calls"]


def test_recheck_api(make_client, tools, monkeypatch):
    c = make_client(required=False)
    body = {k: v for k, v in plan().model_dump(mode="json").items() if k not in ("id", "created_at", "updated_at", "calendar_event_id")}
    pid = c.post("/api/plans", json=body).json()["plan"]["id"]
    monkeypatch.setenv("CALENDAR_BACKEND", "local")
    r = c.post(f"/api/plans/{pid}/recheck", json={})
    assert r.status_code == 200 and r.json()["status"] in ("ok", "warn", "past")
    assert c.post("/api/plans/9999/recheck", json={}).status_code == 404

