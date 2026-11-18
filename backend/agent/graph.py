"""메인 Agent 그래프(LangGraph): 분석 → 계획 → 실행 → 판단 → (재계획) → 응답.

LLM 호출은 요청당 최대 2회: analyze(의도·조건 추출)와 respond(요약 문장). 나머지는 규칙·계산.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import time
from dataclasses import dataclass
from typing import Callable, Literal

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field

from backend.agent import prompts
from backend.agent.conditions import Conditions, merge, missing_fields
from backend.agent.ko_time import fix_changes
from backend.agent.executor import (FATAL, RunCtx, call_tool, make_plan, prev_day_ok, run_fact_query,
                                   run_plan_trip)
from backend.agent.judge import ROAD_MODES, Option, apply_warnings, evaluate, rank
from backend.agent.llm import LLMUnavailable, structured
from backend.agent.state import AgentState
from backend.schemas import PlanIn
from backend.tools.registry import get_tool

WEEKDAY = "월화수목금토일"


class Changes(BaseModel):
    origin: str | None = Field(None, description="출발지 이름(동네·건물·역)")
    destination: str | None = Field(None, description="도착지 이름")
    date: str | None = Field(None, description="이동 날짜 YYYY-MM-DD")
    arrive_by: str | None = Field(None, description="이 시각까지 도착해야 함. 시각만 HH:MM (날짜 넣지 말 것)")
    depart_after: str | None = Field(None, description="이 시각 이후 출발. 시각만 HH:MM")
    budget: int | None = Field(None, description="교통비 상한(원)")
    priority: Literal["cheapest", "fastest", "fewest_transfers"] | None = None
    avoid: list[str] | None = None


class AnalyzeOut(BaseModel):
    intent: Literal["plan_trip", "modify", "fact_query", "terms_query", "save_plan", "register_calendar", "chat"]
    intent_reason: str
    changes: Changes
    option_ref: int | None = None


class Reply(BaseModel):
    text: str


@dataclass
class Deps:
    llm_factory: Callable[[], object]
    plan_repo: object
    settings: object
    now: Callable[[], dt.datetime] = dt.datetime.now
    ctx: RunCtx | None = None  # 실행 1회분 문맥(service가 설정)


# ---------------------------------------------------------------- 공용
def _node(deps: Deps, name: str, fn):
    pw_roles = {"analyze": "planner", "plan": "planner", "replan": "planner", "execute": "worker", "verify": "logger"}
    agent = pw_roles.get(name, "main") if deps.settings.AGENT_MODE == "planner_worker" else "main"

    def wrapped(state: AgentState):
        em = deps.ctx.emitter
        em.emit("node_start", agent=agent, node=name)
        t0 = time.perf_counter()
        out = fn(state) or {}
        payload = {k: out[k] for k in ("intent", "intent_reason", "conditions", "missing", "status") if k in out}
        em.emit("node_end", agent=agent, node=name, payload=payload,
                duration_ms=int((time.perf_counter() - t0) * 1000))
        return out
    return wrapped


def _conds(state) -> Conditions:
    return Conditions(**(state.get("conditions") or {}))


def _hm(t: dt.datetime | None) -> str | None:
    return t.strftime("%H:%M") if t else None


def card(o: Option, i: int) -> dict:
    return {"index": i, "label": o.basis.get("label"), "date": o.leave_at.date().isoformat() if o.leave_at else None,
            "leave_at": _hm(o.leave_at), "arrive_at": _hm(o.arrive_at),
            "arrive_date": o.arrive_at.date().isoformat() if o.arrive_at else None,
            "total_fare": o.total_fare, "total_min": o.total_min, "transfers": o.transfers,
            "legs": [{"mode": lg.mode, "name": lg.name, "minutes": lg.minutes, "fare": lg.fare, "source": lg.source}
                     for lg in o.legs],
            "warnings": list(o.warnings), "estimated": o.estimated,
            "basis": {k: v for k, v in o.basis.items() if k != "rain_block"}}


def _brief(o: Option) -> str:
    train = next((lg.name for lg in o.legs if lg.mode == "train"), None)
    head = f"{train} " if train else ""
    return f"{head}{_hm(o.leave_at) or '?'} 출발 → {_hm(o.arrive_at) or '?'} 도착"


def numbers_ok(text: str, cards: list[dict]) -> bool:
    """응답 문장의 시각·금액이 모두 카드 데이터에 있는지 검사(LLM이 숫자를 지어내지 못하게)."""
    allowed_t, allowed_w = set(), set()
    for c in cards:
        allowed_t |= {c["leave_at"], c["arrive_at"]}
        for k, v in c["basis"].items():
            if isinstance(v, str) and re.fullmatch(r"\d{2}:\d{2}", v):
                allowed_t.add(v)
        for v in [c["total_fare"]] + [lg["fare"] for lg in c["legs"]] + \
                 [c["basis"].get(k) for k in ("train_fare", "access_fare", "egress_fare")]:
            if v is not None:
                allowed_w.add(int(v))
    # 한글이 바로 붙으면 \b가 통하지 않으므로 숫자 경계로 찾는다.
    times = {t.zfill(5) for t in re.findall(r"(?<!\d)\d{1,2}:\d{2}(?!\d)", text)}
    wons = {int(w.replace(",", "")) for w in re.findall(r"(\d[\d,]*)\s*원", text)}
    # "3시", "9만원"처럼 카드 값과 대조할 수 없는 숫자 표현은 통과시키지 않는다.
    loose = re.search(r"\d+\s*시(?!간)|\d+\s*[만천]\s*원", text)
    return not loose and times <= allowed_t and wons <= allowed_w


def _template_reply(cards: list[dict]) -> str:
    lines = [f"조건에 맞는 이동 방법 {len(cards)}가지를 찾았어요."]
    for c in cards:
        fare = f"총 {c['total_fare']:,}원" if c["total_fare"] is not None else "요금 일부 확인 불가"
        lines.append(f"{c['index']}) {c['label'] or '추천'}: {c['leave_at']} 출발 → {c['arrive_at']} 도착, {fare}")
    return "\n".join(lines)


# ---------------------------------------------------------------- 노드
def build_graph(deps: Deps):
    def analyze(state: AgentState):
        now = deps.now()
        prev = state.get("conditions") or {}
        cards = [{k: c[k] for k in ("index", "label", "leave_at", "arrive_at", "total_fare")}
                 for c in (state.get("last_cards") or [])]
        msgs = [("system", prompts.ANALYZE.format(today=now.date().isoformat(), weekday=WEEKDAY[now.weekday()],
                                                  conditions=json.dumps(prev, ensure_ascii=False),
                                                  cards=json.dumps(cards, ensure_ascii=False))),
                ("user", state["user_message"])]
        try:
            out: AnalyzeOut = structured(deps.llm_factory(), AnalyzeOut, msgs, deps.ctx.counter)
        except LLMUnavailable:
            return {"intent": "error", "status": "llm_unavailable",
                    "final_reply": "LLM 키(GMS_API_KEY)가 설정되지 않아 요청을 분석할 수 없어요. .env를 확인해 주세요."}
        changes = {k: v for k, v in out.changes.model_dump().items() if v is not None}
        if out.intent in ("plan_trip", "modify", "fact_query"):
            changes = fix_changes(changes, state["user_message"], now.date())
        base = Conditions(**prev) if out.intent in ("modify", "save_plan", "register_calendar") or prev else None
        if out.intent == "plan_trip" and prev and {"origin", "destination"} <= changes.keys():
            base = None  # 새 계획이면 이전 조건을 버린다
        conds = base or Conditions()
        for k, v in changes.items():  # 형식이 틀린 값은 버리고(지어내지 않음) 나머지만 반영
            try:
                conds = merge(conds, {k: v})
            except ValueError:
                pass
        deps.ctx.emitter.emit("llm_decision", node="analyze", payload={
            "decision": "intent", "value": out.intent, "reason": out.intent_reason, "changes": changes})
        c = conds.model_dump(mode="json")
        missing = missing_fields(conds, now) if out.intent in ("plan_trip", "modify") else []
        if out.intent == "fact_query":
            missing = [m for m in ("origin", "destination") if getattr(conds, m) is None]
        return {"intent": out.intent, "intent_reason": out.intent_reason, "conditions": c,
                "missing": missing, "option_ref": out.option_ref}

    def route_analyze(state: AgentState):
        it = state.get("intent")
        if it == "error":
            return "respond"
        if it == "chat":
            return "respond"
        if it in ("save_plan", "register_calendar"):
            return "action"
        if state.get("missing"):
            return "clarify"
        return "plan"

    def clarify(state: AgentState):
        q = " ".join(prompts.MISSING_Q[m] for m in state["missing"])
        return {"clarification": q, "final_reply": q, "status": "clarify"}

    def plan(state: AgentState):
        tasks = make_plan(state["intent"])
        deps.ctx.emitter.emit("plan_tasks", agent="planner" if deps.settings.AGENT_MODE == "planner_worker"
                              else "main", node="plan",
                              payload={"tasks": tasks, "strategy": state.get("strategy", 0)})
        return {"tasks": tasks}

    def execute(state: AgentState):
        ctx = deps.ctx
        ctx.options.clear()
        ctx.agent = "worker" if deps.settings.AGENT_MODE == "planner_worker" else "main"
        ctx.today = deps.now().date()
        conds = _conds(state)
        intent = state["intent"]
        if intent == "terms_query":
            r = call_tool(ctx, "t1", "search_terms", {"question": state["user_message"]}) \
                if get_tool("search_terms") else {"ok": False, "error": {"code": "NO_INDEX", "message": "규정 검색 미구성"}}
            return {"extra": {"terms": r}}
        if intent == "fact_query":
            res = run_fact_query(ctx, conds, state.get("places") or {}, deps.now().date())
            out = {"tool_errors": (state.get("tool_errors") or []) + res["errors"], "places": ctx.places,
                   "extra": {"facts": res}}
            if res.get("clarify"):
                out.update({"clarification": res["clarify"], "final_reply": res["clarify"], "status": "clarify"})
            return out
        res = run_plan_trip(ctx, conds, state.get("strategy", 0), state.get("places") or {})
        out = {"tool_errors": (state.get("tool_errors") or []) + res["errors"], "places": ctx.places,
               "extra": {"fatal": res["fatal"], "kind": res.get("kind"), "walk_m": res.get("walk_m")}}
        if res.get("clarify"):
            out.update({"clarification": res["clarify"], "final_reply": res["clarify"], "status": "clarify"})
        return out

    def judge(state: AgentState):
        ctx = deps.ctx
        conds = _conds(state)
        opts = apply_warnings(ctx.options, ctx.weather, [], conds.avoid)
        for o in opts:  # 캘린더 조회 실패처럼 모든 후보에 해당하는 안내
            o.warnings = o.warnings + [n for n in dict.fromkeys(ctx.notes) if n not in o.warnings]
        if os.getenv("DEBUG_FORCE", "").strip() == "replan" and state.get("replan_count", 0) < 2:
            opts = []  # 검증용: 과도한 재계획을 일부러 만든다(F3020)
        j = evaluate(opts, conds, ctx.busy, deps.now())
        ranked = rank(j.passed, conds.priority)
        _road_events(ctx, ranked, conds)
        cards = [card(o, i + 1) for i, o in enumerate(ranked)]
        excluded = [{"summary": _brief(o), "reason": r} for o, r in j.excluded][:8]
        undetermined = [{"summary": _brief(o), "reason": r} for o, r in j.undetermined][:5]
        warnings = sorted({w for o in ranked for w in o.warnings})
        return {"cards": cards, "excluded": excluded, "undetermined": undetermined,
                "estimated": [{"summary": _brief(o)} for o in j.estimated][:5], "warnings": warnings,
                "extra": {**(state.get("extra") or {}), "n_options": len(opts), "n_passed": len(j.passed)}}

    def route_judge(state: AgentState):
        if state.get("intent") == "terms_query" or state.get("status") == "clarify":
            return "respond"
        if state.get("cards"):
            return "respond"
        if (state.get("extra") or {}).get("fatal"):
            return "respond"
        if any(e["code"] in FATAL - {"BAD_ARGUMENT"} and e["tool"] in ("search_places", "find_stations", "search_trains")
               for e in state.get("tool_errors") or []):
            return "respond"
        if state.get("replan_count", 0) >= deps.settings.MAX_REPLAN:
            return "respond"
        if state.get("strategy", 0) >= 2 and not prev_day_ok(_conds(state), deps.now().date()):
            return "respond"  # 남은 전략(전날 출발)이 의미 없으면 재계획하지 않는다
        return "replan"

    def verify(state: AgentState):
        """로깅 Agent의 검증(F3021): 지금까지의 실행 이벤트를 규칙으로 판정해 Planner에 넘긴다(LLM 없음)."""
        from backend.events.anomaly import judge_run
        r = judge_run(deps.ctx.emitter.events, deps.settings.MAX_REPLAN)
        rules = sorted({f["rule"] for f in r["findings"]})
        deps.ctx.emitter.emit("verify", agent="logger", node="verify", payload={"verdict": r["verdict"], "rules": rules})
        return {"extra": {**(state.get("extra") or {}), "verify": r["verdict"], "verify_rules": rules}}

    def route_execute(state: AgentState):
        if state.get("intent") in ("terms_query", "fact_query"):
            return "respond"  # 판단(마감·예산 계산)이 필요 없는 질문
        if (state.get("extra") or {}).get("walk_m") is not None:
            return "respond"  # 걸어갈 거리
        return "verify" if deps.settings.AGENT_MODE == "planner_worker" else "judge"

    def route_verify(state: AgentState):
        ex = state.get("extra") or {}
        under_cap = state.get("replan_count", 0) < deps.settings.MAX_REPLAN
        if deps.ctx.replan_request and not state.get("worker_replanned") and under_cap:
            return "replan"
        if ex.get("verify") == "warn" and {"DUPLICATE_CALL", "UNPLANNED_CALL"} & set(ex.get("verify_rules", [])) \
                and not state.get("verify_rebuilt") and under_cap:
            return "replan"
        return "judge"

    def replan(state: AgentState):
        n = state.get("replan_count", 0) + 1
        strategy = state.get("strategy", 0) + 1
        names = {1: "거점 확장(근처 역 3곳까지)", 2: "수단 확장(택시 구간 포함)", 3: "전날 출발 후보 추가"}
        ex = state.get("extra") or {}
        out = {}
        if deps.ctx.replan_request and not state.get("worker_replanned"):
            source, reason = "worker_request", f"Worker 계획 변경 요청: {deps.ctx.replan_request}"
            deps.ctx.replan_request = None
            out["worker_replanned"] = True
        elif ex.get("verify") == "warn" and not state.get("verify_rebuilt") and \
                {"DUPLICATE_CALL", "UNPLANNED_CALL"} & set(ex.get("verify_rules", [])):
            source, reason = "verify", "로깅 Agent 검증 경고: " + ", ".join(ex.get("verify_rules", []))
            out["verify_rebuilt"] = True
        else:
            source, reason = "no_option", f"조건을 만족하는 후보 0개 (검토 {ex.get('n_options', 0)}개)"
        hist = (state.get("replan_history") or []) + [{"count": n, "strategy": names.get(strategy), "reason": reason,
                                                       "source": source}]
        deps.ctx.emitter.emit("replan", agent="planner" if deps.settings.AGENT_MODE == "planner_worker" else "main",
                              node="replan", payload={"count": n, "strategy": names.get(strategy), "reason": reason,
                                                      "source": source})
        return {"replan_count": n, "strategy": strategy, "replan_history": hist, **out}

    def respond(state: AgentState):
        if state.get("status") in ("clarify", "llm_unavailable"):
            return {}
        intent = state.get("intent")
        if intent == "chat":
            return {"final_reply": prompts.HELP, "status": "done"}
        if intent == "terms_query":
            return _terms_reply(state)
        if intent == "fact_query":
            return _fact_reply(state)
        walk_m = (state.get("extra") or {}).get("walk_m")
        if walk_m is not None:
            return {"final_reply": f"출발지와 도착지가 직선거리 약 {walk_m}m로 가까워 걸어서 이동하시면 돼요. "
                                   "이 거리는 대중교통 경로 검색 대상이 아니에요.", "status": "done", "last_cards": []}
        cards = state.get("cards") or []
        conds = _conds(state)
        errors = state.get("tool_errors") or []
        if not cards:
            # 이전 여정 카드를 지워 "1번 저장"이 옛 카드를 저장하지 않게 한다
            return {"final_reply": _no_option_reply(state, errors, deps.settings.MAX_REPLAN), "status": "no_option",
                    "last_cards": []}
        text = None
        try:
            msg = prompts.RESPOND.format(conditions=json.dumps(conds.model_dump(mode="json"), ensure_ascii=False),
                                         cards=json.dumps(cards, ensure_ascii=False),
                                         n_excluded=len(state.get("excluded") or []),
                                         n_undetermined=len(state.get("undetermined") or []),
                                         replans=state.get("replan_count", 0))
            text = structured(deps.llm_factory(), Reply, [("system", msg)], deps.ctx.counter).text
        except Exception:  # LLM 실패해도 템플릿으로 응답(NF3003)
            text = None
        if text is not None and not numbers_ok(text, cards):
            deps.ctx.emitter.emit("llm_decision", node="respond",
                                  payload={"decision": "reply_rejected", "reason": "카드에 없는 숫자 포함"})
            text = None
        reply = (text or _template_reply(cards)) + "\n" + prompts.DISCLAIMER
        return {"final_reply": reply, "status": "done", "last_cards": cards}

    def action(state: AgentState):
        if state["intent"] == "save_plan":
            return _save(state, deps)
        return _register(state, deps)

    g = StateGraph(AgentState)
    for name, fn in [("analyze", analyze), ("clarify", clarify), ("plan", plan), ("execute", execute),
                     ("verify", verify), ("judge", judge), ("replan", replan), ("respond", respond),
                     ("action", action)]:
        g.add_node(name, _node(deps, name, fn))
    g.add_edge(START, "analyze")
    g.add_conditional_edges("analyze", route_analyze, ["respond", "action", "clarify", "plan"])
    g.add_edge("clarify", END)
    g.add_edge("plan", "execute")
    g.add_conditional_edges("execute", route_execute, ["verify", "judge", "respond"])
    g.add_conditional_edges("verify", route_verify, ["replan", "judge"])
    g.add_conditional_edges("judge", route_judge, ["respond", "replan"])
    g.add_edge("replan", "plan")
    g.add_edge("respond", END)
    g.add_edge("action", END)
    return g.compile(checkpointer=InMemorySaver())


# ---------------------------------------------------------------- 응답 보조
def _road_events(ctx: RunCtx, ranked: list[Option], conds: Conditions) -> None:
    """판단이 끝난 최종 후보에 도로 구간이 있을 때만, 출발지 주변(약 5km) 돌발정보를 실행당 1회 조회(설계 19-5)."""
    origin = (ctx.places or {}).get("origin")
    if not ranked or origin is None or get_tool("get_road_events") is None:
        return
    if not any(leg.mode in ROAD_MODES for o in ranked for leg in o.legs):
        return
    m = 0.05
    r = call_tool(ctx, "t12", "get_road_events",
                  {"bbox": [origin["x"] - m, origin["y"] - m, origin["x"] + m, origin["y"] + m],
                   "date": conds.date.isoformat()})
    if r["ok"] and r["data"]["events"]:
        apply_warnings(ranked, {}, r["data"]["events"], [])


def _no_option_reply(state, errors, max_replan) -> str:
    keys = [e for e in errors if e["code"] in ("INVALID_KEY",)]
    if keys:
        tools = ", ".join(sorted({e["tool"] for e in keys}))
        return f"외부 API 키 설정 문제로 조회하지 못했어요({tools}). .env의 키를 확인해 주세요."
    other = [e for e in errors if e["tool"] in ("search_places", "find_stations", "search_trains")]
    if other and state.get("replan_count", 0) == 0:
        return "필요한 정보를 조회하지 못했어요: " + "; ".join(e["message"] for e in other[:2])
    tried = ", ".join(h["strategy"] for h in state.get("replan_history") or [])
    head = f"조건을 만족하는 이동 방법을 찾지 못했어요(재계획 {state.get('replan_count', 0)}/{max_replan}회"
    head += f": {tried})." if tried else ")."
    ex = state.get("excluded") or []
    if ex:
        head += " 예: " + "; ".join(f"{e['summary']} — {e['reason']}" for e in ex[:2]) + "."
    return head + " 도착 시각을 늦추거나 예산을 늘려 볼까요?"


def _terms_reply(state) -> dict:
    r = (state.get("extra") or {}).get("terms") or {}
    if not r.get("ok"):
        if r.get("error", {}).get("code") == "NO_INDEX":
            return {"final_reply": "아직 규정 문서를 색인하지 못했어요. 운송약관 원문을 확인해 주세요.", "status": "done"}
        return {"final_reply": "규정 문서를 검색하지 못했어요.", "status": "done"}
    chunks = r["data"]["chunks"][:3]
    body = "\n".join(f"- {c['text'][:200]} (출처: {c['title']}{', p.' + str(c['page']) if c.get('page') else ''})"
                     for c in chunks)
    return {"final_reply": "관련 규정을 찾았어요. 근거 문단과 출처를 확인해 주세요.\n" + body, "status": "done",
            "cards": [{"type": "source", **c} for c in chunks]}


def _fact_reply(state) -> dict:
    f = (state.get("extra") or {}).get("facts") or {}
    errors = state.get("tool_errors") or []
    if not f.get("trains"):
        if errors:
            return {"final_reply": "열차 시각을 조회하지 못했어요: " + "; ".join(e["message"] for e in errors[:2]),
                    "status": "no_option"}
        return {"final_reply": "해당 날짜·구간의 열차를 찾지 못했어요.", "status": "no_option"}
    c = Conditions(**(state.get("conditions") or {}))
    trains = [t for t in f["trains"]
              if (not c.arrive_by or t["arr_at"][11:16] <= c.arrive_by)
              and (not c.depart_after or t["dep_at"][11:16] >= c.depart_after)]
    head = f"{f['date']} {f['dep']}역 → {f['arr']}역 열차"
    if not trains:
        return {"final_reply": head + "는 있지만 말씀하신 시간 조건에 맞는 열차가 없어요.", "status": "no_option"}
    lines = [f"- {t['grade'] or ''} {t['train_no'] or ''} {t['dep_at'][11:16]} 출발 → {t['arr_at'][11:16]} 도착"
             + (f", {t['fare']:,}원" if t.get("fare") is not None else ", 운임 확인 불가") for t in trains[:10]]
    note = "\n(추정 시간표 — 실제 운행과 다를 수 있어요)" if f.get("estimated") else ""
    body = "\n".join(lines)
    return {"final_reply": f"{head} 시각이에요(시간표 조회 결과).\n{body}{note}\n{prompts.DISCLAIMER}",
            "status": "done"}


def _save(state, deps) -> dict:
    cards = state.get("last_cards") or []
    ref = state.get("option_ref")
    if not cards or not ref or not (1 <= ref <= len(cards)):
        return {"final_reply": "저장할 경로 번호를 알려 주세요. 먼저 이동 계획을 요청해 주세요.", "status": "clarify"}
    c = cards[ref - 1]
    conds = _conds(state)
    res = deps.plan_repo.create(PlanIn(
        title=f"{conds.origin} → {conds.destination}", date=dt.date.fromisoformat(c["date"]),
        leave_at=c["leave_at"], arrive_at=c["arrive_at"], origin_name=conds.origin or "-",
        destination_name=conds.destination or "-", legs=c["legs"], total_fare=c["total_fare"],
        source_run_id=deps.ctx.emitter.run_id))
    msg = f"{ref}번 경로를 이동 계획으로 저장했어요({c['date']} {c['leave_at']}~{c['arrive_at']})."
    if res.overlaps:
        msg += " 같은 날 시간이 겹치는 계획이 있어요: " + ", ".join(
            f"{p.title} {p.leave_at}~{p.arrive_at}" for p in res.overlaps)
    return {"final_reply": msg, "status": "done",
            "extra": {"saved_plan_id": res.plan.id, "overlaps": [p.id for p in res.overlaps]}}


def _register(state, deps) -> dict:
    if get_tool("register_calendar") is None:
        return {"final_reply": "캘린더 연동이 아직 설정되지 않았어요.", "status": "done"}
    plans = deps.plan_repo.list()
    if not plans:
        return {"final_reply": "먼저 이동 계획을 저장해 주세요.", "status": "clarify"}
    latest = max(plans, key=lambda p: p.id)
    deps.ctx.emitter.emit("plan_tasks", node="action", payload={"tasks": make_plan("register_calendar"), "strategy": 0})
    r = call_tool(deps.ctx, "t1", "register_calendar", {"plan_id": latest.id})
    if r["ok"]:
        return {"final_reply": f"'{latest.title}' 계획을 캘린더에 등록했어요.", "status": "done"}
    return {"final_reply": "캘린더 등록에 실패했어요: " + r["error"]["message"], "status": "done"}
