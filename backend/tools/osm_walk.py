"""도보 구간 지도 표시용 보행 경로(OpenStreetMap, FOSSGIS OSRM). 판단·계산에는 쓰지 않고 그림에만 쓴다.

이용 조건(routing.openstreetmap.de): 초당 1회 이하, 과다 사용 금지, 올바른 User-Agent, 출처 표시.
→ 서버에서만 부르고(브라우저 IP·쿠키가 나가지 않음), 결과는 7일 캐시, 호출 사이 1초 간격.
요청 좌표는 그 서버 로그에 남는다. 끄려면 WALK_ROUTE_ENABLED=false(화면은 직선 점선으로 돌아감).
"""
import os
import threading
import time

from backend.tools.base import BAD_ARGUMENT, NO_DATA, fail, ok
from backend.tools.budget import default_budget
from backend.tools.http import fetch_json
from backend.tools.stations import haversine_km

URL = "https://routing.openstreetmap.de/routed-foot/route/v1/foot/{sx},{sy};{ex},{ey}"
HEADERS = {"User-Agent": "RoutePlanner/1.0 (SSAFY AI course project; walking legs map display)"}
TTL = 7 * 24 * 3600
MAX_KM = 5        # 도보 구간으로 보기에 너무 먼 요청은 보내지 않는다
MAX_POINTS = 200
DISABLED = "DISABLED"

_lock = threading.Lock()
_last_call = 0.0


def _wait_turn() -> None:
    """초당 1회 이하로 부르게 앞 호출과 1초 간격을 둔다."""
    global _last_call
    with _lock:
        gap = time.monotonic() - _last_call
        if _last_call and gap < 1.0:
            time.sleep(1.0 - gap)
        _last_call = time.monotonic()


def _enabled() -> bool:
    return os.getenv("WALK_ROUTE_ENABLED", "true").strip().lower() not in {"0", "false", "off", "no"}


def walk_shape(a: list[float], b: list[float]) -> dict:
    if not _enabled():
        return fail(DISABLED, "도보 경로 표시가 꺼져 있습니다.")
    try:
        (sx, sy), (ex, ey) = [(round(float(p[0]), 6), round(float(p[1]), 6)) for p in (a, b)]
    except (TypeError, ValueError, IndexError):
        return fail(BAD_ARGUMENT, "좌표는 [경도, 위도] 두 개여야 합니다.")
    if not all(124 <= x <= 132 and 33 <= y <= 39 for x, y in ((sx, sy), (ex, ey))):
        return fail(BAD_ARGUMENT, "국내 좌표만 받을 수 있습니다.")
    if haversine_km(sx, sy, ex, ey) > MAX_KM:
        return fail(BAD_ARGUMENT, "도보 구간으로 보기에 너무 멉니다.")

    def call():
        _wait_turn()
        return fetch_json(URL.format(sx=sx, sy=sy, ex=ex, ey=ey),
                          params={"overview": "full", "geometries": "geojson"}, headers=HEADERS)
    r = default_budget().cached_call("osm_walk", {"sx": sx, "sy": sy, "ex": ex, "ey": ey}, TTL, call)
    if not r["ok"]:
        return r
    routes = (r["data"] or {}).get("routes") or []
    coords = ((routes[0].get("geometry") or {}).get("coordinates") or []) if routes else []
    if (r["data"] or {}).get("code") != "Ok" or len(coords) < 2:
        return fail(NO_DATA, "보행 경로를 찾지 못했습니다.")
    path = [[round(x, 6), round(y, 6)] for x, y in coords]
    if len(path) > MAX_POINTS:
        step = (len(path) - 1) / (MAX_POINTS - 1)
        path = [path[round(i * step)] for i in range(MAX_POINTS)]
    return ok({"path": path, "distance_m": routes[0].get("distance")})
