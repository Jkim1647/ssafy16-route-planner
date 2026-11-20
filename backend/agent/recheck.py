"""저장한 계획 다시 확인(당일 재확인). 저장 뒤 바뀌었을 수 있는 것만 규칙으로 다시 본다(LLM 없음).

- 시간표: 열차 구간의 열차 번호가 그날 시간표에 아직 있는지, 소요 시간이 같은지(TAGO, 캐시 없이).
  계획에 열차 출발 시각은 저장하지 않아 시각 자체는 비교하지 않는다(소요 시간이 같으면 시각 변경은 못 잡는다)
- 캘린더: 이동 시간과 겹치는 일정(이 계획을 등록한 '이동:' 일정은 제외)
- 날씨: 출발·도착 지점 강수확률, 도보가 길면 주의
- 행사: 도착지 근처 그날 행사(혼잡 참고)
- 출발 시각: 이미 지났는지
결과 status: ok(모두 확인했고 그대로 가도 됨) · warn(주의할 것 있음 → 다른 경로 찾기 권장)
· partial(확인하지 못한 항목이 있음 — "괜찮다"고 말하지 않는다) · past(출발 시각 지남)
항목 level: ok · warn · info(참고) · unknown(조회 실패·예보 없음 등으로 확인 못 함)
"""
from __future__ import annotations

import datetime as dt

from backend.agent.judge import RAIN_POP, WALK_WARN_MIN
from backend.calendar.base import plan_span
from backend.tools.budget import default_budget
from backend.tools.registry import get_tool


def _run(name: str, **kw) -> dict | None:
    tool = get_tool(name)
    return tool.run(**kw) if tool else None


def _item(kind: str, level: str, text: str) -> dict:
    return {"kind": kind, "level": level, "text": text}


