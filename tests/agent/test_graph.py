"""그래프 시나리오 테스트: 가짜 LLM + 가짜 Tool(외부 호출 없음)."""
import datetime as dt

import pytest

from backend.agent.graph import AnalyzeOut, Changes, Deps, Reply, build_graph
from backend.agent.service import run_turn
from backend.db.database import init_db
from backend.db.repositories import EventRepo, PlanRepo, RunRepo
from backend.events.bus import build_bus
from backend.settings import get_settings
from backend.tools import registry
from backend.tools.base import Tool, fail, ok
from tests.fakes import FakeLLM

NOW = dt.datetime(2026, 11, 18, 11, 0)
DAY = "2026-11-21"
ORIGIN = {"name": "첨단동", "address": "광주 광산구", "x": 126.84, "y": 35.22, "place_url": "u"}
DEST = {"name": "강남역", "address": "서울 강남구", "x": 127.03, "y": 37.50, "place_url": "u"}
NEAR = {"name": "광주송정역", "address": "광주", "x": 126.85, "y": 35.23, "place_url": "u"}


def tr(dep, arr, fare=42000, no="101"):
    return {"train_no": no, "grade": "KTX", "dep_at": f"{DAY}T{dep}", "arr_at": f"{DAY}T{arr}", "fare": fare}


class World:
    """가짜 Tool 동작을 시나리오마다 바꾼다."""

    def __init__(self):
        self.places = {"첨단동": ORIGIN, "강남역": DEST, "광주송정역": NEAR}
        self.trains = [tr("10:00", "11:50"), tr("11:00", "12:50", 50000, "103")]
        self.transit = ok({"paths": [{"total_min": 30, "fare": 1500, "transfers": 0, "walk_min": 5,
                                      "legs": [{"mode": "walk", "name": None, "min": 5},
                                               {"mode": "bus", "name": "1002", "min": 25}]}]})
        self.car = ok({"duration_min": 20, "distance_km": 10, "taxi_fare": 15000, "toll": 0, "bbox": [0, 0, 1, 1]})
        self.stations_err = None
        self.calls = []

    def tools(self):
        def places(query, near_x=None, near_y=None):
            if query == "중앙역":
                return fail("AMBIGUOUS_PLACE", "같은 이름의 장소가 여러 지역에 있습니다: 중앙역(안산), 중앙역(부산)")
            p = self.places.get(query)
            return ok({"places": [p]}) if p else fail("NO_DATA", "없음")

        def stations(x, y, radius_km=20):
            if self.stations_err:
                return fail(self.stations_err, "역 오류")
            if y < 36:
                return ok({"stations": [{"station_id": "GJ1", "name": "광주송정", "x": 126.79, "y": 35.13, "distance_km": 5},
                                        {"station_id": "GJ2", "name": "광주", "x": 126.9, "y": 35.16, "distance_km": 9},
                                        {"station_id": "GJ3", "name": "나주", "x": 126.71, "y": 35.01, "distance_km": 19}]})
            return ok({"stations": [{"station_id": "SE1", "name": "용산", "x": 126.96, "y": 37.53, "distance_km": 7},
                                    {"station_id": "SE2", "name": "수서", "x": 127.1, "y": 37.48, "distance_km": 8}]})

        def trains(dep_station_id, arr_station_id, date=None):
            if dep_station_id == "GJ3" and self.second_station_trains is not None:
                return ok({"trains": self.second_station_trains, "estimated": False})
            ts = [t for t in self.trains if t["dep_at"].startswith(date or DAY)]
            return ok({"trains": ts, "estimated": False}) if ts else fail("NO_DATA", "열차 없음")

        def transit(sx, sy, ex, ey):
            return self.transit

        def car(sx, sy, ex, ey):
            return self.car

        def weather(lat, lon, at):
            return ok({"at": at, "pop": 20, "pty": "없음", "temp": 10.0})

        def wrap(name, fn):
            def run(**kw):
                self.calls.append(name)
                return fn(**kw)
            return Tool(name, name, {"type": "object", "properties": {}}, run, "external")

        return {n: wrap(n, f) for n, f in [("search_places", places), ("find_stations", stations),
                                            ("search_trains", trains), ("get_transit_route", transit),
                                            ("get_car_route", car), ("get_weather", weather)]}

    second_station_trains = None


