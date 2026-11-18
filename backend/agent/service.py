"""대화 1턴 실행. 실행 단위(run)마다 이벤트·LLM 호출 수를 모아 응답에 담는다."""
from __future__ import annotations

import threading
import uuid

from pydantic import BaseModel

from backend.agent.executor import RunCtx
from backend.agent.llm import LLMCounter
from backend.events.bus import Emitter

_lock = threading.Lock()  # 그래프 문맥(deps.ctx)이 실행 1회분이라 직렬 실행


class TurnResult(BaseModel):
    run_id: str
    session_id: str
    reply: str
    cards: list[dict] = []
    excluded: list[dict] = []
    undetermined: list[dict] = []
    estimated: list[dict] = []
    warnings: list[str] = []
    clarification: str | None = None
    status: str
    intent: str | None = None
    replan_count: int = 0
    llm_calls: int = 0
    events: list[dict] = []


RESET = {"tasks": [], "strategy": 0, "tool_errors": [], "replan_count": 0, "replan_history": [], "cards": [],
         "excluded": [], "undetermined": [], "estimated": [], "warnings": [], "clarification": None,
         "final_reply": "", "status": "", "missing": [], "option_ref": None, "extra": {}}


def run_turn(graph, deps, bus, run_repo, session_id: str | None, message: str,
             after_run=None) -> TurnResult:
    session_id = session_id or uuid.uuid4().hex[:12]
    run_id = uuid.uuid4().hex[:12]
    with _lock:
        em = Emitter(bus, session_id, run_id)
        counter = LLMCounter()
        deps.ctx = RunCtx(emitter=em, counter=counter)
        run_repo.start(run_id, session_id, message, deps.settings.AGENT_MODE)
        em.emit("run_start", payload={"message": message, "mode": deps.settings.AGENT_MODE})
        try:
            st = graph.invoke({**RESET, "session_id": session_id, "run_id": run_id, "user_message": message},
                              config={"configurable": {"thread_id": session_id}})
            status = st.get("status") or "done"
        except Exception as e:  # 그래프 오류도 응답으로 바꾼다(NF3003); 원문은 화면에 내보내지 않는다
            em.emit("error", payload={"type": type(e).__name__})
            st, status = {"final_reply": "처리 중 오류가 발생했어요. 잠시 후 다시 시도해 주세요."}, "error"
        em.emit("run_end", payload={"status": status, "replan_count": st.get("replan_count", 0),
                                    "llm_calls": counter.count})
        run_repo.finish(run_id, status, st.get("replan_count", 0), counter.count)
        if after_run:
            after_run(run_id)
        return TurnResult(run_id=run_id, session_id=session_id, reply=st.get("final_reply", ""),
                          cards=st.get("cards") or [], excluded=st.get("excluded") or [],
                          undetermined=st.get("undetermined") or [], estimated=st.get("estimated") or [],
                          warnings=st.get("warnings") or [], clarification=st.get("clarification"),
                          status=status, intent=st.get("intent"), replan_count=st.get("replan_count", 0),
                          llm_calls=counter.count, events=list(em.events))
