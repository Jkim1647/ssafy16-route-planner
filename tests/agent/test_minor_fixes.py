"""최종 리뷰의 작은 문제(Minor) 재현 테스트."""
import datetime as dt

import pytest

from backend.agent import service
from backend.agent.ko_time import parse_when
from backend.calendar.local import LocalCalendar
from backend.db.database import init_db
from backend.db.repositories import PlanRepo
from backend.events.anomaly import judge_run
from backend.schemas import PlanIn
from backend.tools import registry
from backend.tools.base import Tool, fail, ok
from tests.agent.test_graph import DAY, NOW, TRIP, A, AnalyzeOut, Changes, Reply, env, tr  # noqa: F401
from tests.helpers import route_get

TODAY = NOW.date()


def add_tool(monkeypatch, name, fn, kind="local"):
    tools = dict(registry._TOOLS)
    tools[name] = Tool(name, name, {"type": "object", "properties": {}}, fn, kind)
    monkeypatch.setattr(registry, "_TOOLS", tools)


def tool_calls(res):
    return [e["payload"] for e in res.events if e["type"] == "tool_call"]


# M1·M2. 걸어갈 거리(700m 미만)면 재계획 없이 도보 안내
def test_walking_distance_answers_without_replan(env):
    world, llm, make, _ = env
    world.places["첨단동주민센터"] = {"name": "첨단동주민센터", "address": "광주", "x": 126.842, "y": 35.221, "place_url": "u"}
    llm.responses = [A("plan_trip", origin="첨단동", destination="첨단동주민센터", date=DAY, arrive_by="14:00")]
    res = make()("x")
    assert res.replan_count == 0 and "걸어서" in res.reply
    assert {c["tool"] for c in tool_calls(res)} <= {"search_places", "get_weather", "get_free_busy"}


# M3. 한국어 시각 파서
def test_ko_time_invalid_date_does_not_raise():
    assert "date" not in parse_when("2월 30일 2시까지", TODAY)


def test_ko_time_hours_duration_is_not_clock_time():
    assert parse_when("3시간 안에 강남역", TODAY) == {}


def test_ko_time_depart_without_e():
    assert parse_when("오후 2시 출발", TODAY) == {"depart_after": "14:00"}


def test_ko_time_night_twelve_not_noon():
    assert parse_when("밤 12시까지", TODAY).get("arrive_by") != "12:00"


# M4. 채팅으로 캘린더 등록해도 계획 외 호출 경고가 없음
def test_chat_register_calendar_is_planned(env, monkeypatch):
    world, llm, make, db = env
    add_tool(monkeypatch, "register_calendar", lambda plan_id: ok({"event_id": "e1", "backend": "local"}))
    PlanRepo(db).create(PlanIn(title="a → b", date=dt.date(2026, 11, 21), leave_at="09:00", arrive_at="10:00",
                               origin_name="a", destination_name="b"))
    llm.responses = [AnalyzeOut(intent="register_calendar", intent_reason="등록", changes=Changes())]
    res = make()("캘린더에 넣어 줘")
    assert judge_run(res.events, 3)["verdict"] == "ok"


# M5. 날짜를 넘기는 겹침
def test_plan_overlap_across_midnight_dates(tmp_path):
    db = str(tmp_path / "a.db")
    init_db(db)
    repo = PlanRepo(db)
    repo.create(PlanIn(title="밤차", date=dt.date(2026, 11, 21), leave_at="23:00", arrive_at="02:00",
                       origin_name="a", destination_name="b"))
    res = repo.create(PlanIn(title="새벽", date=dt.date(2026, 11, 22), leave_at="00:30", arrive_at="01:00",
                             origin_name="a", destination_name="b"))
    assert [p.title for p in res.overlaps] == ["밤차"]


def test_local_calendar_multi_day(tmp_path):
    db = str(tmp_path / "a.db")
    init_db(db)
    cal = LocalCalendar(db)
    cal.add("새벽 일정", dt.datetime(2026, 11, 22, 0, 30), dt.datetime(2026, 11, 22, 1, 0))
    assert [b.title for b in cal.get_free_busy(dt.date(2026, 11, 21), days=2)] == ["새벽 일정"]


