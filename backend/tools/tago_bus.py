"""TAGO 고속버스 Tool (F3002 보충: 열차로 못 가는 구간의 간선 후보). 엔드포인트는 /ExpBusInfo (기획검증 확정)."""
import datetime as dt
import json
import os
import re
from pathlib import Path

from backend.tools.base import BAD_ARGUMENT, INVALID_KEY, NO_DATA, UPSTREAM_ERROR, Tool, fail, ok
from backend.tools.budget import default_budget
from backend.tools.http import fetch_json
from backend.tools.kakao_local import keyword_search
from backend.tools.registry import register
from backend.tools.stations import haversine_km

BASE = "https://apis.data.go.kr/1613000/ExpBusInfo"
ROOT = Path(__file__).resolve().parents[2]
CACHE_PATH = ROOT / "data" / "cache" / "terminals.json"
NOISE = ("종합", "고속", "시외", "버스", "터미널", "·")


def normalize_terminal(name: str) -> str:
    s = re.sub(r"\(.*?\)", "", name or "").strip()
    s = s.split()[0] if s else ""
    for w in NOISE:
        s = s.replace(w, "")
    return s


def _items(body):
    it = (((body or {}).get("response") or {}).get("body") or {}).get("items") or {}
    it = it.get("item", []) if isinstance(it, dict) else []
    return it if isinstance(it, list) else [it]


def load_terminal_index() -> dict | None:
    if CACHE_PATH.exists():
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    key = os.getenv("DATA_GO_KR_KEY", "").strip()
    if not key:
        return None
    r = fetch_json(f"{BASE}/GetExpBusTrminlList", params={"serviceKey": key, "_type": "json", "numOfRows": 1000})
    if not r["ok"]:
        return None
    index: dict[str, list] = {}
    for t in _items(r["data"]):
        index.setdefault(normalize_terminal(t["terminalNm"]), []).append(
            {"terminal_id": t["terminalId"], "name": t["terminalNm"]})
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")
    return index


def find_terminals(x: float, y: float, radius_km: float = 15) -> dict:
    index = load_terminal_index()
    if index is None:
        return fail(INVALID_KEY, "DATA_GO_KR_KEY가 없어 터미널 목록을 받을 수 없습니다.")
    r = keyword_search({"query": "고속버스터미널", "x": x, "y": y, "radius": int(radius_km * 1000), "sort": "distance"})
    if not r["ok"]:
        return r
    found, seen = [], set()
    for d in r["data"]:
        for t in index.get(normalize_terminal(d.get("place_name", "")), []):
            if t["terminal_id"] in seen:
                continue
            seen.add(t["terminal_id"])
            tx, ty = float(d["x"]), float(d["y"])
            found.append({**t, "x": tx, "y": ty, "distance_km": round(haversine_km(x, y, tx, ty), 2)})
    if not found:
        return fail(NO_DATA, "근처에서 고속버스 터미널을 찾지 못했습니다.")
    return ok({"terminals": sorted(found, key=lambda t: t["distance_km"])[:2]})


def _ts(v) -> str:
    s = re.sub(r"\D", "", str(v))[:12]  # YYYYMMDDHHMM, 자정 이후 도착은 2400·2530처럼 오기도 한다
    base = dt.datetime.strptime(s[:8], "%Y%m%d")
    return (base + dt.timedelta(hours=int(s[8:10]), minutes=int(s[10:12]))).isoformat(timespec="minutes")


def search_express_bus(dep_terminal_id: str, arr_terminal_id: str, date: str | None = None) -> dict:
    try:
        day = dt.date.fromisoformat(date) if date else dt.date.today()
    except ValueError:
        return fail(BAD_ARGUMENT, "date는 YYYY-MM-DD 형식이어야 합니다.")
    key = os.getenv("DATA_GO_KR_KEY", "").strip()
    if not key:
        return fail(INVALID_KEY, "DATA_GO_KR_KEY가 설정되지 않았습니다.")
    params = {"depTerminalId": dep_terminal_id, "arrTerminalId": arr_terminal_id,
              "depPlandTime": day.strftime("%Y%m%d"), "_type": "json", "numOfRows": 200}
    r = default_budget().cached_call("tago_bus", params, 24 * 3600,
                                     lambda: fetch_json(f"{BASE}/GetStrtpntAlocFndExpbusInfo",
                                                        params={**params, "serviceKey": key}))
    if not r["ok"]:
        return r
    code = str((((r["data"] or {}).get("response") or {}).get("header") or {}).get("resultCode", "00"))
    if code != "00":
        return fail(UPSTREAM_ERROR, "고속버스 정보 서비스 오류입니다.")
    items = _items(r["data"])
    if not items:
        return fail(NO_DATA, "해당 날짜·구간의 고속버스가 없습니다.")
    buses = [{"train_no": f"{i.get('routeId')}-{str(i['depPlandTime'])[-4:]}", "grade": f"고속버스 {i.get('gradeNm')}",
              "dep_at": _ts(i["depPlandTime"]), "arr_at": _ts(i["arrPlandTime"]),
              "fare": int(i["charge"]) if str(i.get("charge", "")).isdigit() else None, "kind": "bus"}
             for i in items]
    return ok({"date_requested": day.isoformat(), "estimated": False, "buses": buses})


register(Tool(
    name="find_terminals",
    description="열차 후보가 부족해 고속버스로 대안을 찾을 때, 출발지·도착지 근처 고속버스 터미널과 터미널 ID가 필요하면 부른다.",
    parameters={"type": "object", "properties": {"x": {"type": "number"}, "y": {"type": "number"}},
                "required": ["x", "y"]},
    func=find_terminals, kind="external"))
register(Tool(
    name="search_express_bus",
    description="두 고속버스 터미널 사이 특정 날짜의 고속버스 출발·도착 시각과 요금이 필요할 때 부른다(재계획 수단 확장).",
    parameters={"type": "object",
                "properties": {"dep_terminal_id": {"type": "string"}, "arr_terminal_id": {"type": "string"},
                               "date": {"type": "string"}},
                "required": ["dep_terminal_id", "arr_terminal_id"]},
    func=search_express_bus, kind="external"))
