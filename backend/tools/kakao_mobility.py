"""카카오 모빌리티 자동차 길찾기 Tool (F3003 보충: 택시 소요시간·요금, 대중교통 대체)."""
import math

from backend.tools.base import BAD_ARGUMENT, INVALID_KEY, NO_DATA, Tool, fail, ok
from backend.tools.budget import default_budget
from backend.tools.http import fetch_json
from backend.tools.kakao_local import kakao_headers
from backend.tools.registry import register

URL = "https://apis-navi.kakaomobility.com/v1/directions"
TTL = 6 * 3600
MAX_POINTS = 120  # 지도 동선용 도로 좌표는 이 정도로 줄여 담는다


def _road_path(route: dict) -> list[list[float]]:
    """응답의 도로 꼭짓점 [x1, y1, x2, y2, ...]을 이어 [[x, y], ...]로. 너무 많으면 고르게 줄인다(양 끝은 유지)."""
    pts = []
    for sec in route.get("sections") or []:
        for road in sec.get("roads") or []:
            v = road.get("vertexes") or []
            pts += [[round(v[i], 5), round(v[i + 1], 5)] for i in range(0, len(v) - 1, 2)]
    if len(pts) > MAX_POINTS:
        step = (len(pts) - 1) / (MAX_POINTS - 1)
        pts = [pts[round(i * step)] for i in range(MAX_POINTS)]
    return pts


def get_car_route(sx: float, sy: float, ex: float, ey: float) -> dict:
    """두 좌표(경도 x·위도 y) 사이 자동차 경로 요약(택시 대안용).
    data = {duration_min(분 올림), distance_km, taxi_fare, toll, bbox, path(지도용 도로 좌표, 줄여 담음), cached}.
    실패: INVALID_KEY, NO_DATA, 그 밖은 fetch_json·쿼터 코드.
    """
    headers = kakao_headers()
    if headers is None:
        return fail(INVALID_KEY, "KAKAO_REST_KEY가 설정되지 않았습니다.")
    params = {"origin": f"{sx},{sy}", "destination": f"{ex},{ey}"}
    r = default_budget().cached_call("kakao_mobility", {"sx": sx, "sy": sy, "ex": ex, "ey": ey}, TTL,
                                     lambda: fetch_json(URL, params=params, headers=headers))
    if not r["ok"]:
        return r
    routes = (r["data"] or {}).get("routes") or []
    if not routes or routes[0].get("result_code") != 0:
        return fail(NO_DATA, "자동차 경로를 찾지 못했습니다.")
    s = routes[0]["summary"]
    b = s.get("bound") or {}
    return ok({"duration_min": math.ceil(s["duration"] / 60), "distance_km": round(s["distance"] / 1000, 1),
               "taxi_fare": (s.get("fare") or {}).get("taxi"), "toll": (s.get("fare") or {}).get("toll"),
               "bbox": [b.get("min_x"), b.get("min_y"), b.get("max_x"), b.get("max_y")],
               "path": _road_path(routes[0]),
               "cached": r.get("cached", False)}, cached=r.get("cached", False))


MAX_WAYPOINTS = 5  # 카카오 길찾기 경유지 상한
MAX_SHAPE_POINTS = 400


def _thin(pts: list, limit: int) -> list:
    if len(pts) <= limit:
        return pts
    step = (len(pts) - 1) / (limit - 1)
    return [pts[round(i * step)] for i in range(limit)]


def road_shape(points: list[list[float]]) -> dict:
    """버스 정류장 좌표를 차례로 경유하는 도로 좌표(지도 표시용). 정류장 사이를 직선으로 잇는 대신 도로를 따라간다.

    경유지 상한 때문에 7점(출발 + 경유 5 + 도착)씩 나눠 부르고, 앞 조각의 끝을 다음 조각의 시작으로 잇는다.
    한 조각이라도 실패하면 실패(화면은 정류장 직선으로 둔다). 결과는 캐시된다(같은 정류장 열은 다시 부르지 않음).
    """
    if not isinstance(points, list) or len(points) < 2:
        return fail(BAD_ARGUMENT, "좌표가 두 개 이상 필요합니다.")
    headers = kakao_headers()
    if headers is None:
        return fail(INVALID_KEY, "KAKAO_REST_KEY가 설정되지 않았습니다.")
    pts = [[round(float(x), 6), round(float(y), 6)] for x, y in points]
    size = MAX_WAYPOINTS + 1
    path = []
    for i in range(0, len(pts) - 1, size):
        chunk = pts[i:i + size + 1]
        params = {"origin": f"{chunk[0][0]},{chunk[0][1]}", "destination": f"{chunk[-1][0]},{chunk[-1][1]}"}
        if len(chunk) > 2:
            params["waypoints"] = "|".join(f"{x},{y}" for x, y in chunk[1:-1])
        r = default_budget().cached_call("kakao_mobility", {"shape": params}, TTL,
                                         lambda params=params: fetch_json(URL, params=params, headers=headers))
        routes = ((r.get("data") or {}).get("routes") or []) if r["ok"] else []
        if not routes or routes[0].get("result_code") != 0:
            return fail(NO_DATA, "도로 경로를 찾지 못했습니다.")
        piece = []
        for sec in routes[0].get("sections") or []:
            for road in sec.get("roads") or []:
                v = road.get("vertexes") or []
                piece += [[round(v[j], 5), round(v[j + 1], 5)] for j in range(0, len(v) - 1, 2)]
        path += piece[1:] if path and piece and piece[0] == path[-1] else piece
    return ok({"path": _thin(path, MAX_SHAPE_POINTS)})


register(Tool(
    name="get_car_route",
    description="두 지점 사이를 택시나 자동차로 갈 때 시간·택시요금·통행료가 필요하거나, "
                "대중교통 조회가 실패·한도 초과일 때 대체 수단으로 부른다.",
    parameters={"type": "object",
                "properties": {"sx": {"type": "number"}, "sy": {"type": "number"},
                               "ex": {"type": "number"}, "ey": {"type": "number"}},
                "required": ["sx", "sy", "ex", "ey"]},
    func=get_car_route, kind="external"))
