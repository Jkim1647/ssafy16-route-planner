"""같은 인자로 두 번 부르면 두 번째는 영구 캐시에서 온다 → 결과 최상위 `cached`가 True여야 한다.
실행 로그의 tool_result `cached` 표시(executor)가 이 값을 그대로 쓴다. 첫 호출은 실제 호출이므로 False."""
import datetime as dt
import json

import pytest

from backend.tools import its_events, kma_weather, stations, tago_bus
from backend.tools.its_events import get_road_events
from backend.tools.kakao_local import search_places
from backend.tools.kakao_mobility import get_car_route
from backend.tools.kma_weather import get_weather
from backend.tools.stations import find_stations
from backend.tools.tago_bus import find_terminals, search_express_bus
from backend.tools.tago_train import search_trains
from backend.tools.tour_festival import get_festivals
from tests.helpers import load, route_get


@pytest.fixture
def caches(tmp_path, monkeypatch):
    st = tmp_path / "stations.json"
    st.write_text(json.dumps({"광주송정": {"station_id": "NAT031857", "city": "24"}}, ensure_ascii=False), "utf-8")
    monkeypatch.setattr(stations, "CACHE_PATH", st)
    te = tmp_path / "terminals.json"
    te.write_text(json.dumps({"광주": [{"terminal_id": "NAEK500", "name": "광주(유·스퀘어)"}]}, ensure_ascii=False),
                  "utf-8")
    monkeypatch.setattr(tago_bus, "CACHE_PATH", te)
    monkeypatch.setattr(kma_weather, "now", lambda: dt.datetime(2026, 11, 18, 11, 34))
    monkeypatch.setattr(its_events, "today", lambda: dt.date(2026, 11, 18))


TERMINAL_DOCS = {"documents": [{"place_name": "광주종합버스터미널 유스퀘어", "x": "126.88", "y": "35.16",
                                "category_name": "교통,수송 > 터미널 > 버스터미널"}], "meta": {}}
FESTIVAL = {"response": {"header": {"resultCode": "0000"}, "body": {"totalCount": 1, "items": {"item": [
    {"title": "축제", "eventstartdate": "20261118", "eventenddate": "20261122", "addr1": "주소",
     "mapx": "127.0280", "mapy": "37.4980"}]}}}}

CASES = {
    "search_places": ("dapi.kakao.com", lambda: load("kakao_local"), lambda: search_places("벡스코")),
    "find_stations": ("dapi.kakao.com", lambda: load("kakao_stations_near"), lambda: find_stations(126.7930, 35.1379)),
    "find_terminals": ("dapi.kakao.com", lambda: TERMINAL_DOCS, lambda: find_terminals(126.85, 35.2)),
    "search_trains": ("GetStrtpntAlocFndTrainInfo", lambda: load("tago_train_plus1"),
                      lambda: search_trains("NAT031857", "NAT010032", "2026-11-19")),
    "search_express_bus": ("GetStrtpntAlocFndExpbusInfo", lambda: load("tago_bus"),
                           lambda: search_express_bus("NAEK010", "NAEK700", "2026-11-19")),
    "get_car_route": ("kakaomobility", lambda: load("kakao_mobility"),
                      lambda: get_car_route(126.79, 35.13, 126.85, 35.16)),
    "get_weather": ("VilageFcstInfoService", lambda: load("kma"),
                    lambda: get_weather(35.1395, 126.7937, "2026-11-19T15:00")),
    "get_road_events": ("openapi.its.go.kr", lambda: load("its"),
                        lambda: get_road_events([126.6, 35.0, 127.1, 35.3], "2026-11-18")),
    "get_festivals": ("searchFestival2", lambda: FESTIVAL, lambda: get_festivals(127.0276, 37.4979, "2026-11-20")),
}


@pytest.mark.parametrize("name", list(CASES))
def test_second_call_reports_cache_hit(name, monkeypatch, caches):
    host, body, call = CASES[name]
    calls = route_get(monkeypatch, [(lambda u, p: host in u, lambda u, p: body())])
    first = call()
    n = len(calls)
    second = call()
    assert first["ok"] and second["ok"], (first, second)
    assert len(calls) == n, "두 번째 호출은 외부 API를 부르지 않아야 함"
    assert first.get("cached") is False
    assert second.get("cached") is True
    same = lambda d: {k: v for k, v in d.items() if k != "cached"} if isinstance(d, dict) else d  # noqa: E731
    assert same(second["data"]) == same(first["data"])  # 택시 Tool은 예전부터 data 안에도 cached를 담는다
