"""계획(작업 목록)과 실행(F3006·F3007). 계획은 의도별 규칙 템플릿 — GMS 한도 때문에 LLM을 쓰지 않는다(기획검증 6-1).

실행은 작업 목록 순서대로 Tool을 부르고, 앞선 결과(좌표·역 ID)를 다음 Tool 입력으로 넘긴다.
한 Tool이 실패해도 사유를 기록하고 나머지로 진행한다.
"""
from __future__ import annotations

import datetime as dt
import os
import time
from dataclasses import dataclass, field

from backend.agent.conditions import Conditions
from backend.agent.judge import (Busy, Option, Segment, build_intercity_options, build_intracity_options,
                                 is_intracity, segments_for)
from backend.tools.budget import default_budget, normalize_args
from backend.tools.registry import get_tool
from backend.tools.stations import haversine_km

ODSAY_PER_RUN = 4  # 설계 19-3
WALK_KM = 0.7  # ODsay가 경로를 주지 않는 거리(-98: 700m 이내) — 걸어갈 거리로 안내
FATAL = {"INVALID_KEY", "RATE_LIMITED", "UPSTREAM_ERROR", "BAD_ARGUMENT"}


@dataclass
class RunCtx:
    emitter: object
    counter: object
    agent: str = "main"
    options: list[Option] = field(default_factory=list)
    busy: list[Busy] = field(default_factory=list)
    weather: dict = field(default_factory=dict)
    places: dict = field(default_factory=dict)
    odsay_calls: int = 0
    calls: list[tuple[str, str]] = field(default_factory=list)  # (task_id, tool)
    # Planner·Worker 모드(F3021)
    mode: str = "single"
    worker_llm: bool = True
    max_retry: int = 2
    llm_factory: object = None
    replan_request: str | None = None
    # 실행 단위 결과 재사용(F3009): 재계획 때 같은 Tool·같은 입력은 다시 부르지 않는다
    reuse: dict = field(default_factory=dict)
    no_reuse: bool = False
    today: dt.date | None = None  # 오늘 날짜(그래프가 설정). 전날 출발 전략이 의미 있는지 판단
    notes: list[str] = field(default_factory=list)  # 모든 후보에 붙일 안내(예: 캘린더 조회 실패)
    calendar_checked: bool = False  # 캘린더를 실제로 조회해 판단에 반영했는가


# ---------------------------------------------------------------- 계획
PLAN_TRIP = [
    ("t1", "search_places", "출발지 이름 → 좌표", None),
    ("t2", "search_places", "도착지 이름 → 좌표", None),
    ("t3", "find_stations", "출발지 근처 기차역(역 ID)", "intercity"),
    ("t4", "find_stations", "도착지 근처 기차역(역 ID)", "intercity"),
    ("t5", "search_trains", "역 쌍별 열차 시간표·운임", "intercity"),
    ("t6", "get_transit_route", "장소↔역 구간 도보·지하철·버스", "intercity"),
    ("t7", "get_car_route", "장소↔역 구간 택시(대체·변형)", "intercity"),
    ("t8", "get_transit_route", "같은 도시 안 대중교통", "intracity"),
    ("t9", "get_car_route", "같은 도시 안 택시", "intracity"),
    ("t10", "get_weather", "출발·도착 지점 강수확률", None),
    ("t11", "get_free_busy", "그날 캘린더 일정", None),
    ("t12", "get_road_events", "최종 후보 도로 구간 돌발정보(판단 후 1회)", None),
    ("t13", "find_terminals", "고속버스 터미널(재계획 수단 확장)", "intercity"),
    ("t14", "search_express_bus", "고속버스 시간표·요금(재계획 수단 확장)", "intercity"),
]
FACT_QUERY = PLAN_TRIP[:5]
TERMS_QUERY = [("t1", "search_terms", "운송약관·행동요령 문서 검색", None)]
REGISTER = [("t1", "register_calendar", "최근 저장한 이동 계획을 캘린더에 등록", None)]


def make_plan(intent: str) -> list[dict]:
    from backend.agent.planner_worker import FIXED_ARGS
    template = {"plan_trip": PLAN_TRIP, "modify": PLAN_TRIP, "fact_query": FACT_QUERY,
                "terms_query": TERMS_QUERY, "register_calendar": REGISTER}.get(intent, [])
    return [{"id": i, "tool": t, "purpose": p, "when": w, "fixed_args": FIXED_ARGS.get(t, [])}
            for i, t, p, w in template if get_tool(t) is not None]


