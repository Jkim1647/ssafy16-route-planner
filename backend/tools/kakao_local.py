"""카카오 로컬 키워드 검색 Tool (F3004 보조 정보: 위치·주소·링크)."""
import os

from backend.tools.base import AMBIGUOUS_PLACE, BAD_ARGUMENT, INVALID_KEY, NO_DATA, Tool, fail, ok
from backend.tools.budget import default_budget
from backend.tools.http import fetch_json
from backend.tools.registry import register

URL = "https://dapi.kakao.com/v2/local/search/keyword.json"
TTL = 30 * 24 * 3600


def kakao_headers() -> dict | None:
    """카카오 REST API 인증 헤더. KAKAO_REST_KEY가 없으면 None(호출부가 INVALID_KEY로 바꾼다)."""
    key = os.getenv("KAKAO_REST_KEY", "").strip()
    return {"Authorization": f"KakaoAK {key}"} if key else None


KAKAO_MAX_RADIUS_M = 20000  # 카카오 키워드 검색 radius 상한(넘으면 오류)


def radius_params(radius_km: float) -> dict:
    """반경 조건. 상한(20km) 안이면 radius로 보내고, 넘으면 보내지 않는다(거리순 결과를 받아 호출한 쪽이 거리로 거른다)."""
    m = int(radius_km * 1000)
    return {"radius": m} if m <= KAKAO_MAX_RADIUS_M else {}


def keyword_search(params: dict) -> dict:
    """카카오 키워드 검색 원본 호출(캐시·쿼터 포함). documents 목록을 반환."""
    headers = kakao_headers()
    if headers is None:
        return fail(INVALID_KEY, "KAKAO_REST_KEY가 설정되지 않았습니다.")
    r = default_budget().cached_call("kakao", params, TTL, lambda: fetch_json(URL, params=params, headers=headers))
    if not r["ok"]:
        return r
    return ok(r["data"].get("documents", []), cached=r.get("cached", False))


def _place(d: dict) -> dict:
    return {"name": d.get("place_name"), "address": d.get("road_address_name") or d.get("address_name"),
            "x": float(d["x"]), "y": float(d["y"]), "place_url": d.get("place_url")}


def _first(s: str | None) -> str:
    """첫 단어(시·도 또는 이름 머리). 빈 값이면 빈 문자열."""
    parts = (s or "").split()
    return parts[0] if parts else ""


def search_places(query: str, near_x: float | None = None, near_y: float | None = None) -> dict:
    """키워드로 장소를 최대 5개 찾는다. near_x·near_y를 주면 그 좌표에서 가까운 순. data = {places}.
    실패: BAD_ARGUMENT, NO_DATA, AMBIGUOUS_PLACE(기준 좌표 없이 같은 이름이 여러 시·도에 있음 — 임의로 고르지 않고
    후보 최대 3개를 메시지에 담는다), 그 밖은 카카오 검색 실패 코드 그대로.
    """
    if not query or not query.strip():
        return fail(BAD_ARGUMENT, "query는 필수입니다.")
    params = {"query": query.strip(), "size": 5}
    if near_x is not None and near_y is not None:
        params.update({"x": near_x, "y": near_y, "sort": "distance"})
    r = keyword_search(params)
    if not r["ok"]:
        return r
    docs = r["data"]
    if not docs:
        return fail(NO_DATA, f"'{query}' 장소를 찾지 못했습니다.")
    if near_x is None:
        head = _first(docs[0].get("place_name"))
        same = [d for d in docs if _first(d.get("place_name")) == head]
        regions = {_first(d.get("address_name")) for d in same} - {""}
        if len(regions) > 1:  # 같은 이름이 서로 다른 시·도에 있으면 임의로 고르지 않는다
            seen, cands = set(), []
            for d in same:
                reg = _first(d.get("address_name"))
                if reg not in seen:
                    seen.add(reg)
                    cands.append(f"{d['place_name']}({d.get('address_name')})")
            return fail(AMBIGUOUS_PLACE, "같은 이름의 장소가 여러 지역에 있습니다: " + ", ".join(cands[:3]))
    return ok({"places": [_place(d) for d in docs]}, cached=r["cached"])


register(Tool(
    name="search_places",
    description="사용자가 말한 출발지·도착지 이름(동네, 건물, 역 이름)을 좌표와 주소로 바꿔야 할 때 부른다. "
                "다른 Tool에 좌표를 넘기기 전에 가장 먼저 쓴다.",
    parameters={"type": "object",
                "properties": {"query": {"type": "string", "description": "장소 이름"},
                               "near_x": {"type": "number"}, "near_y": {"type": "number"}},
                "required": ["query"]},
    func=search_places, kind="external"))