def _minutes(dep: str | None, arr: str | None) -> int | None:
    try:
        return int((dt.datetime.fromisoformat(arr) - dt.datetime.fromisoformat(dep)).total_seconds() // 60)
    except (TypeError, ValueError):
        return None


def _train_items(plan, day: dt.date) -> list[dict]:
    trains = [lg for lg in plan.legs if (lg.source or "") == "tago_train" and lg.name]
    if not trains:
        return []
    pts = {p.kind: p for p in plan.points}
    dep, arr = pts.get("dep_station"), pts.get("arr_station")
    if not (dep and arr):
        return [_item("train", "unknown", "역 정보가 없는 예전 계획이라 열차 시간표는 다시 확인하지 못했어요")]

    def station_id(p):
        r = _run("find_stations", x=p.x, y=p.y)
        st = (r or {}).get("data", {}).get("stations", []) if r and r["ok"] else []
        same = [s for s in st if s["name"] == p.name]
        return (same or st or [{}])[0].get("station_id")

    sid_dep, sid_arr = station_id(dep), station_id(arr)
    if not (sid_dep and sid_arr):
        return [_item("train", "unknown", "역을 다시 찾지 못해 열차 시간표는 확인하지 못했어요")]
    with default_budget().no_cache():  # 재확인은 지금의 시간표를 봐야 한다(최대 24시간 캐시를 쓰지 않음)
        r = _run("search_trains", dep_station_id=sid_dep, arr_station_id=sid_arr, date=day.isoformat())
    if not r or not r["ok"]:
        return [_item("train", "unknown", "열차 시간표를 지금 조회하지 못했어요")]
    listed = {str(t.get("train_no")).lstrip("0"): t for t in r["data"]["trains"]}
    out = []
    for lg in trains:
        no = lg.name.split()[-1].lstrip("0")
        if no in listed:
            # 계획에는 열차 시각이 없고 소요 시간(분)만 있다 → 소요 시간이 달라졌으면 운행 시각이 바뀐 것으로 본다
            t = listed[no]
            now_min = _minutes(t.get("dep_at"), t.get("arr_at"))
            if lg.minutes is not None and now_min is not None and abs(now_min - lg.minutes) >= 5:
                out.append(_item("train", "warn", f"{lg.name} 소요 시간이 {lg.minutes}분 → {now_min}분으로 달라졌어요"
                                                  "(운행 시각 변경 가능 — 예매처에서 시각을 확인하세요)"))
            else:
                same = "소요 시간도 같아요" if now_min is not None and lg.minutes is not None else "시각은 비교하지 못했어요"
                out.append(_item("train", "ok", f"{lg.name} 열차 번호가 그날 시간표에 그대로 있어요({same})"))
        else:
            out.append(_item("train", "warn", f"{lg.name}을(를) 그날 시간표에서 찾지 못했어요(운휴·변경 가능)"))
    if r["data"].get("estimated"):
        out.append(_item("train", "info", "아직 그날 시간표가 열리지 않아 같은 요일 시간표로 봤어요"))
    return out


def _calendar_items(plan, calendar, start: dt.datetime, end: dt.datetime) -> list[dict]:
    try:
        busy = calendar.get_free_busy(start.date(), days=2 if end.date() > start.date() else 1)
    except Exception:  # 캘린더 연결 실패는 재확인 전체를 막지 않는다
        return [_item("calendar", "unknown", "캘린더를 지금 조회하지 못했어요")]
    own = f"이동: {plan.title}"
    clash = [b for b in busy if b.title != own and b.start < end and start < b.end]
    if not clash:
        return [_item("calendar", "ok", "이동 시간과 겹치는 일정이 없어요")]
    return [_item("calendar", "warn", f"'{b.title}' {b.start:%H:%M}–{b.end:%H:%M} 일정과 겹쳐요") for b in clash[:3]]


def _weather_items(plan, start: dt.datetime, end: dt.datetime) -> list[dict]:
    pts = {p.kind: p for p in plan.points}
    walk = sum(lg.minutes or 0 for lg in plan.legs if lg.mode == "walk")
    pops, got, missed = [], [], []
    for kind, at, label in (("origin", start, "출발지"), ("destination", end, "도착지")):
        p = pts.get(kind)
        if not p:  # 좌표 없이 저장된 지점도 조회 실패와 같이 '확인 못 함'으로 남긴다
            missed.append(label)
            continue
        r = _run("get_weather", lat=p.y, lon=p.x, at=at.strftime("%Y-%m-%dT%H:%M"))
        if r and r["ok"] and r["data"].get("pop") is not None:
            pops.append(r["data"]["pop"])
            got.append(label)
        else:
            missed.append(label)
    if not pops:
        return [_item("weather", "unknown", "그날 예보가 아직 없거나 조회하지 못해 날씨는 확인하지 못했어요")]
    pop = max(pops)
    out = []
    if pop >= RAIN_POP and walk >= WALK_WARN_MIN:
        out.append(_item("weather", "warn", f"강수확률 {pop}% — 도보 {walk}분이라 우산을 챙기거나 택시 구간을 고려하세요"))
    else:
        out.append(_item("weather", "ok", f"강수확률 {pop}%" + (f"({'·'.join(got)} 기준)" if missed else "")))
    if missed:  # 한쪽만 확인했으면 날씨 전체를 확인했다고 하지 않는다
        out.append(_item("weather", "unknown", f"{'·'.join(missed)} 예보는 받지 못해 확인하지 못했어요"))
    return out


def _festival_items(plan, day: dt.date) -> list[dict]:
    dest = next((p for p in plan.points if p.kind == "destination"), None)
    if not dest:
        return []
    r = _run("get_festivals", x=dest.x, y=dest.y, date=day.isoformat())
    if not r or not r["ok"]:
        return []
    return [_item("festival", "warn", f"도착지 {f['distance_km']}km 거리에서 '{f['title']}' 행사 중 — 붐빌 수 있어요")
            for f in r["data"]["festivals"][:2]]


def recheck_plan(plan, *, calendar, now: dt.datetime) -> dict:
    """저장된 계획 하나를 now 기준으로 다시 확인해 {plan_id, status, checked_at, items}를 돌려준다.
    items는 출발 시각·시간표·캘린더·날씨·행사 항목별 {kind, level(ok|warn), text}.
    status: 출발 시각이 지났으면 past, warn 항목이 있으면 warn, 확인 못 한(unknown) 항목이 있으면 partial, 아니면 ok.
    """
    start, end = plan_span(plan)
    items = []
    if now >= start:
        items.append(_item("time", "warn", f"출발 시각 {plan.leave_at}이 이미 지났어요"))
    else:
        left = int((start - now).total_seconds() // 60)
        items.append(_item("time", "ok", f"출발까지 {left // 60}시간 {left % 60}분 남았어요" if left >= 60 else f"출발까지 {left}분 남았어요"))
    items += _train_items(plan, plan.date)
    items += _calendar_items(plan, calendar, start, end)
    items += _weather_items(plan, start, end)
    items += _festival_items(plan, plan.date)
    levels = {i["level"] for i in items}
    status = "past" if now >= start else "warn" if "warn" in levels else "partial" if "unknown" in levels else "ok"
    return {"plan_id": plan.id, "status": status, "checked_at": now.isoformat(timespec="minutes"), "items": items}
