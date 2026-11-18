"""여러 동선 한꺼번에: 구간별로 기존 판단을 이어서 계산(LLM 없음)."""
import datetime as dt

import pytest

from backend.agent.trip import TripError, plan_multi
from backend.db.database import init_db
from backend.events.bus import Emitter, EventBus
from backend.settings import get_settings
from backend.tools import registry
from tests.agent.test_graph import DAY, DEST, NEAR, NOW, ORIGIN, World, tr

D = dt.date.fromisoformat(DAY)


@pytest.fixture
def world(monkeypatch, tmp_path):
    w = World()
    monkeypatch.setattr(registry, "_TOOLS", w.tools())
    db = str(tmp_path / "t.db")
    init_db(db)
    w.db = db
    return w


def stop(p, **kw):
    return {"name": p["name"], "x": p["x"], "y": p["y"], **kw}


def run(world, stops, **kw):
    em = Emitter(EventBus(), "s", "r")
    out = plan_multi(stops, D, settings=get_settings(), emitter=em, db_path=world.db, now=lambda: NOW, **kw)
    return out, em.events


def test_three_stops_chain_departure_after_previous_arrival(world):
    world.trains = [tr("10:00", "11:50"), tr("13:00", "14:50", no="103")]
    stops = [stop(ORIGIN), stop(NEAR, stay_min=90), stop(DEST, arrive_by="16:00")]
    out, events = run(world, stops, depart_after="08:00")
    first, second = out["legs"]
    assert first["status"] == "done" and second["status"] == "done"
    leg1_arrive = first["cards"][0]["arrive_at"]
    lower = (dt.datetime.combine(D, dt.time.fromisoformat(leg1_arrive)) + dt.timedelta(minutes=90)).strftime("%H:%M")
    assert second["depart_after"] == lower
    assert second["cards"][0]["leave_at"] >= lower
    assert out["start_at"] == first["cards"][0]["leave_at"] and out["end_at"] == second["cards"][0]["arrive_at"]
    assert any(e["type"] == "plan_tasks" for e in events)


def test_leg_without_option_stops_the_chain(world):
    world.trains = [tr("10:00", "11:50")]
    stops = [stop(ORIGIN), stop(DEST, arrive_by="09:00"), stop(NEAR)]
    out, _ = run(world, stops, depart_after="08:00")
    assert out["legs"][0]["status"] == "no_option" and out["legs"][0]["reason"]
    assert out["legs"][1]["status"] == "skipped"


def test_requires_a_time_for_first_leg(world):
    with pytest.raises(TripError):
        run(world, [stop(ORIGIN), stop(DEST)])


def test_total_budget_warning(world):
    world.trains = [tr("10:00", "11:50", fare=42000)]
    out, _ = run(world, [stop(ORIGIN), stop(DEST, arrive_by="14:00")], budget=10000)
    assert out["total_fare"] > 10000 and any("예산" in w for w in out["warnings"])


def test_trip_api_validates_stop_count(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from backend.container import Container
    from backend.main import create_app
    from tests.fakes import FakeLLM
    monkeypatch.setenv("DB_PATH", str(tmp_path / "a.db"))
    w = World()
    monkeypatch.setattr(registry, "_TOOLS", w.tools())
    c = TestClient(create_app(Container.build(llm_factory=FakeLLM)), base_url="http://127.0.0.1")
    one = {"name": "a", "x": 126.8, "y": 35.2}
    assert c.post("/api/trips/plan", json={"date": DAY, "stops": [one]}).status_code == 422
    assert c.post("/api/trips/plan", json={"date": DAY, "stops": [one] * 7}).status_code == 422
    assert c.post("/api/trips/plan", json={"date": DAY, "stops": [one, one]}).status_code == 400  # 시각 없음
    r = c.post("/api/trips/plan", json={"date": DAY, "depart_after": "08:00",
                                        "stops": [stop(ORIGIN), stop(DEST, arrive_by="14:00")]})
    assert r.status_code == 200 and r.json()["legs"][0]["status"] == "done"
    assert r.json()["session_id"] in [s["session_id"] for s in c.get("/api/logs").json()]  # 실행 로그에 남음
