import json

import pytest

from backend.tools import tago_bus
from backend.tools.tago_bus import find_terminals, normalize_terminal, search_express_bus
from tests.helpers import load, route_get

BUS = "ExpBusInfo/GetStrtpntAlocFndExpbusInfo"
KAKAO = "dapi.kakao.com"


def test_bus_ok(monkeypatch):
    route_get(monkeypatch, [(lambda u, p: BUS in u, load("tago_bus"))])
    r = search_express_bus("NAEK010", "NAEK700", "2026-11-19")
    assert r["ok"]
    b = r["data"]["buses"][0]
    assert b["dep_at"] == "2026-11-19T01:00" and b["arr_at"] == "2026-11-19T05:00"
    assert isinstance(b["fare"], int) and b["grade"] and b["train_no"].startswith("NAEK010700")


def test_bus_after_midnight_hour_24(monkeypatch):
    body = {"response": {"header": {"resultCode": "00"}, "body": {"items": {"item": [
        {"routeId": "R1", "depPlandTime": 202611192200, "arrPlandTime": 202611192430, "charge": 30000, "gradeNm": "우등"}]}}}}
    route_get(monkeypatch, [(lambda u, p: BUS in u, body)])
    assert search_express_bus("A", "B", "2026-11-19")["data"]["buses"][0]["arr_at"] == "2026-11-20T00:30"


def test_bus_empty(monkeypatch):
    body = {"response": {"header": {"resultCode": "00"}, "body": {"items": {"item": []}, "totalCount": 0}}}
    route_get(monkeypatch, [(lambda u, p: BUS in u, body)])
    assert search_express_bus("A", "B", "2026-11-19")["error"]["code"] == "NO_DATA"


def test_bus_bad_date():
    assert search_express_bus("A", "B", "11/19")["error"]["code"] == "BAD_ARGUMENT"


def test_normalize_terminal():
    assert normalize_terminal("광주종합버스터미널 유스퀘어") == "광주"
    assert normalize_terminal("광주(유·스퀘어)") == "광주"
    assert normalize_terminal("동서울종합터미널") == "동서울"


@pytest.fixture
def term_cache(tmp_path, monkeypatch):
    p = tmp_path / "terminals.json"
    p.write_text(json.dumps({"광주": [{"terminal_id": "NAEK500", "name": "광주(유·스퀘어)"}],
                             "동서울": [{"terminal_id": "NAEK032", "name": "동서울"}]}, ensure_ascii=False),
                 encoding="utf-8")
    monkeypatch.setattr(tago_bus, "CACHE_PATH", p)


def test_find_terminals_matches(monkeypatch, term_cache):
    docs = {"documents": [{"place_name": "광주종합버스터미널 유스퀘어", "x": "126.88", "y": "35.16",
                           "category_name": "교통,수송 > 터미널 > 버스터미널"}], "meta": {}}
    route_get(monkeypatch, [(lambda u, p: KAKAO in u, docs)])
    t = find_terminals(126.85, 35.2)["data"]["terminals"][0]
    assert t["terminal_id"] == "NAEK500" and t["x"] == 126.88


def test_find_terminals_none(monkeypatch, term_cache):
    route_get(monkeypatch, [(lambda u, p: KAKAO in u, {"documents": [], "meta": {}})])
    assert find_terminals(126.85, 35.2)["error"]["code"] == "NO_DATA"


def test_bus_empty_ids_bad_argument():
    from backend.tools.tago_bus import search_express_bus
    assert search_express_bus("", "")["error"]["code"] == "BAD_ARGUMENT"