# ---------------------------------------------------------------- Tool 호출
def _summary(r: dict) -> str:
    if not r.get("ok"):
        return r["error"]["code"]
    d = r.get("data")
    if isinstance(d, dict):
        for k in ("places", "stations", "trains", "paths", "events", "busy", "chunks", "buses"):
            if k in d:
                return f"{k} {len(d[k])}건"
        return ", ".join(f"{k}={v}" for k, v in list(d.items())[:3] if not isinstance(v, (list, dict)))
    return "ok"


def call_tool(ctx: RunCtx, task_id: str, name: str, args: dict, retry_of: int | None = None) -> dict:
    r, call_seq = _call_once(ctx, task_id, name, args, retry_of)
    if ctx.mode == "planner_worker" and retry_of is None and not r.get("ok") and not r.get("reused"):
        r = _worker_on_failure(ctx, task_id, name, args, r, call_seq)
    return r


def _worker_on_failure(ctx: RunCtx, task_id: str, name: str, args: dict, r: dict, call_seq: int) -> dict:
    """Worker 판단(F3021). 고칠 여지가 있는 실패에서만 LLM을 부른다."""
    from backend.agent.planner_worker import RECOVERABLE, TUNABLE, decide, violates_fixed
    code = r["error"]["code"]
    em = ctx.emitter
    if code not in RECOVERABLE:
        em.emit("worker_decision", agent="worker", payload={"tool": name, "code": code, "action": "report",
                                                            "llm": False, "reason": "치명적 실패라 LLM 없이 보고"})
        return r
    if name not in TUNABLE:
        em.emit("worker_decision", agent="worker", payload={"tool": name, "code": code, "action": "skip", "llm": False,
                                                            "reason": "고칠 수 있는 인자가 없음(Planner가 정한 값뿐)"})
        return r
    if not ctx.worker_llm:
        em.emit("worker_decision", agent="worker", payload={"tool": name, "code": code, "action": "skip",
                                                            "llm": False, "reason": "WORKER_LLM=off"})
        return r
    schema = get_tool(name).parameters if get_tool(name) else {}
    for _ in range(ctx.max_retry):
        try:
            d = decide(ctx.llm_factory(), ctx.counter, name, args, r["error"], schema)
        except Exception:
            em.emit("worker_decision", agent="worker", payload={"tool": name, "code": code, "action": "skip",
                                                                "llm": True, "reason": "LLM 판단 실패"})
            return r
        action, reason = d.action, d.reason
        bad = violates_fixed(name, d.new_args)
        if action == "retry" and (bad or not d.new_args):
            action, reason = "skip", f"고정 인자 변경 시도({', '.join(bad)}) → 무효" if bad else "바꿀 인자가 없음"
        em.emit("worker_decision", agent="worker", payload={"tool": name, "code": code, "action": action, "llm": True,
                                                            "new_args": d.new_args, "reason": reason})
        if action == "request_replan":
            ctx.replan_request = reason
            return r
        if action != "retry":
            return r
        args = {**args, **d.new_args}
        r, _ = _call_once(ctx, task_id, name, args, retry_of=call_seq)
        if r.get("ok") or r["error"]["code"] not in RECOVERABLE:
            return r
    return r


def _call_once(ctx: RunCtx, task_id: str, name: str, args: dict, retry_of: int | None) -> tuple[dict, int]:
    call = ctx.emitter.emit("tool_call", agent=ctx.agent, payload={"task_id": task_id, "tool": name, "args": args,
                                                                   **({"retry_of": retry_of} if retry_of else {})})
    t0 = time.perf_counter()
    key = name + normalize_args(args)
    if key in ctx.reuse and not ctx.no_reuse:
        r = {**ctx.reuse[key], "cached": True, "reused": True}
    else:
        tool = get_tool(name)
        r = tool.run(**args) if tool else {"ok": False, "error": {"code": "NOT_FOUND", "message": f"{name} 없음"}}
        ctx.reuse[key] = {k: v for k, v in r.items() if k not in ("cached", "reused")}
    ms = int((time.perf_counter() - t0) * 1000)
    ctx.calls.append((task_id, name))
    ctx.emitter.emit("tool_result", agent=ctx.agent, duration_ms=ms,
                     payload={"task_id": task_id, "tool": name, "ok": r.get("ok"),
                              "code": None if r.get("ok") else r["error"]["code"],
                              "message": None if r.get("ok") else r["error"]["message"],
                              "summary": _summary(r), "cached": bool(r.get("cached"))})
    return r, call["seq"]


