"""계획·실행 로그·이상 판정 저장소. 실행 로그는 append/조회/삭제만 있다(수정 없음, F3014)."""
from __future__ import annotations

import datetime as dt
import json

from backend.db.database import connect
from backend.schemas import PlanIn, PlanOut, PlanSaveResult, PlanUpdate


def _now() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


def _minutes(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def _span(leave: str, arrive: str) -> tuple[int, int]:
    """[출발, 도착) 분 단위. 도착이 출발보다 이르면 자정을 넘긴 것으로 본다."""
    s, e = _minutes(leave), _minutes(arrive)
    return s, e + 1440 if e <= s else e


class PlanRepo:
    def __init__(self, db_path: str):
        self.db = db_path

    def _row(self, r) -> PlanOut:
        d = dict(r)
        d["legs"] = json.loads(d.pop("legs_json") or "[]")
        d["points"] = json.loads(d.pop("points_json", None) or "[]")
        return PlanOut(**d)

    def get(self, plan_id: int) -> PlanOut | None:
        with connect(self.db) as c:
            r = c.execute("SELECT * FROM plans WHERE id=?", (plan_id,)).fetchone()
        return self._row(r) if r else None

    def list(self) -> list[PlanOut]:
        with connect(self.db) as c:
            rows = c.execute("SELECT * FROM plans ORDER BY date, leave_at, id").fetchall()
        return [self._row(r) for r in rows]

    def find_overlaps(self, date: dt.date, leave_at: str, arrive_at: str, exclude_id: int | None = None) -> list[PlanOut]:
        s, e = _span(leave_at, arrive_at)
        # 자정을 넘기는 계획이 있어 전날·다음 날 계획도 날짜 차이(분)를 반영해 비교한다
        days = [(date + dt.timedelta(days=k)).isoformat() for k in (-1, 0, 1)]
        with connect(self.db) as c:
            rows = c.execute("SELECT * FROM plans WHERE date IN (?,?,?) AND id IS NOT ?", (*days, exclude_id)).fetchall()
        out = []
        for r in rows:
            shift = (dt.date.fromisoformat(r["date"]) - date).days * 1440
            s2, e2 = (v + shift for v in _span(r["leave_at"], r["arrive_at"]))
            if s < e2 and s2 < e:
                out.append(self._row(r))
        return out

    def create(self, p: PlanIn) -> PlanSaveResult:
        overlaps = self.find_overlaps(p.date, p.leave_at, p.arrive_at)
        now = _now()
        with connect(self.db) as c:
            cur = c.execute(
                "INSERT INTO plans(title,date,leave_at,arrive_at,origin_name,destination_name,legs_json,total_fare,"
                "source_run_id,created_at,updated_at,points_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (p.title, p.date.isoformat(), p.leave_at, p.arrive_at, p.origin_name, p.destination_name,
                 json.dumps(p.legs, ensure_ascii=False), p.total_fare, p.source_run_id, now, now,
                 json.dumps(p.points, ensure_ascii=False)))
            new_id = cur.lastrowid
        return PlanSaveResult(plan=self.get(new_id), overlaps=overlaps)

    def update(self, plan_id: int, u: PlanUpdate) -> PlanSaveResult | None:
        cur = self.get(plan_id)
        if cur is None:
            return None
        changes = u.model_dump(exclude_none=True)
        merged = cur.model_copy(update=changes)
        PlanIn.model_validate(merged.model_dump())  # 합친 결과도 규격 검사
        if changes:
            cols = ", ".join(f"{k}=?" for k in changes)
            vals = [v.isoformat() if isinstance(v, dt.date) else v for v in changes.values()]
            with connect(self.db) as c:
                c.execute(f"UPDATE plans SET {cols}, updated_at=? WHERE id=?", (*vals, _now(), plan_id))
        updated = self.get(plan_id)
        return PlanSaveResult(plan=updated, overlaps=self.find_overlaps(updated.date, updated.leave_at,
                                                                          updated.arrive_at, exclude_id=plan_id))

    def delete(self, plan_id: int) -> bool:
        with connect(self.db) as c:
            return c.execute("DELETE FROM plans WHERE id=?", (plan_id,)).rowcount > 0

    def set_calendar_event(self, plan_id: int, event_id: str) -> None:
        with connect(self.db) as c:
            c.execute("UPDATE plans SET calendar_event_id=? WHERE id=?", (event_id, plan_id))


