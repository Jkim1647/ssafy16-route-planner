"""로컬 SQLite 캘린더 구현체(Google 연동 전 동작 확인용)."""
from __future__ import annotations

import datetime as dt

from backend.agent.judge import Busy
from backend.auth.context import current_user_id
from backend.calendar.base import plan_span
from backend.db.database import connect


class LocalCalendar:
    name = "local"

    def __init__(self, db_path: str):
        self.db = db_path

    def add(self, title: str, start: dt.datetime, end: dt.datetime, plan_id: int | None = None) -> str:
        with connect(self.db) as c:
            cur = c.execute('INSERT INTO local_calendar(title, start, "end", plan_id, user_id) VALUES(?,?,?,?,?)',
                            (title, start.isoformat(timespec="minutes"), end.isoformat(timespec="minutes"), plan_id,
                             current_user_id()))
            return f"local-{cur.lastrowid}"

    def get_free_busy(self, day: dt.date, days: int = 1) -> list[Busy]:
        lo = dt.datetime.combine(day, dt.time.min).isoformat(timespec="minutes")
        hi = dt.datetime.combine(day + dt.timedelta(days=days), dt.time.min).isoformat(timespec="minutes")
        with connect(self.db) as c:
            rows = c.execute('SELECT title, start, "end" FROM local_calendar WHERE start < ? AND "end" > ? AND user_id=? '
                             'ORDER BY start', (hi, lo, current_user_id())).fetchall()
        return [Busy(r["title"], dt.datetime.fromisoformat(r["start"]), dt.datetime.fromisoformat(r["end"])) for r in rows]

    def upcoming_events(self, start: dt.datetime, days: int = 2) -> list[dict]:
        """로컬 캘린더에는 장소가 없다(이 서비스가 넣은 이동 일정뿐) → 경로 제안 대상 없음."""
        return [{"title": b.title, "start": b.start, "end": b.end, "location": None}
                for b in self.get_free_busy(start.date(), days=days + 1) if b.start >= start]

    def create_event(self, plan) -> str:
        start, end = plan_span(plan)
        return self.add(f"이동: {plan.title}", start, end, plan.id)