@pytest.fixture
def env(tmp_path, monkeypatch):
    world = World()
    monkeypatch.setattr(registry, "_TOOLS", world.tools())
    db = str(tmp_path / "app.db")
    init_db(db)
    llm = FakeLLM()

    def make(**settings_env):
        for k, v in settings_env.items():
            monkeypatch.setenv(k, v)
        s = get_settings()
        deps = Deps(llm_factory=lambda: llm, plan_repo=PlanRepo(db), settings=s, now=lambda: NOW)
        bus = build_bus(EventRepo(db), enabled=s.LOGGING_ENABLED)
        graph = build_graph(deps)

        def turn(msg, session="s1"):
            return run_turn(graph, deps, bus, RunRepo(db), session, msg)
        return turn

    return world, llm, make, db


def A(intent, reason="이유", **changes):
    return AnalyzeOut(intent=intent, intent_reason=reason, changes=Changes(**changes))


TRIP = dict(origin="첨단동", destination="강남역", date=DAY, arrive_by="14:00")


def types(res):
    return [e["type"] for e in res.events]


def test_chat_skips_plan(env):
    world, llm, make, _ = env
    llm.responses = [A("chat", "인사")]
    res = make()("안녕")
    assert "tool_call" not in types(res) and "plan_tasks" not in types(res)
    assert res.llm_calls == 1 and "출발지" in res.reply


def test_missing_condition_asks(env):
    world, llm, make, _ = env
    llm.responses = [A("plan_trip", destination="서울", arrive_by="14:00")]
    res = make()("2시까지 서울 가야 해")
    assert res.clarification and "어디에서 출발" in res.clarification and "날짜" in res.clarification
    assert "tool_call" not in types(res)


def test_ambiguous_place_asks_user(env):
    world, llm, make, _ = env
    llm.responses = [A("plan_trip", origin="중앙역", destination="강남역", date=DAY, arrive_by="14:00")]
    res = make()("중앙역에서 강남역")
    assert res.status == "clarify" and "안산" in res.reply


def test_full_flow_events_order(env):
    world, llm, make, _ = env
    llm.responses = [A("plan_trip", "이동 계획 요청", **TRIP), Reply(text="좋은 경로를 찾았어요.")]
    res = make()("토요일 2시까지 첨단동에서 강남역")
    nodes = [e["node"] for e in res.events if e["type"] == "node_start"]
    assert nodes == ["analyze", "plan", "execute", "judge", "respond"]
    end = next(e for e in res.events if e["type"] == "node_end" and e["node"] == "analyze")
    assert end["payload"]["intent"] == "plan_trip" and end["payload"]["intent_reason"] == "이동 계획 요청"
    assert res.cards and res.cards[0]["label"] == "최저가"
    assert res.llm_calls == 2
    assert "확인하지 못했어요" in res.reply


def test_card_numbers_from_tools(env):
    world, llm, make, _ = env
    llm.responses = [A("plan_trip", **TRIP), Reply(text="ok")]
    c = make()("x").cards[0]
    # 10:00 열차 − 승차 여유 10분 − 출발 구간 30분 = 09:20
    assert c["leave_at"] == "09:20" and c["arrive_at"] == "12:20"
    assert c["total_fare"] == 1500 + 42000 + 1500


def test_tool_failure_continues(env):
    world, llm, make, _ = env
    world.transit = fail("UPSTREAM_ERROR", "down")
    llm.responses = [A("plan_trip", **TRIP), Reply(text="ok")]
    res = make()("x")
    assert res.cards  # 택시로 대체해서 계속 진행
    assert any("택시 기준" in w for w in res.cards[0]["warnings"])


