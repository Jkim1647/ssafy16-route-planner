"""대화 1턴 실행. 실행 단위(run)마다 이벤트·LLM 호출 수를 모아 응답에 담는다."""
from __future__ import annotations

import threading
import uuid
from collections import OrderedDict

from pydantic import BaseModel

from backend.agent.executor import RunCtx
from backend.auth.context import current_user_id
from backend.agent.llm import LLMCounter
from backend.events.bus import Emitter

_lock = threading.Lock()  # 그래프 문맥(deps.ctx)이 실행 1회분이라 직렬 실행
MAX_SESSIONS = 200  # 대화 맥락을 메모리에 유지할 최근 세션 수
_sessions: OrderedDict[str, None] = OrderedDict()


def _touch(graph, session_id: str) -> None:
    """최근 사용 세션 순서를 갱신하고, 오래된 세션의 대화 상태는 메모리에서 지운다(실행 로그는 DB에 남음)."""
    _sessions[session_id] = None
    _sessions.move_to_end(session_id)
    while len(_sessions) > MAX_SESSIONS:
        old, _ = _sessions.popitem(last=False)
        graph.checkpointer.delete_thread(old)


class TurnResult(BaseModel):
    """POST /api/chat 응답 본문. 1턴 결과(답변·경로 카드·제외/판단 불가/추정 목록·경고·되묻기)와
    실행 계측(run_id·재계획 수·LLM 호출 수·이벤트)을 함께 담는다.
    """
    run_id: str
    session_id: str
    reply: str
    cards: list[dict] = []
    excluded: list[dict] = []
    undetermined: list[dict] = []
    estimated: list[dict] = []
    warnings: list[str] = []
    decision: dict | None = None  # 판단 요약 {checked, passed, excluded_by, undetermined, estimated}
    clarification: str | None = None
    status: str
    intent: str | None = None
    replan_count: int = 0
    llm_calls: int = 0
    events: list[dict] = []


RESET = {"tasks": [], "strategy": 0, "tool_errors": [], "replan_count": 0, "replan_history": [], "cards": [],
         "excluded": [], "undetermined": [], "estimated": [], "warnings": [], "clarification": None,
         "final_reply": "", "status": "", "missing": [], "option_ref": None, "extra": {},
         "verify_rebuilt": False, "worker_replanned": False}


def run_turn(graph, deps, bus, run_repo, session_id: str | None, message: str,
             after_run=None) -> TurnResult:
    """사용자 메시지 1건으로 그래프를 1회 실행한다. session_id가 없으면 새로 만들고, run마다 run_start/run_end 이벤트와 runs 행을 남긴다.
    전역 잠금으로 한 번에 한 턴만 돈다(deps.ctx를 턴마다 갈아끼우므로). 대화 상태 키는 '사용자ID:session_id'.
    그래프 예외는 status="error"와 일반 안내 문장으로 바꾼다. after_run(run_id)은 잠금 밖에서 부른다(이상 징후 진단).
    """
    session_id = session_id or uuid.uuid4().hex[:12]
    run_id = uuid.uuid4().hex[:12]
    with _lock:
        em = Emitter(bus, session_id, run_id)
        counter = LLMCounter()
        s = deps.settings
        deps.ctx = RunCtx(emitter=em, counter=counter, mode=s.AGENT_MODE, worker_llm=s.WORKER_LLM,
                          max_retry=s.WORKER_MAX_RETRY, llm_factory=deps.llm_factory,
                          db_path=getattr(deps.plan_repo, "db", None))
        run_repo.start(run_id, session_id, message, deps.settings.AGENT_MODE)
        em.emit("run_start", payload={"message": message, "mode": deps.settings.AGENT_MODE})
        try:
            st = graph.invoke({**RESET, "session_id": session_id, "run_id": run_id, "user_message": message},
                              config={"configurable": {"thread_id": f"{current_user_id()}:{session_id}"}})
            status = st.get("status") or "done"
        except Exception as e:  # 그래프 오류도 응답으로 바꾼다(NF3003); 원문은 화면에 내보내지 않는다
            em.emit("error", payload={"type": type(e).__name__})
            st, status = {"final_reply": "처리 중 오류가 발생했어요. 잠시 후 다시 시도해 주세요."}, "error"
        em.emit("run_end", payload={"status": status, "replan_count": st.get("replan_count", 0),
                                    "llm_calls": counter.count})
        run_repo.finish(run_id, status, st.get("replan_count", 0), counter.count)
        _touch(graph, f"{current_user_id()}:{session_id}")  # 대화 상태 키와 같은 형식
    if after_run:  # 이상 징후 진단(LLM)은 느릴 수 있어 잠금 밖에서 — 다른 요청을 막지 않는다
        after_run(run_id)
    return TurnResult(run_id=run_id, session_id=session_id, reply=st.get("final_reply", ""),
                      cards=st.get("cards") or [], excluded=st.get("excluded") or [],
                      undetermined=st.get("undetermined") or [], estimated=st.get("estimated") or [],
                      warnings=st.get("warnings") or [], clarification=st.get("clarification"),
                      status=status, intent=st.get("intent"), replan_count=st.get("replan_count", 0),
                      llm_calls=counter.count, events=list(em.events),
                      decision=(st.get("extra") or {}).get("decision"))
