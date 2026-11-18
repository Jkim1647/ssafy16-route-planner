"""TAGO 열차 시간표 조회 Tool (F3002 후보 조회, 필수)."""
import datetime as dt
import os

from backend.tools.base import BAD_ARGUMENT, INVALID_KEY, NO_DATA, UPSTREAM_ERROR, Tool, fail, ok
from backend.tools.budget import default_budget
from backend.tools.http import fetch_json
from backend.tools.registry import register

URL = "https://apis.data.go.kr/1613000/TrainInfo/GetStrtpntAlocFndTrainInfo"
TTL = 24 * 3600
AUTH_CODES = {"20", "30", "31", "32"}  # 공공데이터포털 인증·등록 오류 코드


def today() -> dt.date:
    return dt.date.today()


def _ts(s: str) -> str:
    return dt.datetime.strptime(s, "%Y%m%d%H%M%S").isoformat(timespec="minutes")


def search_trains(dep_station_id: str, arr_station_id: str, date: str | None = None) -> dict:
    if not dep_station_id or not arr_station_id:
        return fail(BAD_ARGUMENT, "출발역·도착역 ID는 필수입니다.")
    try:
        day = dt.date.fromisoformat(date) if date else today()  # 날짜 없으면 오늘(기본값, F3002)
    except ValueError:
        return fail(BAD_ARGUMENT, "date는 YYYY-MM-DD 형식이어야 합니다.")
    key = os.getenv("DATA_GO_KR_KEY", "").strip()
    if not key:
        return fail(INVALID_KEY, "DATA_GO_KR_KEY가 설정되지 않았습니다.")
    params = {"depPlaceId": dep_station_id, "arrPlaceId": arr_station_id,
              "depPlandTime": day.strftime("%Y%m%d"), "_type": "json", "numOfRows": 100}
    r = default_budget().cached_call("tago_train", params, TTL,
                                     lambda: fetch_json(URL, params={**params, "serviceKey": key}))
    if not r["ok"]:
        return r
    resp = (r["data"] or {}).get("response") or {}
    code = str((resp.get("header") or {}).get("resultCode", "00"))
    if code in AUTH_CODES:
        return fail(INVALID_KEY, "공공데이터포털 인증키가 등록되지 않았거나 승인되지 않았습니다.")
    if code != "00":
        return fail(UPSTREAM_ERROR, "열차 정보 서비스 오류입니다.")
    items = ((resp.get("body") or {}).get("items") or {})
    items = items.get("item", []) if isinstance(items, dict) else []
    items = items if isinstance(items, list) else [items]
    if not items:
        return fail(NO_DATA, "해당 날짜·구간의 열차가 없습니다.")
    trains = [{"train_no": it.get("trainno"), "grade": it.get("traingradename"),
               "dep_at": _ts(it["depplandtime"]), "arr_at": _ts(it["arrplandtime"]),
               "fare": int(it["adultcharge"]) if str(it.get("adultcharge", "")).isdigit() else None}
              for it in items]
    return ok({"date_requested": day.isoformat(), "date_queried": day.isoformat(),
               "estimated": False, "estimated_reason": None, "trains": trains})


register(Tool(
    name="search_trains",
    description="두 기차역 사이에서 특정 날짜에 운행하는 KTX·일반열차의 출발·도착 시각과 운임이 필요할 때 부른다. "
                "역 ID는 find_stations 결과를 쓴다. 날짜를 생략하면 오늘.",
    parameters={"type": "object",
                "properties": {"dep_station_id": {"type": "string"}, "arr_station_id": {"type": "string"},
                               "date": {"type": "string", "description": "YYYY-MM-DD"}},
                "required": ["dep_station_id", "arr_station_id"]},
    func=search_trains, kind="external"))