def test_replan_reuses_cache_and_widens(env):
    world, llm, make, _ = env
    world.trains = [tr("12:30", "14:20")]  # 1번 역 기준으로는 마감 초과
    world.second_station_trains = [tr("09:00", "10:50", 41000, "201")]
    llm.responses = [A("plan_trip", **TRIP), Reply(text="ok")]
    res = make()("x")
    assert res.replan_count == 1 and res.cards
    rp = [e for e in res.events if e["type"] == "replan"]
    assert rp and "거점 확장" in rp[0]["payload"]["strategy"]
    # 장소 검색은 재계획 때 다시 부르지 않는다(이미 확보한 결과 재사용)
    assert world.calls.count("search_places") == 2


def test_replan_reuses_results_within_run_no_duplicates(env):
    from backend.events.anomaly import judge_run
    world, llm, make, _ = env
    world.trains = [tr("13:00", "15:00")]  # 계속 재계획
    llm.responses = [A("plan_trip", **TRIP)]
    res = make()("x")
    assert res.replan_count == 3
    assert world.calls.count("find_stations") == 2  # 재계획 때는 같은 입력을 다시 부르지 않는다
    assert world.calls.count("get_weather") == 2
    reused = [e for e in res.events if e["type"] == "tool_result" and e["payload"]["cached"]]
    assert reused
    assert "DUPLICATE_CALL" not in {f["rule"] for f in judge_run(res.events, 3)["findings"]}


def test_replan_limit_stops(env):
    world, llm, make, _ = env
    world.trains = [tr("13:00", "15:00")]
    llm.responses = [A("plan_trip", **TRIP)]
    res = make()("x")
    assert res.replan_count == 3 and not res.cards and res.status == "no_option"
    assert "늦추거나" in res.reply and "3/3" in res.reply


def test_upstream_failure_no_replan(env):
    world, llm, make, _ = env
    world.stations_err = "INVALID_KEY"
    llm.responses = [A("plan_trip", **TRIP)]
    res = make()("x")
    assert res.replan_count == 0 and "키" in res.reply


def test_followup_keeps_conditions(env):
    world, llm, make, _ = env
    turn = make()
    llm.responses = [A("plan_trip", **TRIP), Reply(text="ok"), A("modify", depart_after="09:00"), Reply(text="ok")]
    turn("x")
    res = turn("같은 조건에서 9시 이후 출발")
    start = next(e for e in res.events if e["type"] == "node_end" and e["node"] == "analyze")
    c = start["payload"]["conditions"]
    assert c["destination"] == "강남역" and c["date"] == DAY and c["arrive_by"] == "14:00" and c["depart_after"] == "09:00"


def test_respond_number_guard(env):
    world, llm, make, _ = env
    llm.responses = [A("plan_trip", **TRIP), Reply(text="08:15에 출발하면 33,000원이에요")]
    res = make()("x")
    assert "08:15" not in res.reply and "09:20" in res.reply
    assert any(e["type"] == "llm_decision" and e["payload"].get("decision") == "reply_rejected" for e in res.events)


def test_same_place_no_train_call(env):
    world, llm, make, _ = env
    llm.responses = [A("plan_trip", origin="첨단동", destination="광주송정역", date=DAY, arrive_by="14:00"),
                     Reply(text="ok")]
    res = make()("x")
    assert "search_trains" not in world.calls and res.cards


def test_main_works_without_logger(env):
    world, llm, make, db = env
    llm.responses = [A("plan_trip", **TRIP), Reply(text="ok")]
    res = make(LOGGING_ENABLED="false")("x")
    assert res.cards and EventRepo(db).get_session("s1") == []


