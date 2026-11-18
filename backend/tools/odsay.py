"""ODsay 대중교통(도보·지하철·버스) 구간 Tool (F3003 상세: 역↔장소 구간 소요시간·요금).

무료 요금제는 하루 30회라 반드시 ApiBudget 캐시·쿼터를 거친다(설계 19장).
"""
import os

from backend.tools.base import INVALID_KEY, NO_DATA, UPSTREAM_ERROR, Tool, fail, ok
from backend.tools.budget import default_budget
from backend.tools.http import fetch_json
from backend.tools.registry import register

URL = "https://api.odsay.com/v1/api/searchPubTransPathT"
TTL = 7 * 24 * 3600
MODES = {1: "subway", 2: "bus", 3: "walk"}


def _leg(s: dict) -> dict:
    mode = MODES.get(s.get("trafficType"), "walk")
    lane = (s.get("lane") or [{}])[0]
    name = lane.get("name") or lane.get("busNo") if mode != "walk" else None
    return {"mode": mode, "name": name, "min": s.get("sectionTime")}


def _path(p: dict) -> dict:
    info = p.get("info", {})
    legs = [_leg(s) for s in p.get("subPath", [])]
    rides = (info.get("busTransitCount") or 0) + (info.get("subwayTransitCount") or 0)
    walk = [leg["min"] for leg in legs if leg["mode"] == "walk"]
    return {"total_min": info.get("totalTime"), "fare": info.get("payment"),
            "transfers": max(rides - 1, 0), "walk_min": sum(walk) if all(m is not None for m in walk) else None,
            "legs": legs}


def get_transit_route(sx: float, sy: float, ex: float, ey: float) -> dict:
    key = os.getenv("ODSAY_API_KEY", "").strip()
    if not key:
        return fail(INVALID_KEY, "ODSAY_API_KEY가 설정되지 않았습니다.")
    args = {"sx": sx, "sy": sy, "ex": ex, "ey": ey}
    params = {"SX": sx, "SY": sy, "EX": ex, "EY": ey}
    r = default_budget().cached_call("odsay", args, TTL,
                                     lambda: _call(params, key))
    return r


def _call(params: dict, key: str) -> dict:
    r = fetch_json(URL, params={**params, "apiKey": key})
    if not r["ok"]:
        return r
    body = r["data"] or {}
    err = body.get("error")
    if err:
        err = err[0] if isinstance(err, list) else err
        msg = str(err.get("message") or err.get("msg") or "")
        if "ApiKey" in msg or "Auth" in msg:
            return fail(INVALID_KEY, "ODsay API 키 인증에 실패했습니다.")
        if str(err.get("code")) in {"3", "4", "5", "6", "-98"}:
            return fail(NO_DATA, "대중교통 경로를 찾지 못했습니다.")
        return fail(UPSTREAM_ERROR, "대중교통 조회 서비스 오류입니다.")
    paths = [_path(p) for p in (body.get("result") or {}).get("path", [])]
    paths = sorted([p for p in paths if p["total_min"] is not None], key=lambda p: p["total_min"])[:3]
    if not paths:
        return fail(NO_DATA, "대중교통 경로를 찾지 못했습니다.")
    return ok({"paths": paths})


register(Tool(
    name="get_transit_route",
    description="두 지점(예: 출발지↔기차역, 기차역↔목적지, 또는 같은 도시 안 이동) 사이를 도보·지하철·버스로 "
                "갈 때 걸리는 시간과 요금이 필요할 때 부른다.",
    parameters={"type": "object",
                "properties": {"sx": {"type": "number"}, "sy": {"type": "number"},
                               "ex": {"type": "number"}, "ey": {"type": "number"}},
                "required": ["sx", "sy", "ex", "ey"]},
    func=get_transit_route, kind="external"))