def test_overnight_trip_checks_next_day_calendar(env, monkeypatch):
    world, llm, make, _ = env
    world.trains = [{**tr("23:00", "01:30"), "arr_at": "2026-11-22T01:30"}]
    busy = [{"title": "새벽 일정", "start": "2026-11-22T00:30", "end": "2026-11-22T01:00"}]

    def free_busy(date, days=1):
        lo = dt.date.fromisoformat(date)
        return ok({"backend": "local", "busy": [b for b in busy
                                                if lo <= dt.date.fromisoformat(b["start"][:10]) < lo + dt.timedelta(days)]})
    add_tool(monkeypatch, "get_free_busy", free_busy)
    llm.responses = [A("plan_trip", origin="첨단동", destination="강남역", date=DAY, depart_after="22:00",
                       arrive_by="02:30")]
    res = make()("x")
    assert any("새벽 일정" in e["reason"] for e in res.excluded)


# M6. 캘린더 조회 실패를 알림
def test_calendar_failure_is_warned(env, monkeypatch):
    world, llm, make, _ = env
    add_tool(monkeypatch, "get_free_busy", lambda date, days=1: fail("UPSTREAM_ERROR", "캘린더 오류"))
    llm.responses = [A("plan_trip", **TRIP), Reply(text="ok")]
    res = make()("x")
    assert res.cards and any("캘린더" in w for w in res.cards[0]["warnings"])


# M7. 오늘 출발 요청에는 전날 출발 전략을 쓰지 않음
def test_today_request_skips_previous_day(env):
    world, llm, make, _ = env
    llm.responses = [A("plan_trip", origin="첨단동", destination="강남역", date=TODAY.isoformat(), arrive_by="18:00")]
    res = make()("x")
    assert all("전날" not in (e["payload"].get("strategy") or "") for e in res.events if e["type"] == "replan")
    yesterday = (TODAY - dt.timedelta(days=1)).isoformat()
    assert all(c["args"].get("date") != yesterday for c in tool_calls(res) if c["tool"] == "search_trains")


# M9. 오래된 대화 세션은 메모리에서 정리
def _graph(llm, db):
    from backend.agent.graph import Deps, build_graph
    from backend.db.repositories import EventRepo, RunRepo
    from backend.events.bus import build_bus
    from backend.settings import get_settings
    deps = Deps(llm_factory=lambda: llm, plan_repo=PlanRepo(db), settings=get_settings(), now=lambda: NOW)
    return build_graph(deps), deps, build_bus(EventRepo(db), enabled=True), RunRepo(db)


def test_old_sessions_evicted(env, monkeypatch):
    world, llm, make, db = env
    monkeypatch.setattr(service, "MAX_SESSIONS", 2)
    graph, deps, bus, runs = _graph(llm, db)
    for sid in ("a", "b", "c"):
        llm.responses = [A("chat")]
        service.run_turn(graph, deps, bus, runs, sid, "안녕")
    assert graph.checkpointer.get_tuple({"configurable": {"thread_id": "local:a"}}) is None  # 사용자:세션 키
    assert graph.checkpointer.get_tuple({"configurable": {"thread_id": "local:c"}}) is not None


# M10. 장소 이름·주소가 비어 있어도 죽지 않음
def test_ambiguity_check_handles_empty_names(monkeypatch):
    from backend.tools.kakao_local import search_places
    body = {"documents": [{"place_name": "", "address_name": "", "x": "127.0", "y": "37.5"},
                          {"place_name": "역", "address_name": "", "x": "127.1", "y": "37.6"}]}
    route_get(monkeypatch, [(lambda u, p: "kakao" in u, body)])
    assert search_places("역")["ok"]


# M11. 이상 징후 진단(LLM)은 전역 잠금 밖에서 실행
def test_after_run_outside_lock(env):
    world, llm, make, db = env
    seen = []
    graph, deps, bus, runs = _graph(llm, db)
    llm.responses = [A("chat")]
    service.run_turn(graph, deps, bus, runs, "s", "안녕", after_run=lambda rid: seen.append(service._lock.locked()))
    assert seen == [False]