def test_logged_events_match_response(env):
    world, llm, make, db = env
    llm.responses = [A("plan_trip", **TRIP), Reply(text="ok")]
    res = make()("x")
    assert [e["seq"] for e in EventRepo(db).get_session("s1")] == [e["seq"] for e in res.events]


def test_save_plan_from_card(env):
    world, llm, make, db = env
    turn = make()
    llm.responses = [A("plan_trip", **TRIP), Reply(text="ok"), A("save_plan"), ]
    turn("x")
    llm.responses = [AnalyzeOut(intent="save_plan", intent_reason="저장", changes=Changes(), option_ref=1)]
    res = turn("1번으로 저장")
    plans = PlanRepo(db).list()
    assert len(plans) == 1 and plans[0].leave_at == "09:20" and "저장" in res.reply


def test_llm_unavailable_message(env, monkeypatch):
    world, llm, make, _ = env
    from backend.agent.llm import LLMUnavailable

    def boom():
        raise LLMUnavailable("x")
    turn = make()
    llm.responses = [LLMUnavailable("x")]
    res = turn("x")
    assert "GMS_API_KEY" in res.reply


def test_llm_quota_message_explains_and_keeps_tools_unused(env):
    world, llm, make, _ = env
    from backend.agent.llm import LLMUnavailable
    llm.responses = [LLMUnavailable("한도", reason="quota")]
    res = make()("내일 오전 9시까지 첨단동에서 교육장 가야 해")
    assert res.status == "llm_unavailable"
    assert "사용 한도" in res.reply and "GMS_API_KEY" not in res.reply
    assert "여러 동선" in res.reply  # LLM 없이 되는 기능을 안내
    assert not [e for e in res.events if e["type"] == "tool_call"]


def test_odsay_calls_capped_per_run(env):
    world, llm, make, _ = env
    world.trains = [tr("13:00", "15:00")]  # 계속 재계획
    llm.responses = [A("plan_trip", **TRIP)]
    res = make()("x")
    real = [e for e in res.events if e["type"] == "tool_call" and e["payload"]["tool"] == "get_transit_route"]
    per_run_cap = 4 * (res.replan_count + 1)
    assert len(real) <= per_run_cap
    first_pass = []
    for e in res.events:
        if e["type"] == "replan":
            break
        if e["type"] == "tool_call" and e["payload"]["tool"] == "get_transit_route":
            first_pass.append(e)
    assert len(first_pass) <= 4


def test_first_pass_uses_two_stations_each_side(env):
    world, llm, make, _ = env
    llm.responses = [A("plan_trip", **TRIP), Reply(text="ok")]
    res = make()("x")
    pairs = {(e["payload"]["args"]["dep_station_id"], e["payload"]["args"]["arr_station_id"])
             for e in res.events if e["type"] == "tool_call" and e["payload"]["tool"] == "search_trains"}
    assert pairs == {("GJ1", "SE1"), ("GJ1", "SE2"), ("GJ2", "SE1"), ("GJ2", "SE2")}


def test_run_cap_note_differs_from_daily_limit(env):
    world, llm, make, _ = env
    world.trains = [tr("13:00", "15:00")]
    world.second_station_trains = None
    llm.responses = [A("plan_trip", **TRIP)]
    make()("x")
    from backend.agent.judge import segments_for
    seg = segments_for(None, {"duration_min": 10, "taxi_fare": 5000}, "RUN_CAP")[0]
    assert seg.note == "요청당 대중교통 조회 상한(4회) → 택시 기준"


def test_analyze_fixes_date_in_time_field(env):
    world, llm, make, _ = env
    llm.responses = [A("plan_trip", origin="첨단동", destination="강남역", arrive_by="2026-11-21"), Reply(text="ok")]
    res = make()("토요일 오후 2시까지 첨단동에서 강남역")
    end = next(e for e in res.events if e["type"] == "node_end" and e["node"] == "analyze")
    assert end["payload"]["conditions"]["date"] == "2026-11-21"
    assert end["payload"]["conditions"]["arrive_by"] == "14:00"
    assert res.cards


