"""캘린더 일정으로 경로 제안: 앞으로 이틀 안의 '장소가 있는' 일정을 골라 장소 좌표를 붙인다.

경로 계산·LLM은 하지 않는다(사용자가 '경로 찾기'를 누르면 그때 질문 만들기 패널로 넘김).
제외: 장소 없는 일정, 이 서비스가 넣은 '이동:' 일정, 이미 시작했거나 30분 안에 시작하는 일정.
"""
from __future__ import annotations

import datetime as dt

from backend.tools.registry import get_tool

DAYS = 2
MIN_AHEAD = dt.timedelta(minutes=30)
MAX_ITEMS = 5


def _place(location: str) -> dict | None:
    tool = get_tool("search_places")
    r = tool.run(query=location[:50]) if tool else None
    if not r or not r["ok"] or not r["data"]["places"]:
        return None
    p = r["data"]["places"][0]
    return {"name": p["name"], "address": p.get("address"), "x": p["x"], "y": p["y"]}


def calendar_suggestions(calendar, now: dt.datetime) -> list[dict]:
    """앞으로 DAYS일 일정 중 경로 제안 후보를 최대 MAX_ITEMS개 고른다.
    항목 = {title, date, arrive_by(일정 시작 HH:MM), location, place}; place는 search_places 첫 결과 좌표, 못 찾으면 None.
    캘린더 조회가 실패하면 빈 목록.
    """
    try:
        events = calendar.upcoming_events(now, days=DAYS)
    except Exception:  # 캘린더 연결 실패면 제안만 없을 뿐 화면은 그대로
        return []
    out = []
    for e in events:
        loc = (e.get("location") or "").strip()
        if not loc or (e.get("title") or "").startswith("이동:") or e["start"] < now + MIN_AHEAD:
            continue
        out.append({"title": e.get("title") or "(제목 없음)", "date": e["start"].date().isoformat(),
                    "arrive_by": e["start"].strftime("%H:%M"), "location": loc, "place": _place(loc)})
        if len(out) >= MAX_ITEMS:
            break
    return out
