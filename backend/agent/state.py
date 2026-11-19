"""그래프 단계 사이에 전달하는 상태(설계 7.2)."""
from typing import Any, TypedDict


class AgentState(TypedDict, total=False):
    """LangGraph 노드 사이에 오가는 상태(total=False라 모든 키가 선택).
    턴마다 service.RESET으로 초기화되는 키와, 체크포인터로 세션 동안 유지되는 맥락 키(conditions·last_cards·history 등)가 섞여 있다.
    """
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
    verify_rebuilt: bool
    worker_replanned: bool
