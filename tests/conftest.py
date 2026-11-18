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
    # 로컬 .env의 로그인 설정에 테스트가 좌우되지 않게 기본값(로그인 끔)으로. 필요한 테스트가 직접 켠다.
    monkeypatch.setenv("AUTH_REQUIRED", "false")
    for k in ("JWT_SECRET", "GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_REDIRECT_URI", "FRONTEND_URL",
              "CALENDAR_OWNER_EMAIL"):
        monkeypatch.setenv(k, "")  # 빈 값 → 설정 기본값


@pytest.fixture(autouse=True)
def temp_budget(tmp_path):
    """테스트마다 빈 캐시·쿼터 DB를 쓴다."""
    from backend.tools.budget import ApiBudget, set_default_budget

    set_default_budget(ApiBudget(str(tmp_path / "budget.db")))
    yield
    set_default_budget(None)
