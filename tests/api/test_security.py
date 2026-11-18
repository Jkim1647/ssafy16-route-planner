"""보안 점검에서 나온 문제 재현: Host 검사(DNS rebinding), 캘린더 등록 CSRF·중복, 계획 입력 크기 상한."""
from tests.api.test_api import PLAN, client  # noqa: F401
from backend.tools.calendar_tools import register_calendar


# 1. 이 컴퓨터 주소가 아닌 Host로 온 요청은 거절(악성 도메인을 127.0.0.1로 바꿔치기하는 공격 차단)
def test_rejects_foreign_host_header(client):
    assert client.get("/api/plans", headers={"host": "evil.example.com"}).status_code == 400
    assert client.get("/api/plans", headers={"host": "127.0.0.1:8000"}).status_code == 200
    assert client.get("/api/plans", headers={"host": "localhost:8000"}).status_code == 200


# 2. 캘린더 등록은 JSON 요청만(다른 사이트의 폼 전송 차단), 이미 등록된 계획은 다시 등록하지 않음
def test_calendar_register_rejects_form_post(client, monkeypatch):
    monkeypatch.setenv("CALENDAR_BACKEND", "local")
    pid = client.post("/api/plans", json=PLAN).json()["plan"]["id"]
    r = client.post(f"/api/plans/{pid}/calendar", data={"x": "1"})
    assert r.status_code == 415
    assert client.get(f"/api/plans/{pid}").json()["calendar_event_id"] is None


def test_calendar_register_twice_is_conflict(client, monkeypatch):
    monkeypatch.setenv("CALENDAR_BACKEND", "local")
    pid = client.post("/api/plans", json=PLAN).json()["plan"]["id"]
    assert client.post(f"/api/plans/{pid}/calendar", json={}).status_code == 200
    assert client.post(f"/api/plans/{pid}/calendar", json={}).status_code == 409


def test_register_tool_refuses_already_registered(client, monkeypatch):
    monkeypatch.setenv("CALENDAR_BACKEND", "local")
    pid = client.post("/api/plans", json=PLAN).json()["plan"]["id"]
    assert register_calendar(pid)["ok"]
    assert register_calendar(pid)["error"]["code"] == "CONFLICT"


# 3. 계획 입력 크기 상한
def test_plan_rejects_oversized_input(client):
    leg = {"mode": "bus", "name": "1002", "minutes": 29, "fare": None, "source": "odsay", "path": [[126.8, 35.2]] * 2}
    assert client.post("/api/plans", json={**PLAN, "origin_name": "가" * 101}).status_code == 422
    assert client.post("/api/plans", json={**PLAN, "legs": [leg] * 31}).status_code == 422
    assert client.post("/api/plans", json={**PLAN, "legs": [{**leg, "path": [[1.0, 2.0]] * 401}]}).status_code == 422
    assert client.post("/api/plans", json={**PLAN, "points": [{"kind": "origin", "name": "a", "x": 1.0, "y": 2.0}] * 11}).status_code == 422
    assert client.post("/api/plans", json={**PLAN, "total_fare": -1}).status_code == 422


def test_plan_accepts_real_card_shape(client):
    leg = {"mode": "subway", "name": "수도권 2호선", "minutes": 3, "fare": None, "source": "odsay",
           "path": [[127.0, 37.5], [127.01, 37.49]], "line_code": 2}
    pts = [{"kind": "origin", "name": "a", "x": 126.8, "y": 35.2}, {"kind": "destination", "name": "b", "x": 127.0, "y": 37.5}]
    r = client.post("/api/plans", json={**PLAN, "legs": [leg], "points": pts, "total_fare": 43700})
    assert r.status_code == 201
    assert r.json()["plan"]["legs"][0]["path"] == [[127.0, 37.5], [127.01, 37.49]]
