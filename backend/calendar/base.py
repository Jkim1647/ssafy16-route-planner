"""캘린더 구현체 인터페이스(F3023). 로컬 저장소 구현을 먼저 쓰고 Google Calendar로 교체한다."""
from __future__ import annotations

import datetime as dt
from typing import Protocol

from backend.agent.judge import Busy


class CalendarBackend(Protocol):
    name: str

    def get_free_busy(self, day: dt.date) -> list[Busy]: ...

    def create_event(self, plan) -> str: ...


def plan_span(plan) -> tuple[dt.datetime, dt.datetime]:
    """계획의 [출발, 도착). 도착이 출발보다 이르면 다음 날 도착."""
    start = dt.datetime.combine(plan.date, dt.time.fromisoformat(plan.leave_at))
    end = dt.datetime.combine(plan.date, dt.time.fromisoformat(plan.arrive_at))
    return start, end if end > start else end + dt.timedelta(days=1)


def _may_use_google(settings) -> bool:
    """실제 Google 캘린더(서버의 token.json 한 계정)는 그 소유자만. 로그인을 끈 모드의 local 사용자는 소유자로 본다."""
    from backend.auth.context import current_email, current_user_id
    if current_user_id() == "local":
        return True
    owner = (settings.CALENDAR_OWNER_EMAIL or "").strip().lower()
    return bool(owner) and (current_email() or "").lower() == owner


def get_calendar(settings) -> CalendarBackend:
    if settings.CALENDAR_BACKEND == "google" and _may_use_google(settings):
        from backend.calendar.google import GoogleCalendar
        return GoogleCalendar(settings.GOOGLE_CALENDAR_ID)
    from backend.calendar.local import LocalCalendar
    return LocalCalendar(settings.DB_PATH)
