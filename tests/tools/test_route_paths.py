"""지도 동선 좌표: 버스·지하철은 지나는 정류장 좌표, 택시는 도로 좌표를 구간에 담는다."""
from backend.tools.kakao_mobility import get_car_route
from backend.tools.odsay import get_transit_route
from tests.helpers import load, route_get
from tests.agent.test_graph import DAY, TRIP, A, Reply, env  # noqa: F401
from backend.tools.base import ok


def test_transit_legs_carry_stop_coordinates(monkeypatch):
    route_get(monkeypatch, [(lambda u, p: "odsay" in u, load("odsay"))])
    legs = get_transit_route(126.79, 35.13, 126.84, 35.23)["data"]["paths"][0]["legs"]
    bus = next(lg for lg in legs if lg["mode"] == "bus")
    assert len(bus["path"]) == 19 and bus["path"][0] == [126.792176, 35.13827]
    assert all(lg["path"] is None for lg in legs if lg["mode"] == "walk")


def test_car_route_carries_road_coordinates(monkeypatch):
    route_get(monkeypatch, [(lambda u, p: "kakaomobility" in u, load("kakao_mobility"))])
    path = get_car_route(126.79, 35.13, 126.84, 35.23)["data"]["path"]
    assert 2 <= len(path) <= 120
    assert path[0] == [126.79306, 35.13794]


def test_card_legs_keep_paths(env):
    world, llm, make, _ = env
    world.transit = ok({"paths": [{"total_min": 30, "fare": 1500, "transfers": 0, "walk_min": 5, "legs": [
        {"mode": "walk", "name": None, "min": 5, "path": None},
        {"mode": "bus", "name": "1002", "min": 25, "path": [[126.80, 35.20], [126.81, 35.19]]}]}]})
    llm.responses = [A("plan_trip", **TRIP), Reply(text="ok")]
    card = make()("x").cards[0]
    bus = next(lg for lg in card["legs"] if lg["mode"] == "bus")
    assert bus["path"] == [[126.8, 35.2], [126.81, 35.19]]