def _add_its(world, monkeypatch, events):
    calls = []

    def its(bbox, date):
        calls.append(bbox)
        return ok({"realtime": False, "events": events})
    tools = dict(registry._TOOLS)
    tools["get_road_events"] = Tool("get_road_events", "d", {"type": "object", "properties": {}}, its, "external")
    monkeypatch.setattr(registry, "_TOOLS", tools)
    return calls


def test_its_called_once_after_judge(env, monkeypatch):
    world, llm, make, _ = env
    calls = _add_its(world, monkeypatch, [{"type": "공사", "description": "국도22호선 시설물보수작업"}])
    llm.responses = [A("plan_trip", **TRIP), Reply(text="ok")]
    res = make()("x")
    assert len(calls) == 1
    seq = [e["node"] or e["payload"].get("tool") for e in res.events if e["type"] in ("node_start", "tool_call")]
    assert seq.index("get_road_events") > seq.index("judge")
    assert any("공사" in w for w in res.cards[0]["warnings"])  # 출발 구간에 버스가 있음


def test_its_not_called_without_road_legs(env, monkeypatch):
    world, llm, make, _ = env
    world.transit = ok({"paths": [{"total_min": 15, "fare": 1500, "transfers": 0, "walk_min": 3,
                                   "legs": [{"mode": "walk", "name": None, "min": 3},
                                            {"mode": "subway", "name": "1호선", "min": 12}]}]})
    calls = _add_its(world, monkeypatch, [])
    llm.responses = [A("plan_trip", **TRIP), Reply(text="ok")]
    make()("x")
    assert calls == []


def test_bus_added_on_mode_expansion(env, monkeypatch):
    world, llm, make, _ = env
    world.trains = [tr("13:00", "15:00")]  # 열차는 항상 마감 초과
    tools = dict(registry._TOOLS)
    bus_calls = []

    def terminals(x, y, radius_km=15):
        tid = "T_GJ" if y < 36 else "T_SE"
        return ok({"terminals": [{"terminal_id": tid, "name": tid, "x": x, "y": y, "distance_km": 3}]})

    def buses(dep_terminal_id, arr_terminal_id, date=None):
        bus_calls.append(date)
        return ok({"buses": [{"train_no": "R1-0800", "grade": "고속버스 우등", "dep_at": f"{DAY}T08:00",
                              "arr_at": f"{DAY}T12:00", "fare": 30000, "kind": "bus"}], "estimated": False})
    for n, f in (("find_terminals", terminals), ("search_express_bus", buses)):
        tools[n] = Tool(n, n, {"type": "object", "properties": {}}, f, "external")
    monkeypatch.setattr(registry, "_TOOLS", tools)
    llm.responses = [A("plan_trip", **TRIP), Reply(text="ok")]
    res = make()("x")
    assert res.replan_count == 2 and res.cards
    assert any(lg["source"] == "tago_bus" for lg in res.cards[0]["legs"])
    assert bus_calls  # 수단 확장(재계획 2) 전에는 부르지 않음
    first_replan = next(i for i, e in enumerate(res.events) if e["type"] == "replan")
    first_bus = next(i for i, e in enumerate(res.events)
                     if e["type"] == "tool_call" and e["payload"]["tool"] == "search_express_bus")
    assert first_bus > first_replan


