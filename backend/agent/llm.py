"""GMS(OpenAI 호환) LLM 클라이언트. GMS 한도가 작아 최소 모델 + 호출 수 계측(요청당 최대 2회 목표)."""
from dataclasses import dataclass

from pydantic import BaseModel

from backend.settings import get_settings


class LLMUnavailable(RuntimeError):
    """GMS 키가 없거나 LLM을 쓸 수 없을 때."""


@dataclass
class LLMCounter:
    count: int = 0


def get_llm(temperature: float | None = None):
    """.env의 GMS 엔드포인트·모델로 ChatOpenAI를 만든다(timeout 30초, 재시도 1회).
    GMS_API_KEY가 없으면 LLMUnavailable — graph analyze가 잡아 키 설정 안내 응답으로 바꾼다.
    """
    s = get_settings()
    if not s.GMS_API_KEY:
        raise LLMUnavailable("GMS_API_KEY가 설정되지 않았습니다.")
    from langchain_openai import ChatOpenAI

    kwargs = {"model": s.LLM_MODEL, "base_url": s.GMS_BASE_URL, "api_key": s.GMS_API_KEY,
              "timeout": 30, "max_retries": 1}
    if s.LLM_REASONING_EFFORT:
        kwargs["reasoning_effort"] = s.LLM_REASONING_EFFORT
    if temperature is not None:
        kwargs["temperature"] = temperature
    return ChatOpenAI(**kwargs)


def structured(llm, schema: type[BaseModel], messages: list, counter: LLMCounter | None = None) -> BaseModel:
    """LLM 구조화 출력 호출 1회. counter가 있으면 호출 전에 1 올린다(실패한 호출도 요청당 LLM 호출 수에 들어간다)."""
    if counter is not None:
        counter.count += 1
    return llm.with_structured_output(schema).invoke(messages)
