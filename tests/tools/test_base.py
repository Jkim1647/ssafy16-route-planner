import datetime as dt

import pytest
import requests

from backend.tools import http
from backend.tools.base import Tool, fail, ok
from backend.tools.budget import ApiBudget, normalize_args
from backend.tools.registry import catalog, register


class FakeResp:
    def __init__(self, status, body=None, json_error=False):
        self.status_code = status
        self._body = body
        self._json_error = json_error

    def json(self):
        if self._json_error:
            raise ValueError("not json")
        return self._body


def test_run_type_error_becomes_bad_argument():
    t = Tool("one", "d", {}, lambda x: ok(x), "external")
    assert t.run(x=1, y=2)["error"]["code"] == "BAD_ARGUMENT"


def test_run_wrong_type_against_schema_is_bad_argument():
    # 셀프 체크리스트 1번 실제 실행(2026-11-20): find_terminals(x="abc")가 UPSTREAM_ERROR로 나왔다 — 잘못된 입력은 BAD_ARGUMENT
    schema = {"type": "object", "properties": {"x": {"type": "number"}, "n": {"type": "integer"}, "q": {"type": "string"}}}
    called = []
    t = Tool("typed", "d", schema, lambda **kw: called.append(kw) or ok(kw), "external")
    assert t.run(x="abc")["error"]["code"] == "BAD_ARGUMENT"
    assert t.run(n="1.5")["error"]["code"] == "BAD_ARGUMENT"
    assert t.run(q=3)["error"]["code"] == "BAD_ARGUMENT"
    assert called == []  # 함수까지 가지 않는다
    assert t.run(x=126.8, n=3, q="a")["ok"]
    assert t.run(x="126.8")["ok"]  # 숫자로 읽을 수 있는 문자열은 받아 준다(기존 동작)


def test_run_exception_becomes_upstream():
    def boom():
        raise ValueError("secretkey")

    r = Tool("boom", "d", {}, boom, "external").run()
    assert r["error"]["code"] == "UPSTREAM_ERROR"
    assert "secretkey" not in r["error"]["message"]


def test_catalog_only_public_fields():
    register(Tool("cat_test", "언제 쓰는지", {"type": "object"}, lambda: ok(1), "local"))
    entry = next(c for c in catalog() if c["name"] == "cat_test")
    assert set(entry) == {"name", "description", "parameters"}


def test_fetch_json_429_is_rate_limited(monkeypatch):
    monkeypatch.setattr(requests, "get", lambda *a, **k: FakeResp(429))
    assert http.fetch_json("https://x", params={"serviceKey": "k"})["error"]["code"] == "RATE_LIMITED"


def test_fetch_json_401_is_invalid_key(monkeypatch):
    monkeypatch.setattr(requests, "get", lambda *a, **k: FakeResp(401))
    assert http.fetch_json("https://x")["error"]["code"] == "INVALID_KEY"


def test_fetch_json_timeout(monkeypatch):
    def timeout(*a, **k):
        raise requests.Timeout("https://x?serviceKey=abc")

    monkeypatch.setattr(requests, "get", timeout)
    r = http.fetch_json("https://x", params={"serviceKey": "abc"})
    assert r["error"]["code"] == "UPSTREAM_ERROR"
    assert "serviceKey" not in r["error"]["message"]


def test_fetch_json_ok(monkeypatch):
    monkeypatch.setattr(requests, "get", lambda *a, **k: FakeResp(200, {"a": 1}))
    assert http.fetch_json("https://x") == ok({"a": 1})


@pytest.fixture
def budget(tmp_path, monkeypatch):
    monkeypatch.setenv("QUOTA_USE_RESERVE", "false")
    day = {"d": dt.date(2026, 11, 18)}
    b = ApiBudget(str(tmp_path / "b.db"), today=lambda: day["d"])
    b._day = day
    return b


def test_budget_cache_hit_no_second_call(budget):
    calls = []

    def fn():
        calls.append(1)
        return ok({"v": 1})

    first = budget.cached_call("odsay", {"sx": 1}, 60, fn)
    second = budget.cached_call("odsay", {"sx": 1}, 60, fn)
    assert len(calls) == 1
    assert first.get("cached") is False and second["cached"] is True
    assert budget.usage()["odsay"]["used"] == 1


def test_budget_coords_rounded_share_cache():
    assert normalize_args({"x": 126.79312}) == normalize_args({"x": 126.79349})


def test_budget_odsay_stops_at_24_without_reserve(budget, monkeypatch):
    n = {"c": 0}

    def fn():
        n["c"] += 1
        return ok(n["c"])

    for i in range(24):
        assert budget.cached_call("odsay", {"i": i}, 0, fn)["ok"]
    r = budget.cached_call("odsay", {"i": 99}, 0, fn)
    assert r["error"]["code"] == "RATE_LIMITED" and n["c"] == 24
    monkeypatch.setenv("QUOTA_USE_RESERVE", "true")
    for i in range(6):
        assert budget.cached_call("odsay", {"r": i}, 0, fn)["ok"]
    assert budget.cached_call("odsay", {"r": 99}, 0, fn)["error"]["code"] == "RATE_LIMITED"


def test_budget_failure_not_cached(budget):
    calls = []

    def fn():
        calls.append(1)
        return fail("NO_DATA", "없음")

    budget.cached_call("kakao", {"q": "a"}, 60, fn)
    budget.cached_call("kakao", {"q": "a"}, 60, fn)
    assert len(calls) == 2


def test_budget_resets_next_day(budget):
    budget.cached_call("odsay", {"a": 1}, 0, lambda: ok(1))
    budget._day["d"] = dt.date(2026, 11, 19)
    assert budget.usage()["odsay"]["used"] == 0


def test_budget_no_cache_forces_real_call(budget):
    calls = []

    def fn():
        calls.append(1)
        return ok(1)
    budget.cached_call("kakao", {"q": 1}, 60, fn)
    with budget.no_cache():
        r = budget.cached_call("kakao", {"q": 1}, 60, fn)
    assert len(calls) == 2 and r["cached"] is False
    assert budget.cached_call("kakao", {"q": 1}, 60, fn)["cached"] is True


def test_budget_its_daily_soft_limit(budget):
    for i in range(4):
        budget.cached_call("its", {"i": i}, 0, lambda: ok(1))
    assert budget.cached_call("its", {"i": 9}, 0, lambda: ok(1))["error"]["code"] == "RATE_LIMITED"
