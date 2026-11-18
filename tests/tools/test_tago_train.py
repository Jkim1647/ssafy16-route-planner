import copy
import datetime as dt

from backend.tools import tago_train
from backend.tools.tago_train import search_trains
from tests.helpers import load, route_get

TAGO = "TrainInfo/GetStrtpntAlocFndTrainInfo"


def _train_fixture():
    return load("tago_train_plus1")


def test_search_trains_ok(monkeypatch):
    route_get(monkeypatch, [(lambda u, p: TAGO in u, _train_fixture())])
    r = search_trains("NAT031857", "NAT010032", "2026-11-19")
    assert r["ok"]
    t = r["data"]["trains"][0]
    assert dt.datetime.fromisoformat(t["dep_at"]) < dt.datetime.fromisoformat(t["arr_at"])
    assert isinstance(t["fare"], int) and t["train_no"] and t["grade"]
    assert r["data"]["estimated"] is False


def test_search_trains_default_date_is_today(monkeypatch):
    calls = route_get(monkeypatch, [(lambda u, p: TAGO in u, _train_fixture())])
    monkeypatch.setattr(tago_train, "today", lambda: dt.date(2026, 11, 18))
    r = search_trains("NAT031857", "NAT010032")
    assert r["data"]["date_requested"] == "2026-11-18"
    assert calls[0][1]["depPlandTime"] == "20261118"


def test_search_trains_missing_fare_is_none(monkeypatch):
    body = _train_fixture()
    for it in body["response"]["body"]["items"]["item"]:
        it.pop("adultcharge", None)
    route_get(monkeypatch, [(lambda u, p: TAGO in u, body)])
    assert search_trains("A", "B", "2026-11-19")["data"]["trains"][0]["fare"] is None


def test_search_trains_overnight_arrival(monkeypatch):
    body = copy.deepcopy(_train_fixture())
    body["response"]["body"]["items"]["item"] = [{
        "trainno": "1", "traingradename": "무궁화호", "depplacename": "a", "arrplacename": "b",
        "depplandtime": "20261119234000", "arrplandtime": "20261120021000", "adultcharge": "9000"}]
    route_get(monkeypatch, [(lambda u, p: TAGO in u, body)])
    t = search_trains("A", "B", "2026-11-19")["data"]["trains"][0]
    assert t["arr_at"].startswith("2026-11-20T02:10")


def test_search_trains_empty(monkeypatch):
    route_get(monkeypatch, [(lambda u, p: TAGO in u, load("tago_train_empty"))])
    assert search_trains("A", "A", "2026-11-19")["error"]["code"] == "NO_DATA"


def test_search_trains_bad_date():
    assert search_trains("A", "B", "2026-13-40")["error"]["code"] == "BAD_ARGUMENT"


def test_search_trains_no_key(monkeypatch):
    monkeypatch.setenv("DATA_GO_KR_KEY", "")
    assert search_trains("A", "B", "2026-11-19")["error"]["code"] == "INVALID_KEY"


def test_search_trains_auth_error_body(monkeypatch):
    body = {"response": {"header": {"resultCode": "30", "resultMsg": "SERVICE_KEY_IS_NOT_REGISTERED_ERROR"}}}
    route_get(monkeypatch, [(lambda u, p: TAGO in u, body)])
    assert search_trains("A", "B", "2026-11-19")["error"]["code"] == "INVALID_KEY"
