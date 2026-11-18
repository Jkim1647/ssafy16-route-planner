"""ITS 돌발정보 Tool (F3004 보조: 공사·사고·통제). 개발용 키는 월 100회 → 실행당 최대 1회만 부른다.

실시간 정보라 출발일이 오늘이 아니면 기간(시작~종료)이 그 날짜를 포함하는 이벤트만 남긴다(지어내지 않음).
"""
import datetime as dt
import os
import re

from backend.tools.base import BAD_ARGUMENT, INVALID_KEY, UPSTREAM_ERROR, Tool, fail, ok
from backend.tools.budget import default_budget
from backend.tools.http import fetch_json
from backend.tools.registry import register

URL = "https://openapi.its.go.kr:9443/eventInfo"
TTL = 30 * 60


def today() -> dt.date:
    return dt.date.today()


def _ts(s: str | None) -> dt.datetime | None:
    try:
        return dt.datetime.strptime(s, "%Y%m%d%H%M%S") if s else None
    except ValueError:
        return None


def _event(i: dict) -> dict:
    start, end = _ts(i.get("startDate")), _ts(i.get("endDate"))
    detail = i.get("eventDetailType") or ""
    msg = re.sub(r"^<[^>]*>::", "", i.get("message") or "").strip()
    desc = " ".join(x for x in (i.get("roadName"), detail) if x) or msg[:40]
    return {"type": i.get("eventType"), "detail": detail, "description": desc,
            "start": start.isoformat(timespec="minutes") if start else None,
            "end": end.isoformat(timespec="minutes") if end else None,
            "x": float(i["coordX"]) if i.get("coordX") else None, "y": float(i["coordY"]) if i.get("coordY") else None}


def get_road_events(bbox: list, date: str) -> dict:
    if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
        return fail(BAD_ARGUMENT, "bbox는 [minX, minY, maxX, maxY]여야 합니다.")
    try:
        day = dt.date.fromisoformat(date)
    except (TypeError, ValueError):
        return fail(BAD_ARGUMENT, "date는 YYYY-MM-DD 형식이어야 합니다.")
    key = os.getenv("ITS_API_KEY", "").strip()
    if not key:
        return fail(INVALID_KEY, "ITS_API_KEY가 설정되지 않았습니다.")
    min_x, min_y, max_x, max_y = (round(float(v), 3) for v in bbox)
    params = {"type": "all", "eventType": "all", "minX": min_x, "maxX": max_x, "minY": min_y, "maxY": max_y,
              "getType": "json"}
    def fetch():  # HTTP 200 오류 응답은 캐시 전에 실패로 바꾼다(캐시되지 않게)
        r = fetch_json(URL, params={**params, "apiKey": key})
        if r["ok"] and str(((r["data"] or {}).get("header") or {}).get("resultCode", 0)) not in ("0", "00"):
            return fail(UPSTREAM_ERROR, "돌발정보 서비스 오류입니다.")
        return r
    r = default_budget().cached_call("its", params, TTL, fetch)
    if not r["ok"]:
        return r
    body = r["data"] or {}
    events = [_event(i) for i in (body.get("body") or {}).get("items") or []]
    realtime = day == today()
    if not realtime:
        lo, hi = dt.datetime.combine(day, dt.time.min), dt.datetime.combine(day, dt.time.max)
        events = [e for e in events
                  if e["end"] and dt.datetime.fromisoformat(e["end"]) >= lo
                  and (not e["start"] or dt.datetime.fromisoformat(e["start"]) <= hi)]
    return ok({"realtime": realtime, "events": events})


register(Tool(
    name="get_road_events",
    description="추천 경로에 버스·택시 같은 도로 구간이 있을 때, 그 주변의 공사·사고·통제 정보를 확인해 주의를 안내할 때 부른다.",
    parameters={"type": "object",
                "properties": {"bbox": {"type": "array", "items": {"type": "number"},
                                        "description": "[minX, minY, maxX, maxY]"},
                               "date": {"type": "string", "description": "YYYY-MM-DD"}},
                "required": ["bbox", "date"]},
    func=get_road_events, kind="external"))
