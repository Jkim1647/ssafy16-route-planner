import datetime as dt

from backend.tools import its_events
from backend.tools.its_events import get_road_events
from tests.helpers import load, route_get

ITS = "openapi.its.go.kr"
BBOX = [126.6, 35.0, 127.1, 35.3]


def _today(monkeypatch, d=dt.date(2026, 11, 18)):
    monkeypatch.setattr(its_events, "today", lambda: d)


def test_events_today_all(monkeypatch):
    _today(monkeypatch)
    route_get(monkeypatch, [(lambda u, p: ITS in u, load("its"))])
    r = get_road_events(BBOX, "2026-11-18")
    assert r["ok"] and r["data"]["realtime"] is True and len(r["data"]["events"]) == 3
    e = r["data"]["events"][0]
    assert e["type"] == "공사" and e["description"] == "국도22호선 시설물보수작업"
    assert e["start"] == "2026-10-30T00:00" and isinstance(e["x"], float)


def test_events_future_date_filters_by_period(monkeypatch):
    _today(monkeypatch)
    route_get(monkeypatch, [(lambda u, p: ITS in u, load("its"))])
    r = get_road_events(BBOX, "2026-11-21")
    assert r["data"]["realtime"] is False
    assert {e["detail"] for e in r["data"]["events"]} == {"시설물보수작업", "기타공사"}  # 사고(11/19 종료)는 제외


def test_events_empty_is_ok_with_empty_list(monkeypatch):
    _today(monkeypatch)
    route_get(monkeypatch, [(lambda u, p: ITS in u, {"header": {"resultCode": 0}, "body": {"totalCount": 0, "items": []}})])
    r = get_road_events(BBOX, "2026-11-18")
    assert r["ok"] and r["data"]["events"] == []


def test_events_no_key(monkeypatch):
    monkeypatch.setenv("ITS_API_KEY", "")
    assert get_road_events(BBOX, "2026-11-18")["error"]["code"] == "INVALID_KEY"


def test_events_bad_bbox():
    assert get_road_events([1, 2], "2026-11-18")["error"]["code"] == "BAD_ARGUMENT"
