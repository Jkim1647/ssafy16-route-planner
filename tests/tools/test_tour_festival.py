from backend.tools.tour_festival import get_festivals
from tests.helpers import route_get

TOUR = "KorService2/searchFestival2"


def body(items, code="0000"):
    return {"response": {"header": {"resultCode": code, "resultMsg": "OK"},
                         "body": {"items": {"item": items} if items else "", "totalCount": len(items)}}}


def fest(title, start, end, x, y):
    return {"title": title, "eventstartdate": start, "eventenddate": end, "addr1": "주소", "mapx": str(x), "mapy": str(y)}


def test_festivals_near_and_on_date(monkeypatch):
    items = [fest("가까운 축제", "20261118", "20261122", 127.0280, 37.4980),
             fest("먼 축제", "20261118", "20261122", 127.2, 37.6),
             fest("끝난 축제", "20261101", "20261110", 127.0277, 37.4979),
             fest("아직 안 한 축제", "20261201", "20261210", 127.0277, 37.4979)]
    calls = route_get(monkeypatch, [(lambda u, p: TOUR in u, body(items))])
    r = get_festivals(127.0276, 37.4979, "2026-11-20")
    assert r["ok"]
    f = r["data"]["festivals"]
    assert [x["title"] for x in f] == ["가까운 축제"]
    assert f[0]["start"] == "2026-11-18" and f[0]["end"] == "2026-11-22" and f[0]["distance_km"] < 1
    assert calls[0][1]["eventStartDate"] == "20261120"


def test_festivals_none_is_ok_empty(monkeypatch):
    route_get(monkeypatch, [(lambda u, p: TOUR in u, body([]))])
    assert get_festivals(126.88, 35.16, "2026-11-20")["data"]["festivals"] == []


def test_festivals_error_code(monkeypatch):
    route_get(monkeypatch, [(lambda u, p: TOUR in u, body([], code="30"))])
    assert get_festivals(126.88, 35.16, "2026-11-20")["error"]["code"] == "UPSTREAM_ERROR"


def test_festivals_bad_date():
    assert get_festivals(126.88, 35.16, "11/20")["error"]["code"] == "BAD_ARGUMENT"


def test_festivals_no_key(monkeypatch):
    monkeypatch.setenv("DATA_GO_KR_KEY", "")
    assert get_festivals(126.88, 35.16, "2026-11-20")["error"]["code"] == "INVALID_KEY"


def test_festivals_skip_year_round_shows(monkeypatch):
    # 실측: 인사동 '국악공연 진연'(1.1~12.31) 같은 상설 공연은 혼잡 신호가 아니다
    items = [fest("상설 공연", "20260101", "20261231", 127.0277, 37.4979),
             fest("주말 축제", "20261119", "20261122", 127.0278, 37.4979)]
    route_get(monkeypatch, [(lambda u, p: TOUR in u, body(items))])
    assert [f["title"] for f in get_festivals(127.0276, 37.4979, "2026-11-20")["data"]["festivals"]] == ["주말 축제"]