def point(kind: str, p: dict) -> dict:
    """지도 표시용 지점. Tool 결과(장소·역·터미널)의 이름과 좌표만 쓴다."""
    return {"kind": kind, "name": p["name"], "x": float(p["x"]), "y": float(p["y"])}


def _err(errors: list, task_id: str, tool: str, r: dict, note: str = "") -> None:
    errors.append({"task_id": task_id, "tool": tool, "code": r["error"]["code"],
                   "message": r["error"]["message"] + (f" ({note})" if note else "")})


# ---------------------------------------------------------------- 실행
def _at(conds: Conditions) -> str:
    t = conds.arrive_by or conds.depart_after
    return f"{conds.date.isoformat()}T{t}"


def _transit_allowed(ctx, args: dict) -> bool:
    """요청당 ODsay 상한(설계 19-3). 이번 실행에서 이미 조회한 구간은 재사용이라 세지 않는다."""
    if not ctx.no_reuse and "get_transit_route" + normalize_args(args) in ctx.reuse:
        return True
    if ctx.odsay_calls < ODSAY_PER_RUN:
        ctx.odsay_calls += 1
        return True
    return False


def _segment(ctx, errors, task_t, task_c, sx, sy, ex, ey, want_taxi) -> list[Segment]:
    transit, terr = None, None
    if _transit_allowed(ctx, {"sx": sx, "sy": sy, "ex": ex, "ey": ey}):
        r = call_tool(ctx, task_t, "get_transit_route", {"sx": sx, "sy": sy, "ex": ex, "ey": ey})
        if r["ok"]:
            transit = r["data"]
        else:
            terr = r["error"]["code"]
            _err(errors, task_t, "get_transit_route", r)
    else:
        terr = "RUN_CAP"
    car = None
    if want_taxi or transit is None:
        r = call_tool(ctx, task_c, "get_car_route", {"sx": sx, "sy": sy, "ex": ex, "ey": ey})
        car = r["data"] if r["ok"] else None
        if not r["ok"]:
            _err(errors, task_c, "get_car_route", r)
    segs = segments_for(transit, car, terr)
    if transit and not want_taxi:
        segs = [s for s in segs if s.kind == "transit"]
    return segs


def _places(ctx, conds, cached_places, errors) -> dict | None:
    """t1·t2: 출발·도착 장소 좌표. 실패하면 None(오류는 errors에 기록)."""
    places = dict(cached_places)
    for tid, key, q in (("t1", "origin", conds.origin), ("t2", "destination", conds.destination)):
        if key in places and places[key]["query"] == q:
            continue
        r = call_tool(ctx, tid, "search_places", {"query": q})
        if not r["ok"]:
            _err(errors, tid, "search_places", r)
            return None
        places[key] = {"query": q, **r["data"]["places"][0]}
    ctx.places = places
    return places


def run_fact_query(ctx: RunCtx, conds: Conditions, cached_places: dict, today: dt.date) -> dict:
    """사실 질문(열차 시각): 계획(FACT_QUERY = t1~t5)에 있는 Tool만 부른다. 날짜가 없으면 오늘."""
    errors: list[dict] = []
    day = conds.date or today
    places = _places(ctx, conds, cached_places, errors)
    if places is None:
        amb = next((e for e in errors if e["code"] == "AMBIGUOUS_PLACE"), None)
        return {"errors": errors, "trains": [], "clarify": amb and amb["message"] + " 어느 곳인가요?"}
    st = {}
    for tid, key in (("t3", "origin"), ("t4", "destination")):
        r = call_tool(ctx, tid, "find_stations", {"x": places[key]["x"], "y": places[key]["y"]})
        if not r["ok"]:
            _err(errors, tid, "find_stations", r)
            return {"errors": errors, "trains": [], "clarify": None}
        st[key] = r["data"]["stations"][0]
    so, sd = st["origin"], st["destination"]
    r = call_tool(ctx, "t5", "search_trains", {"dep_station_id": so["station_id"], "arr_station_id": sd["station_id"],
                                               "date": day.isoformat()})
    if not r["ok"]:
        _err(errors, "t5", "search_trains", r, f"{so['name']}→{sd['name']}")
        return {"errors": errors, "trains": [], "clarify": None}
    return {"errors": errors, "clarify": None, "date": day.isoformat(), "dep": so["name"], "arr": sd["name"],
            "trains": r["data"]["trains"], "estimated": r["data"].get("estimated", False)}


