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


def test_normalize_terminal_brand_prefix():
    # 카카오 장소명은 브랜드가 앞에 붙는다(실사용 점검: 광주↔서울 고속버스 0건의 원인)
    assert normalize_terminal("유스퀘어광주종합버스터미널") == "광주"
    assert normalize_terminal("유스퀘어 광주종합버스터미널") == "광주"


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


def test_find_terminals_skips_shops_and_pages(monkeypatch, tmp_path):
    # 실사용 점검: 강남 근처 "고속터미널점" 가게들이 1쪽을 채워 센트럴시티(호남선)가 안 잡혔다
    p = tmp_path / "terminals.json"
    p.write_text(json.dumps({"서울경부": [{"terminal_id": "NAEK010", "name": "서울경부"}],
                             "센트럴시티": [{"terminal_id": "NAEK020", "name": "센트럴시티(서울)"}],
                             "다이소": [{"terminal_id": "X1", "name": "다이소"}]}, ensure_ascii=False),
                 encoding="utf-8")
    monkeypatch.setattr(tago_bus, "CACHE_PATH", p)
    term = "교통,수송 > 교통시설 > 고속,시외버스터미널"
    shop = {"place_name": "다이소 강남고속버스터미널점", "x": "127.0", "y": "37.5", "category_name": "가정,생활 > 생활용품점"}
    page1 = [shop] * 14 + [{"place_name": "서울고속버스터미널(경부)", "x": "127.004", "y": "37.504", "category_name": term}]
    page2 = [{"place_name": "센트럴시티터미널(호남)", "x": "127.003", "y": "37.505", "category_name": term}]
    route_get(monkeypatch, [(lambda u, q: KAKAO in u and q.get("page", 1) == 1, {"documents": page1, "meta": {}}),
                            (lambda u, q: KAKAO in u and q.get("page") == 2, {"documents": page2, "meta": {}})])
    ids = [t["terminal_id"] for t in find_terminals(127.0276, 37.4979)["data"]["terminals"]]
    assert ids == ["NAEK010", "NAEK020"]
