"""도보 구간 지도 표시: OpenStreetMap 보행 경로(FOSSGIS OSRM)로 실제 길을 따라 그린다. 직선 점선 대신."""
import pytest

from backend.tools import osm_walk
from backend.tools.osm_walk import walk_shape
from tests.api.test_auth import make_client  # noqa: F401
from tests.helpers import route_get

OSRM = "routing.openstreetmap.de"


@pytest.fixture(autouse=True)
def no_wait(monkeypatch):
    """호출 간격(초당 1회) 대기는 실제로 하지 않는다."""
    monkeypatch.setattr(osm_walk.time, "sleep", lambda s: None)


A, B = [126.8466, 35.2186], [126.8480, 35.2170]


def osrm_ok(calls):
    def body(url, params):
        calls.append((url, params))
        return {"code": "Ok", "routes": [{"distance": 240, "duration": 180, "geometry": {
            "coordinates": [A, [126.8470, 35.2185], [126.8478, 35.2176], B]}}]}
    return body


def test_walk_shape_follows_streets(monkeypatch):
    calls = []
    route_get(monkeypatch, [(lambda u, p: OSRM in u, osrm_ok(calls))])
    r = walk_shape(A, B)
    assert r["ok"] and r["data"]["path"] == [A, [126.847, 35.2185], [126.8478, 35.2176], B]
    url, params = calls[0]
    assert "/routed-foot/route/v1/foot/126.8466,35.2186;126.848,35.217" in url
    assert params["geometries"] == "geojson" and params["overview"] == "full"


def test_walk_shape_cached(monkeypatch):
    calls = []
    route_get(monkeypatch, [(lambda u, p: OSRM in u, osrm_ok(calls))])
    walk_shape(A, B)
    assert walk_shape(A, B)["ok"] and len(calls) == 1  # 같은 구간은 다시 부르지 않는다(이용 조건: 과다 사용 금지)


def test_walk_shape_sends_identifying_user_agent(monkeypatch):
    seen = {}
    import requests

    def fake(url, params=None, headers=None, timeout=None):
        seen.update(headers or {})
        raise requests.ConnectionError()
    monkeypatch.setattr(requests, "get", fake)
    assert walk_shape(A, B)["error"]["code"] == "UPSTREAM_ERROR"
    assert "RoutePlanner" in seen.get("User-Agent", "")  # 이용 조건: 올바른 User-Agent


def test_walk_shape_rejects_long_or_bad(monkeypatch):
    assert walk_shape(A, [127.5, 36.0])["error"]["code"] == "BAD_ARGUMENT"  # 도보 구간으로 너무 멂
    assert walk_shape([1, 2], B)["error"]["code"] == "BAD_ARGUMENT"


def test_walk_shape_can_be_turned_off(monkeypatch):
    monkeypatch.setenv("WALK_ROUTE_ENABLED", "false")
    assert walk_shape(A, B)["error"]["code"] == "DISABLED"


def test_walk_shape_no_route(monkeypatch):
    route_get(monkeypatch, [(lambda u, p: OSRM in u, {"code": "NoRoute", "routes": []})])
    assert walk_shape(A, B)["error"]["code"] == "NO_DATA"


def test_rate_limit_waits_between_calls(monkeypatch):
    slept = []
    clock = iter([100.0, 100.0, 100.2, 101.0])  # 호출마다 간격 확인·기록에 한 번씩
    monkeypatch.setattr(osm_walk.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(osm_walk.time, "sleep", slept.append)
    monkeypatch.setattr(osm_walk, "_last_call", 0.0)
    osm_walk._wait_turn()   # 100.0: 첫 호출
    osm_walk._wait_turn()   # 100.2: 0.8초 기다림(초당 1회)
    assert slept and abs(slept[0] - 0.8) < 1e-6


def test_walk_shape_api(make_client, monkeypatch):
    calls = []
    route_get(monkeypatch, [(lambda u, p: OSRM in u, osrm_ok(calls))])
    c = make_client(required=False)
    r = c.post("/api/map/walk-shape", json={"points": [A, B]})
    assert r.status_code == 200 and len(r.json()["path"]) == 4
    assert c.post("/api/map/walk-shape", json={"points": [A, B, A]}).status_code == 422