def run_plan_trip(ctx: RunCtx, conds: Conditions, strategy: int, cached_places: dict) -> dict:
    """반환: {"errors": [...], "fatal": bool, "clarify": str|None, "kind": intercity|intracity}"""
    errors: list[dict] = []
    places = dict(cached_places)
    for tid, key, q in (("t1", "origin", conds.origin), ("t2", "destination", conds.destination)):
        if key in places and places[key]["query"] == q:
            continue
        r = call_tool(ctx, tid, "search_places", {"query": q})
        if not r["ok"]:
            _err(errors, tid, "search_places", r)
            if r["error"]["code"] == "AMBIGUOUS_PLACE":
                return {"errors": errors, "fatal": True, "clarify": r["error"]["message"] + " 어느 곳인가요?"}
            return {"errors": errors, "fatal": True, "clarify": None}
        p = r["data"]["places"][0]
        places[key] = {"query": q, **p}
    ctx.places = places
    o, d = places["origin"], places["destination"]
    km = haversine_km(o["x"], o["y"], d["x"], d["y"])
    if km < WALK_KM:  # 재계획해도 결과가 없으므로 바로 도보 안내
        return {"errors": errors, "fatal": True, "clarify": None, "kind": "walk", "walk_m": int(km * 1000)}
    _debug_force(ctx, conds, o)
    _weather(ctx, conds, o, d)
    _calendar(ctx, conds, prev_day_ok(conds, ctx.today) and strategy >= 3)

    if is_intracity(o["x"], o["y"], d["x"], d["y"], same_station=False):
        return _intracity(ctx, conds, o, d, errors)

    n = 2 if strategy < 1 else 3
    st = {}
    for tid, key, pl in (("t3", "origin", o), ("t4", "destination", d)):
        r = call_tool(ctx, tid, "find_stations", {"x": pl["x"], "y": pl["y"]})
        if not r["ok"]:
            _err(errors, tid, "find_stations", r)
            return {"errors": errors, "fatal": r["error"]["code"] in FATAL, "clarify": None, "kind": "intercity"}
        st[key] = r["data"]["stations"][:n]
    if st["origin"][0]["station_id"] == st["destination"][0]["station_id"]:
        return _intracity(ctx, conds, o, d, errors)

    dates = [conds.date] + ([conds.date - dt.timedelta(days=1)]
                            if strategy >= 3 and prev_day_ok(conds, ctx.today) else [])
    want_taxi = strategy >= 2
    access = {s["station_id"]: _segment(ctx, errors, "t6", "t7", o["x"], o["y"], s["x"], s["y"], want_taxi)
              for s in st["origin"]}
    egress = {s["station_id"]: _segment(ctx, errors, "t6", "t7", s["x"], s["y"], d["x"], d["y"], want_taxi)
              for s in st["destination"]}
    fatal_trains = False
    for so in st["origin"]:
        for sd in st["destination"]:
            for day in dates:
                r = call_tool(ctx, "t5", "search_trains", {"dep_station_id": so["station_id"],
                                                           "arr_station_id": sd["station_id"], "date": day.isoformat()})
                if not r["ok"]:
                    _err(errors, "t5", "search_trains", r, f"{so['name']}→{sd['name']}")
                    fatal_trains |= r["error"]["code"] in FATAL
                    continue
                trains = [{**t, "estimated": r["data"].get("estimated", False)} for t in r["data"]["trains"]]
                for opt in build_intercity_options(trains, access[so["station_id"]], egress[sd["station_id"]]):
                    opt.id = f"{so['name']}-{sd['name']}-{opt.id}"
                    opt.basis.update({"dep_station": so["name"], "arr_station": sd["name"]})
                    opt.points = [point("origin", o), point("dep_station", so), point("arr_station", sd),
                                  point("destination", d)]
                    ctx.options.append(opt)
    if strategy >= 2:
        _bus_trunk(ctx, errors, o, d, dates)
    return {"errors": errors, "fatal": fatal_trains and not ctx.options, "clarify": None, "kind": "intercity"}


