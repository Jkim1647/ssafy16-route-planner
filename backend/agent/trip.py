"""여러 동선 한꺼번에(LLM 없음): 지점 2~6개를 순서대로 잇고, 구간마다 기존 판단을 그대로 쓴다.

앞 구간에서 고른 경로의 도착 시각 + 그 지점에 머무는 시간 = 다음 구간의 출발 하한.
구간 하나에 맞는 경로가 없으면 그 뒤 구간은 계산하지 않는다(앞이 정해져야 뒤 출발 시각이 정해지므로).
"""
from __future__ import annotations

import datetime as dt

from backend.agent.conditions import Conditions
from backend.agent.executor import RunCtx, make_plan, run_plan_trip
from backend.agent.graph import _brief, card
from backend.agent.judge import apply_warnings, checks_for, evaluate, exclusion_kind, pareto_front, rank, risk_for
from backend.agent.llm import LLMCounter

STRATEGY = {1: "거점 확장(근처 역 3곳까지)", 2: "수단 확장(택시 구간 포함)", 3: "전날 출발 후보 추가"}


class TripError(ValueError):
    """요청만으로는 계산할 수 없음(예: 첫 구간의 시각이 없음)."""


def _place(s: dict) -> dict:
    return {"query": s["name"], "name": s["name"], "address": s.get("address"), "x": s["x"], "y": s["y"]}


def _plan_leg(n: int, conds: Conditions, places: dict, settings, emitter, db_path, now, reuse) -> dict:
    last_excluded: list = []
    for strategy in range(settings.MAX_REPLAN + 1):
        ctx = RunCtx(emitter=emitter, counter=LLMCounter(), db_path=db_path, reuse=reuse)
        ctx.today = now().date()
        emitter.emit("plan_tasks", node="plan", payload={"tasks": make_plan("plan_trip", strategy, conds.modes), "strategy": strategy, "leg": n})
        res = run_plan_trip(ctx, conds, strategy, dict(places))
        if res.get("walk_m") is not None:
            return {"status": "walk", "cards": [], "reason": f"직선거리 약 {res['walk_m']}m — 걸어서 이동하면 돼요"}
        opts = apply_warnings(ctx.options, ctx.weather, [], conds.avoid)
        for o in opts:
            o.warnings = o.warnings + [m for m in dict.fromkeys(ctx.notes) if m not in o.warnings]
        j = evaluate(opts, conds, ctx.busy, now())
        front = pareto_front(j.passed)
        ranked = rank(front, conds.priority)
        last_excluded = [{"summary": _brief(o), "reason": r} for o, r in j.excluded][:5]
        if ranked:
            cards = [card(o, i + 1) for i, o in enumerate(ranked)]
            for c, o in zip(cards, ranked):
                c["checks"] = checks_for(o, conds, ctx.busy, ctx.calendar_checked)
                c["risk"] = risk_for(o, conds)
            by: dict[str, int] = {}
            for _, r in j.excluded:
                by[exclusion_kind(r)] = by.get(exclusion_kind(r), 0) + 1
            return {"status": "done", "cards": cards, "excluded": last_excluded, "replan_count": strategy,
                    "decision": {"checked": len(opts), "passed": len(j.passed), "dominated": len(j.passed) - len(front),
                                 "excluded_by": by}}
        if res.get("fatal") or strategy == settings.MAX_REPLAN:
            break
        emitter.emit("replan", node="replan", payload={
            "count": strategy + 1, "strategy": STRATEGY.get(strategy + 1), "source": "no_option",
            "reason": f"{n}구간 조건을 만족하는 후보 0개 (검토 {len(opts)}개)"})
    reason = "; ".join(f"{e['summary']} — {e['reason']}" for e in last_excluded[:2]) or "조건에 맞는 경로를 찾지 못했어요"
    return {"status": "no_option", "cards": [], "excluded": last_excluded, "reason": reason}


def plan_multi(stops: list[dict], date: dt.date, *, settings, emitter, db_path, now,
               depart_after: str | None = None, budget: int | None = None, priority: str = "cheapest") -> dict:
    """지점 목록(stops: name·x·y, 두 번째부터 arrive_by·stay_min 선택)을 순서대로 이어 구간마다 경로를 고른다.
    반환 {legs, total_fare, start_at, end_at, warnings}; 각 leg의 status는 done·walk·no_option·skipped 등.
    지점이 2개 미만이거나 첫 구간 시각 기준이 없으면 TripError(사용자에게 보일 문장).
    """
    if len(stops) < 2:
        raise TripError("지점을 두 곳 이상 정해 주세요.")
    if not depart_after and not stops[1].get("arrive_by"):
        raise TripError("첫 구간의 출발 시각(언제부터)이나 첫 도착지의 도착 마감을 정해 주세요.")
    reuse: dict = {}
    legs, warnings = [], []
    lower, stopped = depart_after, False
    for i in range(len(stops) - 1):
        a, b = stops[i], stops[i + 1]
        leg = {"index": i + 1, "from": a["name"], "to": b["name"], "depart_after": lower, "arrive_by": b.get("arrive_by")}
        if stopped:
            legs.append({**leg, "status": "skipped", "cards": [], "reason": "앞 구간이 정해지지 않아 계산하지 않았어요"})
            continue
        if not lower and not b.get("arrive_by"):
            legs.append({**leg, "status": "no_option", "cards": [], "reason": "이 구간의 출발 시각을 정할 수 없어요"})
            stopped = True
            continue
        conds = Conditions(origin=a["name"], destination=b["name"], date=date, depart_after=lower,
                           arrive_by=b.get("arrive_by"), priority=priority)
        leg.update(_plan_leg(i + 1, conds, {"origin": _place(a), "destination": _place(b)}, settings, emitter, db_path,
                             now, reuse))
        legs.append(leg)
        if leg["status"] == "walk":  # 걷는 시간은 확인한 값이 없어 지어내지 않는다 → 다음 출발 하한은 그대로
            warnings.append(f"{a['name']} → {b['name']}은 걸어서 가는 거리라 걷는 시간은 계산에 넣지 않았어요")
            continue
        if leg["status"] != "done":
            stopped = True
            continue
        c = leg["cards"][0]
        arrived = dt.datetime.combine(dt.date.fromisoformat(c["arrive_date"]), dt.time.fromisoformat(c["arrive_at"]))
        nxt = arrived + dt.timedelta(minutes=int(b.get("stay_min") or 0))
        if nxt.date() != date and i < len(stops) - 2:
            warnings.append(f"{b['name']}에서 출발하는 시각이 다음 날이라 이후 구간은 계산하지 않았어요")
            stopped = True
        lower = nxt.strftime("%H:%M")
    done = [lg for lg in legs if lg["status"] == "done"]
    fares = [lg["cards"][0]["total_fare"] for lg in done]
    total = None if not done or any(f is None for f in fares) else sum(fares)
    if budget is not None and total is not None and total > budget:
        warnings.append(f"전체 요금 {total:,}원 > 예산 {budget:,}원")
    return {"legs": legs, "total_fare": total, "warnings": warnings,
            "start_at": done[0]["cards"][0]["leave_at"] if done else None,
            "end_at": done[-1]["cards"][0]["arrive_at"] if done else None}
