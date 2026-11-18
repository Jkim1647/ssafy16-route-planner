"""좌표 주변 기차역을 찾아 TAGO 역 ID로 연결하는 Tool (search_trains 입력 준비)."""
import json
import math
import os
import re
from pathlib import Path

from backend.tools.base import INVALID_KEY, NO_DATA, Tool, fail, ok
from backend.tools.http import fetch_json
from backend.tools.kakao_local import keyword_search
from backend.tools.registry import register

ROOT = Path(__file__).resolve().parents[2]
CACHE_PATH = ROOT / "data" / "cache" / "stations.json"
TRAIN = "https://apis.data.go.kr/1613000/TrainInfo"


def normalize_station_name(name: str) -> str:
    n = re.sub(r"\(.*?\)", "", name).strip().split()[0] if name.strip() else ""
    return n[:-1] if n.endswith("역") else n


def haversine_km(x1: float, y1: float, x2: float, y2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(y1), math.radians(y2)
    dp, dl = math.radians(y2 - y1), math.radians(x2 - x1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _items(body: dict) -> list:
    it = (((body or {}).get("response") or {}).get("body") or {}).get("items") or {}
    it = it.get("item", []) if isinstance(it, dict) else []
    return it if isinstance(it, list) else [it]


def load_station_index() -> dict | None:
    """TAGO 역 이름 → {station_id, city}. 처음 한 번 TAGO에서 받아 파일로 캐시한다."""
    if CACHE_PATH.exists():
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    key = os.getenv("DATA_GO_KR_KEY", "").strip()
    if not key:
        return None
    cities = fetch_json(f"{TRAIN}/GetCtyCodeList", params={"serviceKey": key, "_type": "json"})
    if not cities["ok"]:
        return None
    index = {}
    for c in _items(cities["data"]):
        r = fetch_json(f"{TRAIN}/GetCtyAcctoTrainSttnList",
                       params={"serviceKey": key, "_type": "json", "cityCode": c["citycode"], "numOfRows": 300})
        for s in _items(r["data"]) if r["ok"] else []:
            index[s["nodename"]] = {"station_id": s["nodeid"], "city": str(c["citycode"])}
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")
    return index


def find_stations(x: float, y: float, radius_km: float = 20) -> dict:
    index = load_station_index()
    if index is None:
        return fail(INVALID_KEY, "DATA_GO_KR_KEY가 없어 역 목록을 받을 수 없습니다.")
    r = keyword_search({"query": "기차역", "x": x, "y": y, "radius": int(radius_km * 1000), "sort": "distance"})
    if not r["ok"]:
        return r
    found, seen = [], set()
    for d in r["data"]:
        name = normalize_station_name(d.get("place_name", ""))
        info = index.get(name)
        if not info or info["station_id"] in seen:
            continue  # 신호장·화물역 등 TAGO에 없는 곳은 후보에서 뺀다
        seen.add(info["station_id"])
        sx, sy = float(d["x"]), float(d["y"])
        found.append({"station_id": info["station_id"], "name": name, "x": sx, "y": sy,
                      "distance_km": round(haversine_km(x, y, sx, sy), 2),
                      "ktx": "KTX" in (d.get("category_name") or "")})
    if not found:
        return fail(NO_DATA, "근처에서 열차를 탈 수 있는 역을 찾지 못했습니다.")
    found.sort(key=lambda s: (not s["ktx"], s["distance_km"]))  # KTX 정차역을 먼저(간선 열차가 많음)
    return ok({"stations": found[:3]})


register(Tool(
    name="find_stations",
    description="출발지나 도착지 좌표 근처에서 KTX·일반열차를 탈 수 있는 역과 그 역 ID가 필요할 때 부른다. "
                "열차 시간표를 조회하기 전에 쓴다.",
    parameters={"type": "object",
                "properties": {"x": {"type": "number", "description": "경도"},
                               "y": {"type": "number", "description": "위도"},
                               "radius_km": {"type": "number"}},
                "required": ["x", "y"]},
    func=find_stations, kind="external"))