def _bus_trunk(ctx, errors, o, d, dates) -> None:
    """수단 확장(재계획 2단계): 고속버스를 간선 후보로 추가. 터미널 구간은 택시 기준(ODsay 상한 보호)."""
    if get_tool("find_terminals") is None or get_tool("search_express_bus") is None:
        return
    term = {}
    for key, pl in (("origin", o), ("destination", d)):
        r = call_tool(ctx, "t13", "find_terminals", {"x": pl["x"], "y": pl["y"]})
        if not r["ok"]:
            _err(errors, "t13", "find_terminals", r)
            return
        term[key] = r["data"]["terminals"][0]
    to, td = term["origin"], term["destination"]
    access = _segment(ctx, errors, "t6", "t7", o["x"], o["y"], to["x"], to["y"], True)
    egress = _segment(ctx, errors, "t6", "t7", td["x"], td["y"], d["x"], d["y"], True)
    for day in dates:
        r = call_tool(ctx, "t14", "search_express_bus", {"dep_terminal_id": to["terminal_id"],
                                                         "arr_terminal_id": td["terminal_id"], "date": day.isoformat()})
        if not r["ok"]:
            _err(errors, "t14", "search_express_bus", r, f"{to['name']}→{td['name']}")
            continue
        for opt in build_intercity_options(r["data"]["buses"], access, egress):
            opt.id = f"bus-{opt.id}"
            opt.basis.update({"dep_station": to["name"], "arr_station": td["name"]})
            opt.points = [point("origin", o), point("dep_station", to), point("arr_station", td),
                          point("destination", d)]
            ctx.options.append(opt)


def _debug_force(ctx, conds, o) -> None:
    """검증용(F3020 4.6): 이상 실행을 일부러 만든다. 기본값 꺼짐. 실제 호출을 하므로 판정이 정직하다."""
    mode = os.getenv("DEBUG_FORCE", "").strip()
    if mode == "duplicate":
        ctx.no_reuse = True
        try:
            with default_budget().no_cache():
                call_tool(ctx, "t1", "search_places", {"query": conds.origin})
        finally:
            ctx.no_reuse = False
    elif mode == "unplanned" and get_tool("get_weather"):
        call_tool(ctx, "t99", "get_weather", {"lat": o["y"], "lon": o["x"], "at": f"{conds.date}T12:00"})


def _intracity(ctx, conds, o, d, errors) -> dict:
    paths, car = [], None
    if _transit_allowed(ctx, {"sx": o["x"], "sy": o["y"], "ex": d["x"], "ey": d["y"]}):
        r = call_tool(ctx, "t8", "get_transit_route", {"sx": o["x"], "sy": o["y"], "ex": d["x"], "ey": d["y"]})
        if r["ok"]:
            paths = r["data"]["paths"]
        else:
            _err(errors, "t8", "get_transit_route", r)
    r = call_tool(ctx, "t9", "get_car_route", {"sx": o["x"], "sy": o["y"], "ex": d["x"], "ey": d["y"]})
    if r["ok"]:
        car = r["data"]
    else:
        _err(errors, "t9", "get_car_route", r)
    for opt in build_intracity_options(paths, car, conds):
        opt.points = [point("origin", o), point("destination", d)]
        ctx.options.append(opt)
    return {"errors": errors, "fatal": not ctx.options and any(e["code"] in FATAL for e in errors),
            "clarify": None, "kind": "intracity"}


def _weather(ctx, conds, o, d) -> None:
    if get_tool("get_weather") is None:
        return
    for key, pl in (("origin", o), ("destination", d)):
        r = call_tool(ctx, "t10", "get_weather", {"lat": pl["y"], "lon": pl["x"], "at": _at(conds)})
        ctx.weather[key] = r["data"] if r["ok"] else None


def prev_day_ok(conds: Conditions, today: dt.date | None) -> bool:
    """전날 출발 후보가 의미 있는가: 도착 마감이 있고, 전날이 이미 지나지 않았을 때만."""
    return bool(conds.arrive_by) and (today is None or conds.date - dt.timedelta(days=1) >= today)


def _calendar(ctx, conds, prev_day: bool) -> None:
    """이동이 걸칠 수 있는 날짜(전날 출발·자정 넘김 포함)의 일정을 한 번에 조회."""
    if get_tool("get_free_busy") is None:
        return
    start = conds.date - dt.timedelta(days=1) if prev_day else conds.date
    overnight = bool(conds.arrive_by and conds.depart_after and conds.arrive_by <= conds.depart_after)
    days = 1 + prev_day + overnight
    args = {"date": start.isoformat(), **({"days": days} if days > 1 else {})}
    r = call_tool(ctx, "t11", "get_free_busy", args)
    if r["ok"]:
        ctx.busy = [Busy(b["title"], dt.datetime.fromisoformat(b["start"]), dt.datetime.fromisoformat(b["end"]))
                    for b in r["data"]["busy"]]
        ctx.calendar_checked = True
    else:
        ctx.notes.append("캘린더 조회 실패 — 기존 일정과 겹치는지 확인하지 못했어요")
