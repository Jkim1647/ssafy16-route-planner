"""공유 화면용 계획 가리기: 주인이 '집'으로 저장한 곳 근처 지점은 동네 수준으로 흐리게 보낸다.

- 집에서 RADIUS_KM 안의 출발·도착 지점: 좌표를 GRID도(약 500m) 격자로 반올림, 이름은 '집 근처'
- 구간 동선 좌표(택시 도로 등) 중 집 RADIUS_KM 안의 점은 뺀다(길을 따라가면 집이 드러나므로)
- 주인 화면(/api/plans)은 그대로 — 공유 응답(/api/shared)에만 적용
"""
from __future__ import annotations

from backend.tools.stations import haversine_km

RADIUS_KM = 0.3
GRID = 0.005
LABEL = "집 근처"


def _near(x: float, y: float, homes) -> bool:
    return any(haversine_km(x, y, hx, hy) <= RADIUS_KM for hx, hy, _ in homes)


def _snap(v: float) -> float:
    return round(round(v / GRID) * GRID, 6)


def redact_home(data: dict, homes: list[tuple[float, float, set[str]]]) -> dict:
    """homes: [(x, y, {이름들})]. data(공유 응답 dict)를 고쳐 돌려준다. home_hidden: 가린 것이 있었는지."""
    hidden = False
    names = set().union(*(n for _, _, n in homes)) if homes else set()
    for p in data.get("points") or []:
        if homes and _near(p["x"], p["y"], homes):
            names.add(p["name"])
            p.update(x=_snap(p["x"]), y=_snap(p["y"]), name=LABEL)
            hidden = True
    for leg in data.get("legs") or []:
        path = leg.get("path")
        if homes and path:
            kept = [pt for pt in path if not _near(pt[0], pt[1], homes)]
            if len(kept) != len(path):
                hidden = True
                leg["path"] = kept if len(kept) >= 2 else None
    for key in ("origin_name", "destination_name"):
        if data.get(key) in names:
            data[key] = LABEL
            hidden = True
    for name in sorted(names - {LABEL, "집"}, key=len, reverse=True):  # 제목에 든 집 장소 이름(예: 아파트 이름)
        if name and name in (data.get("title") or ""):
            data["title"] = data["title"].replace(name, LABEL)
            hidden = True
    data["home_hidden"] = hidden
    return data
