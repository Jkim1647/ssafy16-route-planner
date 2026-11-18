"""캘린더 로컬 서버 API 툴(F3023): 일정 조회·등록. 등록은 계획 ID만 받고 제목·시각은 저장소에서 읽는다."""
import datetime as dt

from backend.calendar.base import get_calendar
from backend.db.repositories import PlanRepo
from backend.settings import get_settings
from backend.tools.base import BAD_ARGUMENT, NOT_FOUND, UPSTREAM_ERROR, Tool, fail, ok
from backend.tools.registry import register


def _hm(t: dt.datetime) -> str:
    return t.isoformat(timespec="minutes")


def get_free_busy(date: str, days: int = 1) -> dict:
    try:
        day = dt.date.fromisoformat(date)
    except (TypeError, ValueError):
        return fail(BAD_ARGUMENT, "date는 YYYY-MM-DD 형식이어야 합니다.")
    if not isinstance(days, int) or not 1 <= days <= 3:
        return fail(BAD_ARGUMENT, "days는 1~3 사이 정수입니다.")
    cal = get_calendar(get_settings())
    try:
        busy = cal.get_free_busy(day, days)
    except Exception:
        return fail(UPSTREAM_ERROR, "캘린더를 조회하지 못했습니다.")
    return ok({"backend": cal.name, "busy": [{"title": b.title, "start": _hm(b.start), "end": _hm(b.end)} for b in busy]})


def register_calendar(plan_id: int) -> dict:
    s = get_settings()
    plan = PlanRepo(s.DB_PATH).get(int(plan_id))
    if plan is None:
        return fail(NOT_FOUND, "그런 이동 계획이 없습니다.")
    cal = get_calendar(s)
    try:
        event_id = cal.create_event(plan)
    except Exception:
        return fail(UPSTREAM_ERROR, "캘린더에 등록하지 못했습니다.")
    PlanRepo(s.DB_PATH).set_calendar_event(plan.id, event_id)
    return ok({"event_id": event_id, "backend": cal.name})


register(Tool(
    name="get_free_busy",
    description="이동하는 날짜에 사용자의 기존 일정(바쁜 시간대)을 확인해, 이동 시간과 겹치는 경로를 걸러낼 때 부른다.",
    parameters={"type": "object", "properties": {"date": {"type": "string", "description": "YYYY-MM-DD"},
                                                 "days": {"type": "integer", "description": "조회 일수 1~3(자정 넘김·전날 출발)"}},
                "required": ["date"]},
    func=get_free_busy, kind="local"))
register(Tool(
    name="register_calendar",
    description="사용자가 저장한 이동 계획을 캘린더에 넣어 달라고 할 때 부른다. 계획 ID만 넘기면 제목·시각은 서버가 저장소에서 읽는다.",
    parameters={"type": "object", "properties": {"plan_id": {"type": "integer"}}, "required": ["plan_id"]},
    func=register_calendar, kind="local"))
