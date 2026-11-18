"""기상청 단기예보 Tool (F3004 보조: 강수확률·강수형태·기온). 예보 범위 밖은 지어내지 않고 OUT_OF_RANGE."""
import datetime as dt
import math
import os

from backend.tools.base import BAD_ARGUMENT, INVALID_KEY, OUT_OF_RANGE, UPSTREAM_ERROR, Tool, fail, ok
from backend.tools.budget import default_budget
from backend.tools.http import fetch_json
from backend.tools.registry import register

URL = "https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getVilageFcst"
BASE_HOURS = (2, 5, 8, 11, 14, 17, 20, 23)
PTY = {"0": "없음", "1": "비", "2": "비/눈", "3": "눈", "4": "소나기"}
MAX_DAYS_AHEAD = 4


def now() -> dt.datetime:
    return dt.datetime.now()


def latlon_to_grid(lat: float, lon: float) -> tuple[int, int]:
    """기상청 격자 변환(Lambert Conformal Conic, 기상청 공개 공식)."""
    re_, grid = 6371.00877, 5.0
    slat1, slat2, olon, olat, xo, yo = 30.0, 60.0, 126.0, 38.0, 43, 136
    d = math.pi / 180.0
    re = re_ / grid
    s1, s2, ol, oa = slat1 * d, slat2 * d, olon * d, olat * d
    sn = math.log(math.cos(s1) / math.cos(s2)) / math.log(math.tan(math.pi / 4 + s2 / 2) / math.tan(math.pi / 4 + s1 / 2))
    sf = math.tan(math.pi / 4 + s1 / 2) ** sn * math.cos(s1) / sn
    ro = re * sf / math.tan(math.pi / 4 + oa / 2) ** sn
    ra = re * sf / math.tan(math.pi / 4 + lat * d / 2) ** sn
    theta = lon * d - ol
    theta = (theta + math.pi) % (2 * math.pi) - math.pi
    theta *= sn
    return int(ra * math.sin(theta) + xo + 0.5), int(ro - ra * math.cos(theta) + yo + 0.5)


def latest_base_time(t: dt.datetime) -> tuple[str, str]:
    """발표 시각(02,05,…,23시) 중 API 제공 지연 10분을 지난 가장 최근 것."""
    ready = t - dt.timedelta(minutes=10)
    hours = [h for h in BASE_HOURS if h <= ready.hour]
    if not hours:
        prev = ready - dt.timedelta(days=1)
        return prev.strftime("%Y%m%d"), "2300"
    return ready.strftime("%Y%m%d"), f"{hours[-1]:02d}00"


def get_weather(lat: float, lon: float, at: str) -> dict:
    try:
        target = dt.datetime.fromisoformat(at)
    except (TypeError, ValueError):
        return fail(BAD_ARGUMENT, "at은 YYYY-MM-DDTHH:MM 형식이어야 합니다.")
    cur = now()
    if target.date() > cur.date() + dt.timedelta(days=MAX_DAYS_AHEAD) or target < cur - dt.timedelta(hours=1):
        return fail(OUT_OF_RANGE, "단기예보 범위(오늘~4일 뒤) 밖이라 날씨를 확인할 수 없습니다.")
    key = os.getenv("DATA_GO_KR_KEY", "").strip()
    if not key:
        return fail(INVALID_KEY, "DATA_GO_KR_KEY가 설정되지 않았습니다.")
    nx, ny = latlon_to_grid(lat, lon)
    base_date, base_time = latest_base_time(cur)
    params = {"dataType": "JSON", "numOfRows": 1500, "pageNo": 1,
              "base_date": base_date, "base_time": base_time, "nx": nx, "ny": ny}
    def fetch():  # HTTP 200 오류 응답은 캐시 전에 실패로 바꾼다(캐시되지 않게)
        r = fetch_json(URL, params={**params, "serviceKey": key})
        if r["ok"] and str((((r["data"] or {}).get("response") or {}).get("header") or {}).get("resultCode")) != "00":
            return fail(UPSTREAM_ERROR, "기상청 서비스 오류입니다.")
        return r
    r = default_budget().cached_call("kma", params, 3 * 3600, fetch)
    if not r["ok"]:
        return r
    resp = (r["data"] or {}).get("response") or {}
    items = (((resp.get("body") or {}).get("items")) or {}).get("item", [])
    # 3일 뒤부터는 3시간 간격 예보 → 가장 가까운 예보 시각(±3시간 이내)을 쓰고 그 시각을 함께 밝힌다
    slots = {}
    for i in items:
        slot = dt.datetime.strptime(i["fcstDate"] + i["fcstTime"], "%Y%m%d%H%M")
        slots.setdefault(slot, {})[i["category"]] = i["fcstValue"]
    near = min(slots, key=lambda s: (abs(s - target), s < target), default=None)
    if near is None or abs(near - target) > dt.timedelta(hours=3):
        return fail(OUT_OF_RANGE, "해당 시각의 예보가 아직 발표되지 않았습니다.")
    vals = slots[near]
    return ok({"at": target.isoformat(timespec="minutes"), "forecast_at": near.isoformat(timespec="minutes"),
               "pop": int(vals["POP"]) if "POP" in vals else None,
               "pty": PTY.get(vals.get("PTY")) if "PTY" in vals else None,
               "temp": float(vals["TMP"]) if "TMP" in vals else None})


register(Tool(
    name="get_weather",
    description="이동하는 날짜·시각에 출발지나 도착지에 비·눈이 올지(강수확률) 확인해 도보 구간 주의를 안내할 때 부른다. "
                "오늘부터 4일 뒤까지만 가능.",
    parameters={"type": "object",
                "properties": {"lat": {"type": "number"}, "lon": {"type": "number"},
                               "at": {"type": "string", "description": "YYYY-MM-DDTHH:MM"}},
                "required": ["lat", "lon", "at"]},
    func=get_weather, kind="external"))
