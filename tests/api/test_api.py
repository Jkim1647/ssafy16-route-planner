import pytest
from fastapi.testclient import TestClient

from backend.agent.graph import AnalyzeOut, Changes
from backend.container import Container
from backend.main import create_app
from tests.fakes import FakeLLM

PLAN = {"title": "서울 출장", "date": "2026-11-21", "leave_at": "10:00", "arrive_at": "12:00",
        "origin_name": "첨단동", "destination_name": "강남역"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "app.db"))
    llm = FakeLLM()
    c = Container.build(llm_factory=lambda: llm)
    app = create_app(c)
    tc = TestClient(app, raise_server_exceptions=False, base_url="http://127.0.0.1")  # 허용된 Host로
    tc.llm = llm
    return tc


def test_plan_crud_roundtrip(client):
    r = client.post("/api/plans", json=PLAN)
    assert r.status_code == 201
    pid = r.json()["plan"]["id"]
    assert client.get(f"/api/plans/{pid}").json()["title"] == "서울 출장"
    assert len(client.get("/api/plans").json()) == 1
    r = client.put(f"/api/plans/{pid}", json={"leave_at": "09:00"})
    assert r.status_code == 200 and r.json()["plan"]["leave_at"] == "09:00"
    assert client.delete(f"/api/plans/{pid}").status_code == 204
    assert client.get(f"/api/plans/{pid}").status_code == 404


def test_plan_calendar_register(client, monkeypatch):
    monkeypatch.setenv("CALENDAR_BACKEND", "local")
    pid = client.post("/api/plans", json=PLAN).json()["plan"]["id"]
    r = client.post(f"/api/plans/{pid}/calendar", json={})
    assert r.status_code == 200 and r.json()["event_id"].startswith("local-")
    assert client.get(f"/api/plans/{pid}").json()["calendar_event_id"] == r.json()["event_id"]
    assert client.post("/api/plans/999/calendar", json={}).status_code == 404


def test_plan_overlap_in_response(client):
    client.post("/api/plans", json=PLAN)
    r = client.post("/api/plans", json={**PLAN, "leave_at": "11:00", "arrive_at": "13:00"})
    assert r.status_code == 201 and len(r.json()["overlaps"]) == 1


def test_plan_validation_422(client):
    assert client.post("/api/plans", json={**PLAN, "leave_at": "25:00"}).status_code == 422


def test_chat_returns_events(client):
    client.llm.responses = [AnalyzeOut(intent="chat", intent_reason="인사", changes=Changes())]
    r = client.post("/api/chat", json={"message": "안녕"})
    assert r.status_code == 200
    body = r.json()
    assert body["session_id"] and body["reply"] and body["events"][0]["type"] == "run_start"


def test_logs_list_detail_delete(client):
    client.llm.responses = [AnalyzeOut(intent="chat", intent_reason="인사", changes=Changes())]
    sid = client.post("/api/chat", json={"message": "안녕"}).json()["session_id"]
    lst = client.get("/api/logs").json()
    assert lst[0]["session_id"] == sid and lst[0]["first_message"] == "안녕"
    detail = client.get(f"/api/logs/{sid}").json()
    assert [e["seq"] for e in detail["events"]] == sorted(e["seq"] for e in detail["events"])
    assert client.delete(f"/api/logs/{sid}").status_code == 204
    assert client.get(f"/api/logs/{sid}").status_code == 404


def test_anomaly_judged_after_chat(client):
    client.llm.responses = [AnalyzeOut(intent="chat", intent_reason="인사", changes=Changes())]
    run_id = client.post("/api/chat", json={"message": "안녕"}).json()["run_id"]
    a = client.get(f"/api/runs/{run_id}/anomaly").json()
    assert a["verdict"] == "undetermined" and a["diagnosis"] is None  # 계획·Tool 호출 근거 없음
    assert client.llm.responses == []  # 판정에 LLM을 쓰지 않음


def test_logs_no_put(client):
    assert client.put("/api/logs/abc", json={}).status_code == 405


def test_config_status_booleans_only(client):
    body = client.get("/api/config/status").json()
    assert set(body["keys"].values()) <= {True, False}
    assert "test-key" not in str(body)
    assert body["quota"]["odsay"]["limit"] == 30


def test_tools_catalog(client):
    names = {t["name"] for t in client.get("/api/tools").json()}
    assert {"search_places", "search_trains", "get_transit_route"} <= names


def test_500_hides_detail(client):
    client.llm.responses = [RuntimeError("secret-internal-detail")]
    r = client.post("/api/chat", json={"message": "x"})
    assert "secret-internal-detail" not in r.text


def test_cors_allows_live_server_only(client):
    ok = client.options("/api/plans", headers={"Origin": "http://127.0.0.1:5500",
                                               "Access-Control-Request-Method": "GET"})
    assert ok.headers.get("access-control-allow-origin") == "http://127.0.0.1:5500"
    bad = client.options("/api/plans", headers={"Origin": "http://evil.example",
                                                "Access-Control-Request-Method": "GET"})
    assert bad.headers.get("access-control-allow-origin") is None
