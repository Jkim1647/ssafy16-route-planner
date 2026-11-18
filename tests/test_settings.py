from backend.settings import get_settings


def test_missing_key_is_none(monkeypatch):
    monkeypatch.setenv("ODSAY_API_KEY", "")
    assert get_settings().ODSAY_API_KEY is None


def test_key_status_has_no_values(monkeypatch):
    monkeypatch.setenv("ODSAY_API_KEY", "secret123")
    status = get_settings().key_status()
    assert status["ODSAY_API_KEY"] is True
    assert "secret123" not in str(status)


def test_empty_reasoning_effort_is_none(monkeypatch):
    monkeypatch.setenv("LLM_REASONING_EFFORT", "")
    assert get_settings().LLM_REASONING_EFFORT is None


def test_bool_and_int_parsing(monkeypatch):
    monkeypatch.setenv("WORKER_LLM", "off")
    monkeypatch.setenv("MAX_REPLAN", "5")
    s = get_settings()
    assert s.WORKER_LLM is False
    assert s.MAX_REPLAN == 5
