from backend.tools.kakao_mobility import get_car_route
from backend.tools.odsay import get_transit_route
from tests.helpers import load, route_get

ODSAY = "api.odsay.com"
MOB = "kakaomobility"


def test_transit_ok(monkeypatch):
    route_get(monkeypatch, [(lambda u, p: ODSAY in u, load("odsay"))])
    r = get_transit_route(126.793, 35.1379, 126.8432, 35.228)
    assert r["ok"]
    paths = r["data"]["paths"]
    assert 1 <= len(paths) <= 3
    assert paths[0]["total_min"] == 44 and paths[0]["fare"] == 1250 and paths[0]["transfers"] == 0
    assert paths == sorted(paths, key=lambda p: p["total_min"])


def test_transit_legs_modes_subset(monkeypatch):
    route_get(monkeypatch, [(lambda u, p: ODSAY in u, load("odsay"))])
    p = get_transit_route(126.793, 35.1379, 126.8432, 35.228)["data"]["paths"][0]
    assert {leg["mode"] for leg in p["legs"]} <= {"walk", "subway", "bus"}
    assert p["walk_min"] == 8  # 도보 subPath sectionTime 1 + 7


def test_transit_no_result(monkeypatch):
    route_get(monkeypatch, [(lambda u, p: ODSAY in u, load("odsay_empty"))])
    assert get_transit_route(125.0, 33.0, 125.1, 33.1)["error"]["code"] == "NO_DATA"


def test_transit_no_key(monkeypatch):
    monkeypatch.setenv("ODSAY_API_KEY", "")
    assert get_transit_route(1, 2, 3, 4)["error"]["code"] == "INVALID_KEY"


def test_transit_key_error_body(monkeypatch):
    route_get(monkeypatch, [(lambda u, p: ODSAY in u, {"error": [{"code": "500", "message": "[ApiKeyAuthFailed]"}]})])
    assert get_transit_route(1, 2, 3, 4)["error"]["code"] == "INVALID_KEY"


def test_car_route_ok(monkeypatch):
    body = load("kakao_mobility")
    body["routes"][0]["summary"]["duration"] = 1830
    route_get(monkeypatch, [(lambda u, p: MOB in u, body)])
    r = get_car_route(126.793, 35.1379, 126.8432, 35.228)["data"]
    assert r["duration_min"] == 31 and r["taxi_fare"] == 17300 and r["toll"] == 0
    assert len(r["bbox"]) == 4


def test_car_route_no_route(monkeypatch):
    route_get(monkeypatch, [(lambda u, p: MOB in u, {"routes": [{"result_code": 104, "result_msg": "no route"}]})])
    assert get_car_route(1, 2, 3, 4)["error"]["code"] == "NO_DATA"


def test_car_route_no_key(monkeypatch):
    monkeypatch.setenv("KAKAO_REST_KEY", "")
    assert get_car_route(1, 2, 3, 4)["error"]["code"] == "INVALID_KEY"
