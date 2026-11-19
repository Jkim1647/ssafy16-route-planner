"""Planner·Worker 분리(F3021)의 Worker 판단 규칙.

- Worker는 평소 LLM 없이 작업 목록대로 Tool을 부른다.
- 인자를 고치면 결과가 달라질 수 있는 실패(결과 없음·대상 없음·잘못된 입력)일 때만 LLM에게
  재시도 / 건너뜀 / 계획 변경 요청 중 하나를 묻는다(WORKER_LLM=on).
- 재시도는 같은 Tool로만, WORKER_MAX_RETRY 이내, Planner가 사용자 조건으로 고정한 인자는 못 바꾼다.
- 키 오류·호출 한도·서버 오류·장소 모호(AMBIGUOUS)는 사용자에게 알리거나 멈출 일이라 LLM에 넘기지 않는다.
"""
from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, Field

RECOVERABLE = {"NO_DATA", "NOT_FOUND", "BAD_ARGUMENT"}
# 인자를 고치면 결과가 달라질 수 있는 Tool과 그 조정 가능 인자. 이 밖의 Tool은 규칙으로 건너뛴다(LLM 0회).
TUNABLE = {"find_stations": ["radius_km"], "find_terminals": ["radius_km"]}
# Planner가 사용자 조건(장소·날짜·시각)에서 채운 인자 — Worker가 바꿀 수 없다
FIXED_ARGS = {
    "search_places": ["query"], "find_stations": ["x", "y"], "search_trains": ["date"],
    "get_transit_route": ["sx", "sy", "ex", "ey"], "get_car_route": ["sx", "sy", "ex", "ey"],
    "get_weather": ["lat", "lon", "at"], "find_terminals": ["x", "y"], "search_express_bus": ["date"],
    "get_free_busy": ["date"], "get_road_events": ["date"], "search_terms": ["question"],
    "get_festivals": ["x", "y", "date"],
}

PROMPT = """너는 이동 플래너의 Worker다. Tool 호출이 실패했다. 인자를 고쳐 같은 Tool을 다시 부를지(retry),
이 작업을 건너뛸지(skip), Planner에게 계획 변경을 요청할지(request_replan) 하나를 고른다.
- 고정 인자 {fixed}는 절대 바꾸지 마라. 바꿀 수 있는 인자만 new_args에 넣는다.
- 예: 근처 역·터미널이 없으면 radius_km를 넓혀 retry.
Tool: {tool}
입력: {args}
실패: {code} — {message}
Tool 입력 규격: {schema}"""


class WorkerDecision(BaseModel):
    """Worker LLM의 실패 대응 판단: retry(new_args로 같은 Tool 재호출)·skip·request_replan. executor._worker_on_failure가 쓴다."""
    action: Literal["retry", "skip", "request_replan"]
    new_args: dict = Field(default_factory=dict)
    reason: str


def decide(llm, counter, tool_name: str, args: dict, error: dict, schema: dict) -> WorkerDecision:
    """실패한 호출(인자·오류 코드·입력 규격·고정 인자)을 프롬프트로 주고 WorkerDecision을 받는다(LLM 1회, counter 집계).
    고정 인자 위반 검사는 호출부가 violates_fixed로 따로 한다.
    """
    from backend.agent.llm import structured
    msg = PROMPT.format(fixed=FIXED_ARGS.get(tool_name, []), tool=tool_name,
                        args=json.dumps(args, ensure_ascii=False), code=error["code"], message=error["message"],
                        schema=json.dumps(schema, ensure_ascii=False))
    return structured(llm, WorkerDecision, [("system", msg)], counter)


def violates_fixed(tool_name: str, new_args: dict) -> list[str]:
    """new_args 중 Planner가 사용자 조건으로 고정한 인자(FIXED_ARGS) 이름 목록. 비어 있지 않으면 재시도는 무효 처리된다."""
    return [k for k in new_args if k in FIXED_ARGS.get(tool_name, [])]
