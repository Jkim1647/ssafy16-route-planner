import pytest
import requests


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """테스트는 실제 외부 API를 부르지 않는다(ODsay 하루 30회 등 한도 보호, 설계 19-6)."""

    def _blocked(*args, **kwargs):
        raise AssertionError("테스트에서 실제 네트워크 호출 금지 — fixture로 monkeypatch 하세요")

    monkeypatch.setattr(requests, "get", _blocked)
    monkeypatch.setattr(requests, "post", _blocked)