def test_origin_at_station_walks_instead_of_route_api(env, monkeypatch):
    # 실사용 점검: 출발지가 역·터미널 자체면 길찾기 API가 같은 점에 NO_DATA → 후보가 모두 사라졌다
    world, llm, make, _ = env
    world.places["첨단동"] = {**ORIGIN, "x": 126.79, "y": 35.13}  # 광주송정(GJ1)과 같은 좌표
    tools = dict(registry._TOOLS)
    for n in ("get_transit_route", "get_car_route"):
        real = tools[n].func

        def same_point_fails(sx, sy, ex, ey, _real=real):
            return fail("NO_DATA", "같은 지점") if (sx, sy) == (ex, ey) else _real(sx=sx, sy=sy, ex=ex, ey=ey)
        tools[n] = Tool(n, n, {"type": "object", "properties": {}}, same_point_fails, "external")
    monkeypatch.setattr(registry, "_TOOLS", tools)
    llm.responses = [A("plan_trip", **TRIP), Reply(text="ok")]
    res = make()("x")
    from_gj1 = [c for c in res.cards if c["basis"].get("dep_station") == "광주송정"]
    assert from_gj1 and from_gj1[0]["legs"][0]["mode"] in ("walk", "train")


def _add_festivals(monkeypatch, result):
    tools = dict(registry._TOOLS)
    calls = []

    def festivals(x, y, date, radius_km=1.0):
        calls.append((x, y, date))
        return result
    tools["get_festivals"] = Tool("get_festivals", "f", {"type": "object", "properties": {}}, festivals, "external")
    monkeypatch.setattr(registry, "_TOOLS", tools)
    return calls


def test_festival_near_destination_warns(env, monkeypatch):
    world, llm, make, _ = env
    calls = _add_festivals(monkeypatch, ok({"festivals": [
        {"title": "강남 페스티벌", "start": "2026-11-18", "end": "2026-11-22", "address": "강남", "x": 1, "y": 2,
         "distance_km": 0.4}]}))
    llm.responses = [A("plan_trip", **TRIP), Reply(text="ok")]
    res = make()("x")
    assert calls and calls[0][2] == DAY  # 도착지 좌표·이동 날짜로 조회
    plan = next(e for e in res.events if e["type"] == "plan_tasks")
    assert "get_festivals" in [t["tool"] for t in plan["payload"]["tasks"]]
    assert res.cards and all(any("강남 페스티벌" in w for w in c["warnings"]) for c in res.cards)


def test_festival_failure_is_silent(env, monkeypatch):
    from backend.tools.base import UPSTREAM_ERROR, fail
    world, llm, make, _ = env
    _add_festivals(monkeypatch, fail(UPSTREAM_ERROR, "x"))
    llm.responses = [A("plan_trip", **TRIP), Reply(text="ok")]
    res = make()("x")
    assert res.cards and not any("행사" in w for c in res.cards for w in c["warnings"])


def test_bus_tries_next_terminal_when_nearest_has_none(env, monkeypatch):
    # 실사용 점검: 강남 최근접은 서울남부인데 광주행이 없고, 센트럴시티에는 있다
    from backend.tools.base import NO_DATA, fail
    world, llm, make, _ = env
    world.trains = [tr("13:00", "15:00")]
    tools = dict(registry._TOOLS)
    pairs = []

    def terminals(x, y, radius_km=15):
        if y < 36:
            return ok({"terminals": [{"terminal_id": "T_GJ", "name": "광주", "x": x, "y": y, "distance_km": 1}]})
        return ok({"terminals": [{"terminal_id": "T_NAMBU", "name": "서울남부", "x": x, "y": y, "distance_km": 1},
                                 {"terminal_id": "T_CENTRAL", "name": "센트럴시티", "x": x, "y": y, "distance_km": 2}]})

    def buses(dep_terminal_id, arr_terminal_id, date=None):
        pairs.append((dep_terminal_id, arr_terminal_id))
        if "T_CENTRAL" not in (dep_terminal_id, arr_terminal_id):
            return fail(NO_DATA, "없음")
        return ok({"buses": [{"train_no": "R1-0800", "grade": "고속버스 우등", "dep_at": f"{DAY}T08:00",
                              "arr_at": f"{DAY}T12:00", "fare": 30000, "kind": "bus"}], "estimated": False})
    for n, f in (("find_terminals", terminals), ("search_express_bus", buses)):
        tools[n] = Tool(n, n, {"type": "object", "properties": {}}, f, "external")
    monkeypatch.setattr(registry, "_TOOLS", tools)
    llm.responses = [A("plan_trip", **TRIP), Reply(text="ok")]
    res = make()("x")
    bus_cards = [c for c in res.cards if any(lg["source"] == "tago_bus" for lg in c["legs"])]
    assert bus_cards and "센트럴시티" in (bus_cards[0]["basis"]["dep_station"], bus_cards[0]["basis"]["arr_station"])
    assert len(set(pairs)) == 2  # 없는 쌍은 한 번만 보고 다음 터미널로


