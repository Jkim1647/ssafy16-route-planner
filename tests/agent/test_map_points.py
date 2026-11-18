"""지도 표시용 지점 좌표: 경로 카드와 저장된 계획에 출발지·역·도착지 좌표가 담긴다."""
import datetime as dt
import sqlite3

from backend.db.database import init_db
from backend.db.repositories import PlanRepo
from backend.schemas import PlanIn
from tests.agent.test_graph import DAY, TRIP, A, AnalyzeOut, Changes, Reply, env  # noqa: F401


def kinds(points):
    return [p["kind"] for p in points]


def test_intercity_card_has_route_points(env):
    world, llm, make, _ = env
    llm.responses = [A("plan_trip", **TRIP), Reply(text="ok")]
    card = make()("x").cards[0]
    assert kinds(card["points"]) == ["origin", "dep_station", "arr_station", "destination"]
    o, s = card["points"][0], card["points"][1]
    assert (o["name"], o["x"], o["y"]) == ("첨단동", 126.84, 35.22)
    assert s["name"] == card["basis"]["dep_station"] and isinstance(s["x"], float)


def test_intracity_card_has_origin_and_destination(env):
    world, llm, make, _ = env
    llm.responses = [A("plan_trip", origin="첨단동", destination="광주송정역", date=DAY, arrive_by="14:00"),
                     Reply(text="ok")]
    card = make()("x").cards[0]
    assert kinds(card["points"]) == ["origin", "destination"]


def test_saved_plan_keeps_points(env):
    world, llm, make, db = env
    turn = make()
    llm.responses = [A("plan_trip", **TRIP), Reply(text="ok")]
    turn("x")
    llm.responses = [AnalyzeOut(intent="save_plan", intent_reason="저장", changes=Changes(), option_ref=1)]
    turn("1번 저장")
    [plan] = PlanRepo(db).list()
    assert kinds(plan.points) == ["origin", "dep_station", "arr_station", "destination"]


def test_plan_points_roundtrip(tmp_path):
    db = str(tmp_path / "a.db")
    init_db(db)
    pts = [{"kind": "origin", "name": "a", "x": 126.8, "y": 35.2}, {"kind": "destination", "name": "b", "x": 127.0, "y": 37.5}]
    res = PlanRepo(db).create(PlanIn(title="a → b", date=dt.date(2026, 11, 21), leave_at="09:00", arrive_at="10:00",
                                     origin_name="a", destination_name="b", points=pts))
    assert PlanRepo(db).get(res.plan.id).points == pts


def test_old_database_gets_points_column(tmp_path):
    db = str(tmp_path / "old.db")
    with sqlite3.connect(db) as c:  # 지점 칸이 없던 1일차 스키마
        c.execute("CREATE TABLE plans(id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, date TEXT NOT NULL, "
                  "leave_at TEXT NOT NULL, arrive_at TEXT NOT NULL, origin_name TEXT NOT NULL, "
                  "destination_name TEXT NOT NULL, legs_json TEXT NOT NULL DEFAULT '[]', total_fare INTEGER, "
                  "source_run_id TEXT, calendar_event_id TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)")
        c.execute("INSERT INTO plans(title,date,leave_at,arrive_at,origin_name,destination_name,created_at,updated_at) "
                  "VALUES('옛 계획','2026-11-21','09:00','10:00','a','b','2026-11-18T10:00:00','2026-11-18T10:00:00')")
    init_db(db)
    repo = PlanRepo(db)
    assert repo.list()[0].points == []
    repo.create(PlanIn(title="새 계획", date=dt.date(2026, 11, 21), leave_at="11:00", arrive_at="12:00",
                       origin_name="a", destination_name="b", points=[{"kind": "origin", "name": "a", "x": 1.0, "y": 2.0}]))
    assert len(repo.list()) == 2
