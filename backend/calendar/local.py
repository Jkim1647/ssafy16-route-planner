"""로컬 SQLite 캘린더 구현체(Google 연동 전 동작 확인용)."""
from __future__ import annotations

import datetime as dt

from backend.agent.judge import Busy
from backend.calendar.base import plan_span
from backend.db.database import connect


class LocalCalendar:
    name = "local"

    def __init__(self, db_path: str):
        self.db = db_path

    def add(self, title: str, start: dt.datetime, end: dt.datetime, plan_id: int | None = None) -> str:
        with connect(self.db) as c:
            cur = c.execute('INSERT INTO local_calendar(title, start, "end", plan_id) VALUES(?,?,?,?)',
                            (title, start.isoformat(timespec="minutes"), end.isoformat(timespec="minutes"), plan_id))
            return f"local-{cur.lastrowid}"

    def get_free_busy(self, day: dt.date, days: int = 1) -> list[Busy]:
        lo = dt.datetime.combine(day, dt.time.min).isoformat(timespec="minutes")
        hi = dt.datetime.combine(day + dt.timedelta(days=days), dt.time.min).isoformat(timespec="minutes")
        with connect(self.db) as c:
            rows = c.execute('SELECT title, start, "end" FROM local_calendar WHERE start < ? AND "end" > ? ORDER BY start',
                             (hi, lo)).fetchall()
        return [Busy(r["title"], dt.datetime.fromisoformat(r["start"]), dt.datetime.fromisoformat(r["end"])) for r in rows]

    def create_event(self, plan) -> str:
        start, end = plan_span(plan)
        return self.add(f"이동: {plan.title}", start, end, plan.id)
