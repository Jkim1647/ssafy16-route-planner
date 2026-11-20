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


def test_get_llm_claude_uses_gms_anthropic_route(monkeypatch):
    # 2026-11-20: GMS의 GPT 쪽이 한도로 막혀 Claude로 전환(강사 안내 방식). 같은 ChatOpenAI로 GMS Anthropic 경로를 부르고,
    # GMS는 키를 x-api-key 헤더로 받는다. 명세 고정 버전(langchain-openai·langchain-core)을 그대로 쓰기 위해 새 패키지 없음.
    from langchain_openai import ChatOpenAI
    monkeypatch.setenv("LLM_MODEL", "claude-haiku-5-5")
    monkeypatch.setenv("GMS_BASE_URL", "https://gms.ssafy.io/gmsapi/api.openai.com/v1")
    monkeypatch.setenv("LLM_REASONING_EFFORT", "")
    llm = get_llm()
    assert isinstance(llm, ChatOpenAI)
    assert llm.model_name == "claude-haiku-5-5"
    assert llm.openai_api_base == "https://gms.ssafy.io/gmsapi/api.anthropic.com/v1"
    assert llm.default_headers["x-api-key"] == "test-key"


def test_get_llm_gpt_keeps_openai_route(monkeypatch):
    monkeypatch.setenv("LLM_MODEL", "gpt-6-luna")
    monkeypatch.setenv("LLM_REASONING_EFFORT", "")
    llm = get_llm()
    assert llm.openai_api_base == "https://gms.ssafy.io/gmsapi/api.openai.com/v1" or "api.openai.com" in str(llm.openai_api_base)
    assert not (llm.default_headers or {}).get("x-api-key")


def test_requirements_keep_spec_pinned_versions():
    # 명세서 1.2-5 필수 라이브러리 버전 고정 — LLM 전환으로 버전이 바뀌면 안 된다
    from pathlib import Path
    req = (Path(__file__).resolve().parents[2] / "requirements.txt").read_text(encoding="utf-8").split()
    for pin in ("langchain-openai==1.4.3", "langchain-core==1.6.0", "openai==2.54.0"):
        assert pin in req
    assert not any(r.startswith(("langchain-anthropic", "anthropic==")) for r in req)
