import datetime as dt

import pytest

from backend.db.database import init_db
from backend.db.repositories import AnomalyRepo, EventRepo, PlanRepo, RunRepo
from backend.schemas import PlanIn, PlanUpdate


@pytest.fixture
def db(tmp_path):
    path = str(tmp_path / "app.db")
    init_db(path)
    return path


def plan(leave, arrive, date="2026-11-21", title="서울 출장"):
    return PlanIn(title=title, date=dt.date.fromisoformat(date), leave_at=leave, arrive_at=arrive,
                  origin_name="첨단동", destination_name="강남역")


def test_create_plan_has_created_at(db):
    res = PlanRepo(db).create(plan("10:00", "12:00"))
    assert res.plan.id > 0 and res.plan.created_at is not None and res.overlaps == []


def test_overlap_same_date_reported_but_saved(db):
    repo = PlanRepo(db)
    repo.create(plan("10:00", "12:00"))
    second = repo.create(plan("11:00", "13:00"))
    assert len(second.overlaps) == 1
    assert len(repo.list()) == 2


def test_touching_ranges_not_overlap(db):
    repo = PlanRepo(db)
    repo.create(plan("10:00", "12:00"))
    assert repo.create(plan("12:00", "13:00")).overlaps == []


def test_other_date_not_overlap(db):
    repo = PlanRepo(db)
    repo.create(plan("10:00", "12:00"))
    assert repo.create(plan("10:00", "12:00", date="2026-11-22")).overlaps == []


def test_overnight_plan_overlap(db):
    repo = PlanRepo(db)
    repo.create(plan("23:00", "02:00"))  # 자정 넘김
    assert len(repo.create(plan("23:30", "23:50")).overlaps) == 1


def test_update_rechecks_overlap(db):
    repo = PlanRepo(db)
    repo.create(plan("10:00", "12:00"))
    p2 = repo.create(plan("13:00", "14:00")).plan
    res = repo.update(p2.id, PlanUpdate(leave_at="11:30"))
    assert res.plan.leave_at == "11:30" and len(res.overlaps) == 1


def test_update_missing_returns_none(db):
    assert PlanRepo(db).update(999, PlanUpdate(title="x")) is None


def test_delete_returns_false_when_missing(db):
    repo = PlanRepo(db)
    p = repo.create(plan("10:00", "12:00")).plan
    assert repo.delete(p.id) is True
    assert repo.delete(p.id) is False


def test_plan_bad_time_rejected():
    with pytest.raises(ValueError):
        plan("25:00", "12:00")


def ev(session, run, seq, type_="node_start"):
    return {"session_id": session, "run_id": run, "seq": seq, "ts": f"2026-11-18T10:00:0{seq}",
            "agent": "main", "type": type_, "node": "analyze", "payload": {"k": seq}, "duration_ms": None}


def test_events_ordered_by_seq(db):
    repo = EventRepo(db)
    for s in (2, 1, 3):
        repo.append(ev("s1", "r1", s))
    assert [e["seq"] for e in repo.get_session("s1")] == [1, 2, 3]
    assert repo.get_session("s1")[0]["payload"] == {"k": 1}


def test_sessions_isolated(db):
    repo = EventRepo(db)
    RunRepo(db).start("ra", "A", "a", "single")  # 목록은 소유자가 기록된 실행이 있는 세션만
    RunRepo(db).start("rb", "B", "b", "single")
    repo.append(ev("A", "ra", 1))
    repo.append(ev("B", "rb", 1))
    assert {e["session_id"] for e in repo.get_session("A")} == {"A"}
    assert {s["session_id"] for s in repo.list_sessions()} == {"A", "B"}


def test_delete_session_cascades(db):
    events, runs, anomalies = EventRepo(db), RunRepo(db), AnomalyRepo(db)
    runs.start("r1", "s1", "안녕", "single")
    events.append(ev("s1", "r1", 1))
    anomalies.save("r1", "ok", [])
    assert events.delete_session("s1") is True
    assert events.get_session("s1") == [] and anomalies.get("r1") is None
    assert events.delete_session("s1") is False


def test_event_repo_has_no_update():
    assert not hasattr(EventRepo, "update")


def test_run_repo_finish(db):
    runs = RunRepo(db)
    runs.start("r1", "s1", "msg", "single")
    runs.finish("r1", "done", 1, 2)
    r = runs.get("r1")
    assert r["replan_count"] == 1 and r["llm_calls"] == 2 and r["status"] == "done"


def test_anomaly_diagnosis_separate(db):
    a = AnomalyRepo(db)
    a.save("r1", "warn", [{"rule": "DUPLICATE_CALL"}])
    a.set_diagnosis("r1", "원인")
    got = a.get("r1")
    assert got["verdict"] == "warn" and got["findings"][0]["rule"] == "DUPLICATE_CALL" and got["diagnosis"] == "원인"
