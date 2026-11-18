"""테스트 공용: 저장해 둔 실제 응답(tests/fixtures)으로 requests.get을 대신한다."""
import json
import pathlib

import requests

FIX = pathlib.Path(__file__).parent / "fixtures"


def load(name: str):
    return json.loads((FIX / f"{name}.json").read_text(encoding="utf-8"))


class Resp:
    def __init__(self, body, status=200):
        self._body, self.status_code = body, status

    def json(self):
        return self._body


def route_get(monkeypatch, routes):
    """routes: [(판별 함수(url, params) -> bool, body 또는 callable)] 순서대로 매칭. 호출 기록을 반환."""
    calls = []

    def fake(url, params=None, headers=None, timeout=None):
        calls.append((url, dict(params or {})))
        for match, body in routes:
            if match(url, params or {}):
                b = body(url, params or {}) if callable(body) else body
                return b if isinstance(b, Resp) else Resp(b)
        raise AssertionError(f"unrouted GET {url}")

    monkeypatch.setattr(requests, "get", fake)
    return calls
