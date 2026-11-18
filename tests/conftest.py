import pytest
import requests


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """테스트는 실제 외부 API를 부르지 않는다(ODsay 하루 30회 등 한도 보호, 설계 19-6)."""

    def _blocked(*args, **kwargs):
        raise AssertionError("테스트에서 실제 네트워크 호출 금지 — fixture로 monkeypatch 하세요")

    monkeypatch.setattr(requests, "get", _blocked)
    monkeypatch.setattr(requests, "post", _blocked)


@pytest.fixture(autouse=True)
def fake_keys(monkeypatch):
    """실제 키 대신 가짜 키. 키 없음 시나리오는 각 테스트에서 빈 값으로 덮어쓴다."""
    for k in ("KAKAO_REST_KEY", "ODSAY_API_KEY", "DATA_GO_KR_KEY", "ITS_API_KEY", "GMS_API_KEY"):
        monkeypatch.setenv(k, "test-key")
    monkeypatch.setenv("QUOTA_USE_RESERVE", "false")


@pytest.fixture(autouse=True)
def temp_budget(tmp_path):
    """테스트마다 빈 캐시·쿼터 DB를 쓴다."""
    from backend.tools.budget import ApiBudget, set_default_budget

    set_default_budget(ApiBudget(str(tmp_path / "budget.db")))
    yield
    set_default_budget(None)
