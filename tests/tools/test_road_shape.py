"""지도 동선: 버스 정류장 좌표를 카카오 길찾기 경유지로 넣어 도로를 따라가는 선으로 바꾼다(정류장 사이 대각선 대신)."""
from backend.tools.kakao_mobility import road_shape
from tests.api.test_auth import make_client  # noqa: F401
from tests.helpers import route_get

KAKAO = "kakaomobility"


def fake_directions(calls):
    def body(url, params):
        calls.append(params)
        ox, oy = map(float, params["origin"].split(","))
        dx, dy = map(float, params["destination"].split(","))
        return {"routes": [{"result_code": 0, "summary": {"duration": 60, "distance": 100},
                            "sections": [{"roads": [{"vertexes": [ox, oy, (ox + dx) / 2, oy, dx, dy]}]}]}]}
    return body


def stops(n):
    return [[126.80 + i * 0.002, 35.19 + i * 0.001] for i in range(n)]


def test_road_shape_chunks_waypoints_and_joins(monkeypatch):
    calls = []
    route_get(monkeypatch, [(lambda u, p: KAKAO in u, fake_directions(calls))])
    pts = stops(12)
    r = road_shape(pts)
    assert r["ok"]
    path = r["data"]["path"]
    assert len(calls) == 2  # 출발 + 경유 5 + 도착 = 7점씩, 앞 조각의 끝이 다음 조각의 시작
    assert all(len(c.get("waypoints", "").split("|")) <= 5 for c in calls)
    assert calls[1]["origin"] == calls[0]["destination"]
    assert path[0] == [round(pts[0][0], 5), round(pts[0][1], 5)] and path[-1] == [round(pts[-1][0], 5), round(pts[-1][1], 5)]
    assert [round(pts[6][0] / 2 + pts[0][0] / 2, 5), pts[0][1]] in path  # 도로 꼭짓점(가운데 점)이 들어 있다


def test_road_shape_two_points_no_waypoints(monkeypatch):
    calls = []
    route_get(monkeypatch, [(lambda u, p: KAKAO in u, fake_directions(calls))])
    assert road_shape(stops(2))["ok"] and "waypoints" not in calls[0]


def test_road_shape_fails_when_a_piece_fails(monkeypatch):
    route_get(monkeypatch, [(lambda u, p: KAKAO in u, {"routes": [{"result_code": 104}]})])
    assert road_shape(stops(3))["error"]["code"] == "NO_DATA"


def test_road_shape_bad_points():
    assert road_shape([[126.8, 35.1]])["error"]["code"] == "BAD_ARGUMENT"


def test_road_shape_api(make_client, monkeypatch):
    calls = []
    route_get(monkeypatch, [(lambda u, p: KAKAO in u, fake_directions(calls))])
    c = make_client(required=False)
    r = c.post("/api/map/road-shape", json={"points": stops(4)})
    assert r.status_code == 200 and len(r.json()["path"]) == 3  # 한 조각: 출발·가운데·도착
    assert c.post("/api/map/road-shape", json={"points": stops(81)}).status_code == 422  # 너무 많은 점
    assert c.post("/api/map/road-shape", json={"points": [[0, 0], [1, 1]]}).status_code == 422  # 국내 좌표만
