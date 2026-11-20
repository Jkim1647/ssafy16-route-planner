import pytest
from pydantic import BaseModel

from backend.agent.llm import LLMCounter, LLMUnavailable, get_llm, structured
from tests.fakes import FakeLLM


class Out(BaseModel):
    v: int


def test_structured_counts_calls():
    counter = LLMCounter()
    llm = FakeLLM([Out(v=1), Out(v=2)])
    assert structured(llm, Out, ["a"], counter).v == 1
    assert structured(llm, Out, ["b"], counter).v == 2
    assert counter.count == 2


def test_get_llm_without_key_raises(monkeypatch):
    monkeypatch.setenv("GMS_API_KEY", "")
    with pytest.raises(LLMUnavailable):
        get_llm()


def test_get_llm_uses_minimal_model(monkeypatch):
    monkeypatch.setenv("LLM_MODEL", "gpt-5-nano")
    monkeypatch.setenv("LLM_REASONING_EFFORT", "minimal")
    llm = get_llm()
    assert llm.model_name == "gpt-5-nano"
    assert llm.reasoning_effort == "minimal"


def _req():
    import httpx
    return httpx.Request("POST", "https://gms.example/v1/chat/completions")


def test_structured_quota_error_becomes_unavailable():
    # GMS 뒤 OpenAI 조직 사용 한도 초과(429, 2026-11-20 실제 발생) → 일반 오류가 아니라 "한도" 사유로
    import httpx
    import openai
    err = openai.RateLimitError("429", response=httpx.Response(429, request=_req()),
                                body={"code": "organization_spend_limit_exceeded"})
    counter = LLMCounter()
    with pytest.raises(LLMUnavailable) as e:
        structured(FakeLLM([err]), Out, ["a"], counter)
    assert e.value.reason == "quota"
    assert counter.count == 1  # 실패한 호출도 센다


def test_structured_connection_error_becomes_unavailable():
    import openai
    with pytest.raises(LLMUnavailable) as e:
        structured(FakeLLM([openai.APIConnectionError(request=_req())]), Out, ["a"])
    assert e.value.reason == "connection"


def test_structured_other_errors_propagate():
    with pytest.raises(ValueError):  # 스키마 위반 같은 다른 오류는 그대로(호출부 처리 유지)
        structured(FakeLLM([ValueError("bad")]), Out, ["a"])
