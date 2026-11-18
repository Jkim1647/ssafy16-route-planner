"""그래프 단계 사이에 전달하는 상태(설계 7.2)."""
from typing import Any, TypedDict


class AgentState(TypedDict, total=False):
    session_id: str
    run_id: str
    user_message: str
    # 분석
    intent: str
    intent_reason: str
    conditions: dict          # Conditions.model_dump(mode="json") — 대화 맥락으로 유지
    missing: list[str]
    option_ref: int | None
    # 계획·실행
    tasks: list[dict]
    strategy: int             # 0 기본, 1 거점 확장, 2 수단 확장, 3 전날 출발
    tool_errors: list[dict]
    places: dict
    options_raw: list         # judge 입력(Option 객체)
    busy: list
    weather: dict
    # 판단·재계획
    replan_count: int
    replan_history: list[dict]
    cards: list[dict]
    excluded: list[dict]
    undetermined: list[dict]
    estimated: list[dict]
    warnings: list[str]
    # 응답
    final_reply: str
    clarification: str | None
    status: str
    # 맥락(세션 간 유지)
    last_cards: list[dict]
    history: list[dict]
    extra: dict[str, Any]
