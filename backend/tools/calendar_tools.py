"""캘린더 로컬 서버 API 툴(F3023): 일정 조회·등록. 등록은 계획 ID만 받고 제목·시각은 저장소에서 읽는다."""
import datetime as dt

from backend.calendar.base import get_calendar
from backend.db.repositories import PlanRepo
from backend.settings import get_settings
from backend.tools.base import BAD_ARGUMENT, CONFLICT, NOT_FOUND, UPSTREAM_ERROR, Tool, fail, ok
from backend.tools.registry import register


def _hm(t: dt.datetime) -> str:
    return t.isoformat(timespec="minutes")


def get_free_busy(date: str, days: int = 1) -> dict:
    """date부터 days(1~3)일간 바쁜 시간대. data = {backend, busy: [{title, start, end(HH:MM)}]}.
    실패: BAD_ARGUMENT(형식·범위), UPSTREAM_ERROR(캘린더 조회 실패).
    """
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
    """저장한 계획을 캘린더에 '이동: 제목' 일정으로 넣고 일정 ID를 계획에 기록한다. data = {event_id, backend}.
    실패: BAD_ARGUMENT, NOT_FOUND(현재 사용자의 계획이 아님), CONFLICT(이미 등록 — 중복 일정 방지), UPSTREAM_ERROR.
    """
    try:
        pid = int(plan_id)
    except (TypeError, ValueError):
        pid = 0
    if pid <= 0:
        return fail(BAD_ARGUMENT, "plan_id는 1 이상의 정수입니다.")
    s = get_settings()
    plan = PlanRepo(s.DB_PATH).get(pid)
    if plan is None:
        return fail(NOT_FOUND, "그런 이동 계획이 없습니다.")
    if plan.calendar_event_id:  # 같은 계획을 여러 번 등록해 중복 일정이 생기지 않게
        return fail(CONFLICT, "이미 캘린더에 등록된 계획입니다.")
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