@pytest.mark.parametrize("mode,rule", [("duplicate", "DUPLICATE_CALL"), ("unplanned", "UNPLANNED_CALL"),
                                       ("replan", "EXCESSIVE_REPLAN")])
def test_debug_force_creates_detectable_anomaly(env, monkeypatch, mode, rule):
    from backend.events.anomaly import judge_run
    world, llm, make, _ = env
    monkeypatch.setenv("DEBUG_FORCE", mode)
    llm.responses = [A("plan_trip", **TRIP), Reply(text="ok")]
    res = make()("x")
    r = judge_run(res.events, 3)
    assert r["verdict"] == "warn" and rule in {f["rule"] for f in r["findings"]}


def test_calendar_busy_excludes_overlapping_options(env, monkeypatch):
    world, llm, make, _ = env
    tools = dict(registry._TOOLS)
    tools["get_free_busy"] = Tool("get_free_busy", "d", {"type": "object", "properties": {}},
                                  lambda date: ok({"backend": "local", "busy": [
                                      {"title": "팀 회의", "start": f"{DAY}T09:00", "end": f"{DAY}T09:30"}]}), "local")
    monkeypatch.setattr(registry, "_TOOLS", tools)
    llm.responses = [A("plan_trip", **TRIP), Reply(text="ok")]
    res = make()("x")
    # 10:00 열차 이동창(09:20~12:20)은 회의와 겹쳐 제외, 11:00 열차(10:20~)는 통과
    assert any("캘린더 '팀 회의'" in e["reason"] for e in res.excluded)
    assert res.cards and all(c["leave_at"] >= "09:30" for c in res.cards)


def test_terms_query_uses_rag_with_sources(env, monkeypatch):
    world, llm, make, _ = env
    tools = dict(registry._TOOLS)
    tools["search_terms"] = Tool("search_terms", "d", {"type": "object", "properties": {}}, lambda question, k=4: ok(
        {"chunks": [{"text": "출발 1시간 전까지 반환 시 위약금 5%", "source": "korail.md", "title": "여객운송약관",
                     "page": 3, "distance": 0.1}]}), "local")
    monkeypatch.setattr(registry, "_TOOLS", tools)
    llm.responses = [A("terms_query", "규정 질문")]
    res = make()("KTX 출발 30분 전 취소 위약금?")
    assert "여객운송약관" in res.reply and "p.3" in res.reply
    assert res.cards[0]["type"] == "source" and res.llm_calls == 1


def test_terms_query_without_index(env, monkeypatch):
    world, llm, make, _ = env
    tools = dict(registry._TOOLS)
    tools["search_terms"] = Tool("search_terms", "d", {"type": "object", "properties": {}},
                                 lambda question, k=4: fail("NO_INDEX", "없음"), "local")
    monkeypatch.setattr(registry, "_TOOLS", tools)
    llm.responses = [A("terms_query", "규정 질문")]
    assert "색인하지 못했어요" in make()("위약금?").reply


def test_rate_limited_falls_back_to_taxi_no_replan(env):
    world, llm, make, _ = env
    world.transit = fail("RATE_LIMITED", "한도")
    llm.responses = [A("plan_trip", **TRIP), Reply(text="ok")]
    res = make()("x")
    assert res.replan_count == 0 and res.cards
    assert "대중교통 조회 한도 초과 → 택시 기준" in res.cards[0]["warnings"]
