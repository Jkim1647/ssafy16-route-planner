"""앱 구성 요소를 한곳에서 조립(설정·DB·저장소·이벤트 버스·Agent 그래프)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import backend.tools.catalog_all  # noqa: F401 — Tool 등록
from backend.agent.graph import Deps, build_graph
from backend.agent.llm import get_llm
from backend.agent.service import TurnResult, run_turn
from backend.db.database import init_db
from backend.db.repositories import AnomalyRepo, EventRepo, PlanRepo, RunRepo
from backend.events.bus import EventBus, build_bus
from backend.settings import Settings, get_settings


@dataclass
class Container:
    settings: Settings
    plans: PlanRepo
    events: EventRepo
    runs: RunRepo
    anomalies: AnomalyRepo
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
        c = cls(settings=s, plans=plans, events=events, runs=RunRepo(s.DB_PATH), anomalies=AnomalyRepo(s.DB_PATH),
                bus=build_bus(events, enabled=s.LOGGING_ENABLED), deps=deps, graph=build_graph(deps))
        return c

    def chat(self, session_id: str | None, message: str) -> TurnResult:
        return run_turn(self.graph, self.deps, self.bus, self.runs, session_id, message, after_run=self.after_run)
