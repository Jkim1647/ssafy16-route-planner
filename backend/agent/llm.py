"""GMS LLM 클라이언트(ChatOpenAI 하나로). 모델 이름이 `claude-*`면 GMS의 Anthropic 경로, 그 밖은 GMS_BASE_URL.
GMS 한도가 작아 최소 모델 + 호출 수 계측(요청당 최대 2회 목표)."""
from dataclasses import dataclass

from pydantic import BaseModel

from backend.settings import get_settings


class LLMUnavailable(RuntimeError):
    """GMS 키가 없거나 LLM을 쓸 수 없을 때. reason: "no_key"(키 없음) · "quota"(GMS 사용 한도 초과, 429)
    · "connection"(연결·시간 초과). 화면 안내 문장을 사유별로 고르는 데 쓴다."""

    def __init__(self, message: str, reason: str = "no_key"):
        super().__init__(message)
        self.reason = reason


@dataclass
class LLMCounter:
    count: int = 0


def anthropic_base_url(gms_base_url: str | None) -> str:
    """GMS는 공급자별 경로를 쓴다(.../gmsapi/api.openai.com/v1 ↔ .../gmsapi/api.anthropic.com/v1).
    OpenAI 경로 설정에서 같은 GMS 호스트의 Anthropic 경로를 만든다."""
    base = (gms_base_url or "https://gms.ssafy.io/gmsapi/api.openai.com/v1").rstrip("/")
    head = base.split("/api.openai.com")[0] if "/api.openai.com" in base else base.rsplit("/", 2)[0]
    return f"{head}/api.anthropic.com/v1"


def get_llm(temperature: float | None = None):
    """.env의 GMS 키·모델로 ChatOpenAI를 만든다(timeout 30초, 재시도 1회).
    LLM_MODEL이 `claude-`로 시작하면 GMS Anthropic 경로 + `x-api-key` 헤더(2026-11-20 GMS 안내: GPT 쪽 장애로 전환),
    아니면 GMS_BASE_URL(OpenAI 호환). 같은 클래스라 명세 고정 버전(langchain-openai)을 그대로 쓴다.
    GMS_API_KEY가 없으면 LLMUnavailable — graph analyze가 잡아 키 설정 안내 응답으로 바꾼다.
    """
    s = get_settings()
    if not s.GMS_API_KEY:
        raise LLMUnavailable("GMS_API_KEY가 설정되지 않았습니다.")
    from langchain_openai import ChatOpenAI

    kwargs = {"model": s.LLM_MODEL, "base_url": s.GMS_BASE_URL, "api_key": s.GMS_API_KEY,
              "timeout": 30, "max_retries": 1}
    if s.LLM_MODEL.startswith("claude-"):
        kwargs["base_url"] = anthropic_base_url(s.GMS_BASE_URL)
        kwargs["default_headers"] = {"x-api-key": s.GMS_API_KEY}  # GMS는 Anthropic 경로의 키를 이 헤더에서 찾는다
    if s.LLM_REASONING_EFFORT:
        kwargs["reasoning_effort"] = s.LLM_REASONING_EFFORT
    if temperature is not None:
        kwargs["temperature"] = temperature
    return ChatOpenAI(**kwargs)


def structured(llm, schema: type[BaseModel], messages: list, counter: LLMCounter | None = None) -> BaseModel:
    """LLM 구조화 출력 호출 1회. counter가 있으면 호출 전에 1 올린다(실패한 호출도 요청당 LLM 호출 수에 들어간다).
    한도 초과·연결 실패는 LLMUnavailable(reason)로 바꿔 화면에서 사유를 안내한다."""
    if counter is not None:
        counter.count += 1
    import openai

    try:
        return llm.with_structured_output(schema).invoke(messages)
    except openai.RateLimitError as e:  # 2026-11-20 실제 발생: GMS GPT 쪽 사용 한도 초과(429)
        raise LLMUnavailable("GMS 사용 한도를 넘었습니다.", reason="quota") from e
    except openai.APIConnectionError as e:  # 시간 초과(APITimeoutError)도 여기에 포함
        raise LLMUnavailable("GMS에 연결할 수 없습니다.", reason="connection") from e
