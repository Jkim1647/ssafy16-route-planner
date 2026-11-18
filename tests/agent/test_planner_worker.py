"""Planner·Worker 모드(F3021). test_graph의 가짜 세계를 재사용한다."""
import pytest

from backend.agent.planner_worker import WorkerDecision
from backend.tools import registry
from backend.tools.base import Tool, fail, ok
from tests.agent.test_graph import TRIP, A, Reply, env  # noqa: F401 — fixture 재사용


def worker_llm_calls(res):
    return [e for e in res.events if e["type"] == "worker_decision" and e["payload"].get("llm")]


def pw(make, **kw):
    return make(AGENT_MODE="planner_worker", **kw)


def test_agents_labeled_and_tasks_have_fixed_args(env):
    world, llm, make, _ = env
    llm.responses = [A("plan_trip", **TRIP), Reply(text="ok")]
    res = pw(make)("x")
    agents = {e["agent"] for e in res.events}
    assert {"planner", "worker", "logger"} <= agents
    plan = next(e for e in res.events if e["type"] == "plan_tasks")
    t1 = next(t for t in plan["payload"]["tasks"] if t["id"] == "t1")
    assert "query" in t1["fixed_args"]
    assert all(e["agent"] == "worker" for e in res.events if e["type"] == "tool_call")


def test_worker_no_llm_on_success(env):
    world, llm, make, _ = env
    llm.responses = [A("plan_trip", **TRIP), Reply(text="ok")]
    res = pw(make)("x")
    assert worker_llm_calls(res) == [] and res.llm_calls == 2 and res.cards


def test_worker_no_llm_on_invalid_key(env):
    world, llm, make, _ = env
    world.stations_err = "INVALID_KEY"
    llm.responses = [A("plan_trip", **TRIP)]
    res = pw(make)("x")
    assert worker_llm_calls(res) == [] and res.llm_calls == 1


def _flaky_stations(world, monkeypatch, radius_needed=40):
    tools = dict(registry._TOOLS)
    base = tools["find_stations"].func
    seen = []

    def stations(x, y, radius_km=20):
        seen.append(radius_km)
        if y < 36 and radius_km < radius_needed:
            return fail("NO_DATA", "근처 역 없음")
        return base(x=x, y=y, radius_km=radius_km)
    tools["find_stations"] = Tool("find_stations", "d", {"type": "object", "properties": {}}, stations, "external")
    monkeypatch.setattr(registry, "_TOOLS", tools)
    return seen


def test_worker_retry_on_no_data(env, monkeypatch):
    world, llm, make, _ = env
    seen = _flaky_stations(world, monkeypatch)
    llm.responses = [A("plan_trip", **TRIP),
                     WorkerDecision(action="retry", new_args={"radius_km": 40}, reason="반경을 넓힌다"),
                     Reply(text="ok")]
    res = pw(make)("x")
    assert 40 in seen and res.cards
    retry = [e for e in res.events if e["type"] == "tool_call" and e["payload"].get("retry_of")]
    assert retry and retry[0]["payload"]["args"]["radius_km"] == 40
    assert len(worker_llm_calls(res)) == 1


def test_worker_no_llm_when_no_tunable_args(env, monkeypatch):
    world, llm, make, _ = env
    tools = dict(registry._TOOLS)
    base = tools["search_trains"].func

    def trains(dep_station_id, arr_station_id, date=None):
        if dep_station_id == "GJ2":
            return fail("NO_DATA", "열차 없음")  # 역·날짜 모두 Planner가 정한 값 → Worker가 고칠 인자 없음
        return base(dep_station_id=dep_station_id, arr_station_id=arr_station_id, date=date)
    tools["search_trains"] = Tool("search_trains", "d", {"type": "object", "properties": {}}, trains, "external")
    monkeypatch.setattr(registry, "_TOOLS", tools)
    llm.responses = [A("plan_trip", **TRIP), Reply(text="ok")]
    res = pw(make)("x")
    nodata = [e for e in res.events if e["type"] == "worker_decision" and e["payload"]["tool"] == "search_trains"]
    assert nodata and all(not e["payload"]["llm"] for e in nodata)
    assert res.llm_calls == 2


def test_worker_cannot_change_fixed_args(env, monkeypatch):
    world, llm, make, _ = env
    seen = _flaky_stations(world, monkeypatch)
    llm.responses = [A("plan_trip", **TRIP),
                     WorkerDecision(action="retry", new_args={"x": 0.0, "y": 0.0}, reason="좌표를 바꾼다")]
    res = pw(make)("x")
    d = next(e for e in res.events if e["type"] == "worker_decision")
    assert d["payload"]["action"] == "skip" and "고정 인자" in d["payload"]["reason"]
    assert all(r == 20 for r in seen)


def test_worker_request_replan_reaches_planner(env, monkeypatch):
    world, llm, make, _ = env
    _flaky_stations(world, monkeypatch, radius_needed=999)
    llm.responses = [A("plan_trip", **TRIP),
                     WorkerDecision(action="request_replan", reason="역을 못 찾음")] + \
                    [WorkerDecision(action="skip", reason="그만")] * 5
    res = pw(make)("x")
    rp = [e for e in res.events if e["type"] == "replan"]
    assert rp and rp[0]["payload"]["source"] == "worker_request"


def test_worker_llm_off_skips(env, monkeypatch):
    world, llm, make, _ = env
    _flaky_stations(world, monkeypatch)
    llm.responses = [A("plan_trip", **TRIP)]
    res = pw(make, WORKER_LLM="off")("x")
    assert worker_llm_calls(res) == []
    d = [e for e in res.events if e["type"] == "worker_decision"]
    assert d and d[0]["payload"]["action"] == "skip"


def test_verify_warn_triggers_one_rebuild(env, monkeypatch):
    world, llm, make, _ = env
    monkeypatch.setenv("DEBUG_FORCE", "unplanned")
    llm.responses = [A("plan_trip", **TRIP), Reply(text="ok")]
    res = pw(make)("x")
    verifies = [e for e in res.events if e["type"] == "verify"]
    assert verifies and verifies[0]["agent"] == "logger" and verifies[0]["payload"]["verdict"] == "warn"
    rebuilds = [e for e in res.events if e["type"] == "replan" and e["payload"]["source"] == "verify"]
    assert len(rebuilds) == 1


def test_single_mode_unchanged(env):
    world, llm, make, _ = env
    llm.responses = [A("plan_trip", **TRIP), Reply(text="ok")]
    res = make()("x")
    assert not any(e["type"] in ("verify", "worker_decision") for e in res.events)
