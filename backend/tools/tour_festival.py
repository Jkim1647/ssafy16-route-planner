"""TourAPI 행사 정보 Tool (참고 경고): 도착지 근처에서 그날 열리는 축제·행사 → 주변이 붐빌 수 있음을 안내.

한국관광공사 국문 관광정보 서비스(KorService2/searchFestival2). 지역 필터 대신 그날 진행 중인 행사 전체를
한 번 받아(하루 캐시) 좌표 거리로 거른다 — 시·도 코드 변환이 필요 없고 경계 근처 행사도 놓치지 않는다.
"""
import datetime as dt
import os

from backend.tools.base import BAD_ARGUMENT, INVALID_KEY, UPSTREAM_ERROR, Tool, fail, ok
from backend.tools.budget import default_budget
from backend.tools.http import fetch_json
from backend.tools.registry import register
from backend.tools.stations import haversine_km

URL = "https://apis.data.go.kr/B551011/KorService2/searchFestival2"
TTL = 6 * 60 * 60
ROWS = 1000  # 하루 진행 중 행사는 전국 150건 안팎(2026-11 실측)
MAX_FESTIVALS = 3
MAX_SPAN_DAYS = 31  # 1년 내내 하는 상설 공연은 혼잡 신호가 아니라서 뺀다


def _ymd(s: str | None) -> str | None:
    s = (s or "").strip()
    return f"{s[:4]}-{s[4:6]}-{s[6:8]}" if len(s) == 8 and s.isdigit() else None


def _items(body: dict) -> list:
    items = (((body or {}).get("response") or {}).get("body") or {}).get("items") or {}
    items = items.get("item", []) if isinstance(items, dict) else []
    return items if isinstance(items, list) else [items]


def get_festivals(x: float, y: float, date: str, radius_km: float = 1.0) -> dict:
    """좌표 반경 radius_km 안에서 date에 진행 중인 행사(가까운 순 최대 MAX_FESTIVALS개).
    기간이 MAX_SPAN_DAYS를 넘는 상설 행사는 뺀다. data = {festivals: [{title, start, end, address, x, y, distance_km}]}.
    실패: BAD_ARGUMENT, INVALID_KEY, UPSTREAM_ERROR. 행사가 없으면 실패가 아니라 빈 목록.
    """
    try:
        day = dt.date.fromisoformat(date)
    except (TypeError, ValueError):
        return fail(BAD_ARGUMENT, "date는 YYYY-MM-DD 형식이어야 합니다.")
    key = os.getenv("DATA_GO_KR_KEY", "").strip()
    if not key:
        return fail(INVALID_KEY, "DATA_GO_KR_KEY가 설정되지 않았습니다.")
    # eventStartDate = 이 날짜에 아직 끝나지 않은 행사(이미 시작한 행사 포함)
    params = {"MobileOS": "ETC", "MobileApp": "RoutePlanner", "_type": "json", "numOfRows": ROWS, "arrange": "A",
              "eventStartDate": day.strftime("%Y%m%d")}

    def fetch():  # HTTP 200 오류 응답은 캐시 전에 실패로 바꾼다(캐시되지 않게)
        r = fetch_json(URL, params={**params, "serviceKey": key})
        if r["ok"] and str((((r["data"] or {}).get("response") or {}).get("header") or {}).get("resultCode")) != "0000":
            return fail(UPSTREAM_ERROR, "관광정보 서비스 오류입니다.")
        return r
    r = default_budget().cached_call("tour", params, TTL, fetch)
    if not r["ok"]:
        return r
    found = []
    for i in _items(r["data"]):
        start, end = _ymd(i.get("eventstartdate")), _ymd(i.get("eventenddate"))
        if not (start and end and start <= day.isoformat() <= end and i.get("mapx") and i.get("mapy")):
            continue
        if (dt.date.fromisoformat(end) - dt.date.fromisoformat(start)).days > MAX_SPAN_DAYS:
            continue
        fx, fy = float(i["mapx"]), float(i["mapy"])
        km = haversine_km(x, y, fx, fy)
        if km <= radius_km:
            found.append({"title": i.get("title"), "start": start, "end": end, "address": i.get("addr1"),
                          "x": fx, "y": fy, "distance_km": round(km, 2)})
    return ok({"festivals": sorted(found, key=lambda f: f["distance_km"])[:MAX_FESTIVALS]})


register(Tool(
    name="get_festivals",
    description="이동하는 날 도착지 근처에서 축제·행사가 열려 주변이 붐빌 수 있는지 확인해 여유 있게 가라고 안내할 때 부른다.",
    parameters={"type": "object",
                "properties": {"x": {"type": "number"}, "y": {"type": "number"},
                               "date": {"type": "string", "description": "YYYY-MM-DD"},
                               "radius_km": {"type": "number"}},
                "required": ["x", "y", "date"]},
    func=get_festivals, kind="external"))