class EventRepo:
    def __init__(self, db_path: str):
        self.db = db_path

    def append(self, e: dict) -> None:
        with connect(self.db) as c:
            c.execute("INSERT INTO run_events(session_id,run_id,seq,ts,agent,type,node,payload_json,duration_ms) "
                      "VALUES(?,?,?,?,?,?,?,?,?)",
                      (e["session_id"], e["run_id"], e["seq"], e["ts"], e.get("agent"), e["type"], e.get("node"),
                       json.dumps(e.get("payload") or {}, ensure_ascii=False, default=str), e.get("duration_ms")))

    @staticmethod
    def _ev(r) -> dict:
        d = dict(r)
        d["payload"] = json.loads(d.pop("payload_json") or "{}")
        d.pop("id", None)
        return d

    def get_session(self, session_id: str) -> list[dict]:
        with connect(self.db) as c:
            rows = c.execute("SELECT * FROM run_events WHERE session_id=? ORDER BY id", (session_id,)).fetchall()
        evs = [self._ev(r) for r in rows]
        order = {}
        for e in evs:
            order.setdefault(e["run_id"], len(order))
        return sorted(evs, key=lambda e: (order[e["run_id"]], e["seq"]))

    def get_run(self, run_id: str) -> list[dict]:
        with connect(self.db) as c:
            rows = c.execute("SELECT * FROM run_events WHERE run_id=? ORDER BY seq", (run_id,)).fetchall()
        return [self._ev(r) for r in rows]

    def list_sessions(self) -> list[dict]:
        with connect(self.db) as c:
            rows = c.execute(
                "SELECT e.session_id, COUNT(DISTINCT e.run_id) AS run_count, MAX(e.ts) AS last_ts, "
                "(SELECT COUNT(*) FROM anomaly_reports a JOIN runs r ON r.run_id=a.run_id "
                " WHERE r.session_id=e.session_id AND a.verdict='warn') AS warn_count, "
                "(SELECT user_message FROM runs r WHERE r.session_id=e.session_id ORDER BY started_at LIMIT 1) AS first_message "
                "FROM run_events e GROUP BY e.session_id ORDER BY last_ts DESC").fetchall()
        return [dict(r) for r in rows]

    def delete_session(self, session_id: str) -> bool:
        with connect(self.db) as c:
            run_ids = [r[0] for r in c.execute(
                "SELECT DISTINCT run_id FROM run_events WHERE session_id=? UNION SELECT run_id FROM runs WHERE session_id=?",
                (session_id, session_id))]
            n = c.execute("DELETE FROM run_events WHERE session_id=?", (session_id,)).rowcount
            c.execute("DELETE FROM runs WHERE session_id=?", (session_id,))
            c.executemany("DELETE FROM anomaly_reports WHERE run_id=?", [(r,) for r in run_ids])
        return n > 0


class RunRepo:
    def __init__(self, db_path: str):
        self.db = db_path

    def start(self, run_id: str, session_id: str, user_message: str, mode: str) -> None:
        with connect(self.db) as c:
            c.execute("INSERT OR REPLACE INTO runs(run_id,session_id,user_message,mode,status,started_at) "
                      "VALUES(?,?,?,?,'running',?)", (run_id, session_id, user_message, mode, _now()))

    def finish(self, run_id: str, status: str, replan_count: int, llm_calls: int) -> None:
        with connect(self.db) as c:
            c.execute("UPDATE runs SET status=?, replan_count=?, llm_calls=?, ended_at=? WHERE run_id=?",
                      (status, replan_count, llm_calls, _now(), run_id))

    def get(self, run_id: str) -> dict | None:
        with connect(self.db) as c:
            r = c.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
        return dict(r) if r else None


class AnomalyRepo:
    def __init__(self, db_path: str):
        self.db = db_path

    def save(self, run_id: str, verdict: str, findings: list, diagnosis: str | None = None) -> None:
        with connect(self.db) as c:
            c.execute("INSERT OR REPLACE INTO anomaly_reports VALUES(?,?,?,?,?)",
                      (run_id, verdict, json.dumps(findings, ensure_ascii=False), diagnosis, _now()))

    def set_diagnosis(self, run_id: str, text: str) -> None:
        with connect(self.db) as c:
            c.execute("UPDATE anomaly_reports SET diagnosis=? WHERE run_id=?", (text, run_id))

    def get(self, run_id: str) -> dict | None:
        with connect(self.db) as c:
            r = c.execute("SELECT * FROM anomaly_reports WHERE run_id=?", (run_id,)).fetchone()
        if not r:
            return None
        d = dict(r)
        d["findings"] = json.loads(d.pop("findings_json"))
        return d
