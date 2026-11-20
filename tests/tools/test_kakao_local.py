import json

import pytest

from backend.tools import stations
from backend.tools.kakao_local import search_places
from backend.tools.stations import find_stations, haversine_km, normalize_station_name
from tests.helpers import load, route_get

KAKAO = "dapi.kakao.com"


def test_search_places_ok(monkeypatch):
    route_get(monkeypatch, [(lambda u, p: KAKAO in u, load("kakao_local"))])
    r = search_places("벡스코")
    assert r["ok"]
    first = r["data"]["places"][0]
    assert first["name"].startswith("벡스코")
    assert isinstance(first["x"], float) and isinstance(first["y"], float)
    assert first["place_url"]


def test_search_places_empty_query():
    assert search_places("")["error"]["code"] == "BAD_ARGUMENT"


def test_search_places_no_key(monkeypatch):
    monkeypatch.setenv("KAKAO_REST_KEY", "")
    calls = route_get(monkeypatch, [])
    assert search_places("벡스코")["error"]["code"] == "INVALID_KEY"
    assert calls == []


def test_search_places_no_data(monkeypatch):
    route_get(monkeypatch, [(lambda u, p: KAKAO in u, {"documents": [], "meta": {"total_count": 0}})])
    assert search_places("zzzzqqq")["error"]["code"] == "NO_DATA"


def test_search_places_ambiguous(monkeypatch):
    route_get(monkeypatch, [(lambda u, p: KAKAO in u, load("kakao_local_ambiguous"))])
    r = search_places("중앙역")
    assert r["error"]["code"] == "AMBIGUOUS_PLACE"
    assert "안산" in r["error"]["message"] and "부산" in r["error"]["message"]


def test_search_places_near_skips_ambiguity(monkeypatch):
    route_get(monkeypatch, [(lambda u, p: KAKAO in u, load("kakao_local_ambiguous"))])
    assert search_places("중앙역", near_x=129.03, near_y=35.10)["ok"]


def test_normalize_station_name():
    assert normalize_station_name("광주송정역") == "광주송정"
    assert normalize_station_name("서울역 (KTX)") == "서울"
    assert normalize_station_name(" 용산역 ") == "용산"


@pytest.fixture
def station_cache(tmp_path, monkeypatch):
    path = tmp_path / "stations.json"
    path.write_text(json.dumps({"광주송정": {"station_id": "NAT031857", "city": "24"},
                                "서광주": {"station_id": "NAT030879", "city": "24"},
                                "극락강": {"station_id": "NAT030667", "city": "24"}},
                               ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(stations, "CACHE_PATH", path)
    return path


def test_find_stations_matches_tago(monkeypatch, station_cache):
    route_get(monkeypatch, [(lambda u, p: KAKAO in u, load("kakao_stations_near"))])
    r = find_stations(126.7930, 35.1379)
    assert r["ok"]
    st = r["data"]["stations"]
    assert st[0]["station_id"] == "NAT031857" and st[0]["name"] == "광주송정"
    assert len(st) <= 3
    assert len({s["station_id"] for s in st}) == len(st)
    assert all("신호장" not in s["name"] for s in st)


def test_find_stations_prefers_ktx(monkeypatch, station_cache):
    docs = {"documents": [
        {"place_name": "서광주역", "x": "126.85", "y": "35.15", "category_name": "교통,수송 > 교통시설 > 기차역"},
        {"place_name": "광주송정역", "x": "126.79", "y": "35.13", "category_name": "교통,수송 > 교통시설 > 기차역 > KTX정차역"}],
        "meta": {}}
    route_get(monkeypatch, [(lambda u, p: KAKAO in u, docs)])
    st = find_stations(126.86, 35.16)["data"]["stations"]
    assert st[0]["name"] == "광주송정" and st[0]["ktx"] is True and st[1]["ktx"] is False


def test_find_stations_none_matched(monkeypatch, station_cache):
    route_get(monkeypatch, [(lambda u, p: KAKAO in u, {"documents": [{"place_name": "북송정신호장", "x": "126.8", "y": "35.1", "category_name": "교통 > 기차역"}], "meta": {}})])
    assert find_stations(126.79, 35.13)["error"]["code"] == "NO_DATA"


def test_find_stations_no_kakao_key(monkeypatch, station_cache):
    monkeypatch.setenv("KAKAO_REST_KEY", "")
    assert find_stations(126.79, 35.13)["error"]["code"] == "INVALID_KEY"


def test_haversine_seoul_busan():
    assert 315 <= haversine_km(126.9707, 37.5547, 129.0414, 35.1151) <= 335


def test_find_stations_wider_than_kakao_limit(monkeypatch, station_cache):
    # 4차 상호 점검 중 발견: 카카오 반경 상한은 20km라 Worker가 반경을 넓히면(40km) 실제 API가 오류를 냈다.
    # 20km 넘는 반경은 반경 없이 거리순으로 받고 거리로 거른다.
    sent = []
    docs = {"documents": [
        {"place_name": "광주송정역", "x": "126.79", "y": "35.13", "category_name": "기차역"},  # 약 33km
        {"place_name": "서광주역", "x": "126.85", "y": "35.15", "category_name": "기차역"}], "meta": {}}

    def match(u, p):
        sent.append(dict(p or {}))
        return KAKAO in u
    route_get(monkeypatch, [(match, docs)])
    r = find_stations(126.79, 35.43, radius_km=40)
    assert r["ok"] and all(s["distance_km"] <= 40 for s in r["data"]["stations"])
    assert all(int(p.get("radius", 0)) <= 20000 for p in sent)
    assert find_stations(126.79, 35.43, radius_km=30)["error"]["code"] == "NO_DATA"  # 31~33km 역은 30km 밖
