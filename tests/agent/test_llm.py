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
