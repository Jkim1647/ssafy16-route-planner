"""앱 구성 요소를 한곳에서 조립(설정·DB·저장소·이벤트 버스·Agent 그래프)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import backend.tools.catalog_all  # noqa: F401 — Tool 등록
from backend.agent.graph import Deps, build_graph
from backend.agent.llm import get_llm
from backend.agent.service import TurnResult, run_turn
from backend.db.database import init_db
from backend.db.repositories import AnomalyRepo, EventRepo, PlaceRepo, PlanRepo, RunRepo, UserRepo
from backend.events.anomaly import evaluate_and_store
from backend.events.bus import EventBus, build_bus
from backend.settings import Settings, get_settings


@dataclass
class Container:
    settings: Settings
    plans: PlanRepo
    events: EventRepo
    runs: RunRepo
    anomalies: AnomalyRepo
    users: UserRepo
    places: PlaceRepo
    bus: EventBus
    deps: Deps
    graph: object
    after_run: Callable[[str], None] | None = None

    @classmethod
    def build(cls, llm_factory: Callable[[], object] = get_llm) -> "Container":
        s = get_settings()
        init_db(s.DB_PATH)
        events = EventRepo(s.DB_PATH)
        plans = PlanRepo(s.DB_PATH)
        deps = Deps(llm_factory=llm_factory, plan_repo=plans, settings=s)
        c = cls(settings=s, plans=plans, events=events, runs=RunRepo(s.DB_PATH), anomalies=AnomalyRepo(s.DB_PATH), users=UserRepo(s.DB_PATH), places=PlaceRepo(s.DB_PATH),
                bus=build_bus(events, enabled=s.LOGGING_ENABLED), deps=deps, graph=build_graph(deps))
        if s.LOGGING_ENABLED:  # 로깅 Agent의 평가: 실행이 끝나면 규칙 판정, 이상일 때만 LLM 진단(F3020)
            c.after_run = lambda run_id: evaluate_and_store(run_id, c.events, c.anomalies, llm_factory, s.MAX_REPLAN)
        return c

    def chat(self, session_id: str | None, message: str) -> TurnResult:
        from backend.auth.context import current_user_id
        if session_id and self.events.session_owner(session_id) not in (None, current_user_id()):
            session_id = None  # 다른 사용자의 세션 ID로 그 사람 대화 맥락에 끼어들 수 없게 새 세션으로
        return run_turn(self.graph, self.deps, self.bus, self.runs, session_id, message, after_run=self.after_run)
