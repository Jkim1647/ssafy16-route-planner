import datetime as dt

from backend.tools import kma_weather
from backend.tools.kma_weather import get_weather, latest_base_time, latlon_to_grid
from tests.helpers import load, route_get

KMA = "VilageFcstInfoService"


def test_grid_seoul():
    assert latlon_to_grid(37.5665, 126.9780) == (60, 127)


def test_grid_gwangju_gwangsan():
    assert latlon_to_grid(35.1395, 126.7937) == (57, 74)


def test_base_time_before_0210():
    assert latest_base_time(dt.datetime(2026, 11, 18, 2, 5)) == ("20261117", "2300")


def test_base_time_midday():
    assert latest_base_time(dt.datetime(2026, 11, 18, 11, 34)) == ("20261118", "1100")


def _fixed_now(monkeypatch):
    monkeypatch.setattr(kma_weather, "now", lambda: dt.datetime(2026, 11, 18, 11, 34))


def test_weather_ok(monkeypatch):
    _fixed_now(monkeypatch)
    route_get(monkeypatch, [(lambda u, p: KMA in u, load("kma"))])
    r = get_weather(35.1395, 126.7937, "2026-11-19T15:00")
    assert r["ok"]
    d = r["data"]
    assert isinstance(d["pop"], int) and d["temp"] is not None and d["pty"] is not None


def test_weather_three_hourly_uses_nearest_slot(monkeypatch):
    _fixed_now(monkeypatch)
    route_get(monkeypatch, [(lambda u, p: KMA in u, load("kma"))])
    r = get_weather(35.1395, 126.7937, "2026-11-21T14:00")
    assert r["ok"] and r["data"]["forecast_at"] == "2026-11-21T15:00"


def test_weather_out_of_range(monkeypatch):
    _fixed_now(monkeypatch)
    route_get(monkeypatch, [(lambda u, p: KMA in u, load("kma"))])
    assert get_weather(35.1395, 126.7937, "2026-11-25T15:00")["error"]["code"] == "OUT_OF_RANGE"


def test_weather_far_future_no_call(monkeypatch):
    _fixed_now(monkeypatch)
    calls = route_get(monkeypatch, [(lambda u, p: KMA in u, load("kma"))])
    assert get_weather(35.1, 126.7, "2026-12-30T10:00")["error"]["code"] == "OUT_OF_RANGE"
    assert calls == []


def test_weather_bad_at():
    assert get_weather(35.1, 126.7, "내일")["error"]["code"] == "BAD_ARGUMENT"
