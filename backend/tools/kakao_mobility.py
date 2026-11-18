"""카카오 모빌리티 자동차 길찾기 Tool (F3003 보충: 택시 소요시간·요금, 대중교통 대체)."""
import math

from backend.tools.base import INVALID_KEY, NO_DATA, Tool, fail, ok
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
               "cached": r.get("cached", False)})


register(Tool(
    name="get_car_route",
    description="두 지점 사이를 택시나 자동차로 갈 때 시간·택시요금·통행료가 필요하거나, "
                "대중교통 조회가 실패·한도 초과일 때 대체 수단으로 부른다.",
    parameters={"type": "object",
                "properties": {"sx": {"type": "number"}, "sy": {"type": "number"},
                               "ex": {"type": "number"}, "ey": {"type": "number"}},
                "required": ["sx", "sy", "ex", "ey"]},
    func=get_car_route, kind="external"))
