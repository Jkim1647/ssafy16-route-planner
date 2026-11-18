"""백엔드 API(F3017): 대화 · 계획 관리 · 실행 로그 · 메타 정보를 서로 다른 경로로 제공."""
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from backend.agent.service import TurnResult
from backend.schemas import PlanIn, PlanOut, PlanSaveResult, PlanUpdate
from backend.tools.budget import default_budget
from backend.tools.registry import catalog

router = APIRouter(prefix="/api")


def _c(request: Request):
    return request.app.state.container


# ---------------------------------------------------------------- 대화
class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=500)
    session_id: str | None = Field(default=None, max_length=40)


@router.post("/chat", response_model=TurnResult, tags=["대화"])
def chat(body: ChatIn, request: Request):
    return _c(request).chat(body.session_id, body.message)


# ---------------------------------------------------------------- 계획
@router.get("/plans", response_model=list[PlanOut], tags=["계획"])
def list_plans(request: Request):
    return _c(request).plans.list()


@router.post("/plans", response_model=PlanSaveResult, status_code=201, tags=["계획"])
def create_plan(body: PlanIn, request: Request):
    return _c(request).plans.create(body)


@router.get("/plans/{plan_id}", response_model=PlanOut, tags=["계획"])
def get_plan(plan_id: int, request: Request):
    p = _c(request).plans.get(plan_id)
    if p is None:
        raise HTTPException(404, "그런 이동 계획이 없습니다.")
    return p


@router.put("/plans/{plan_id}", response_model=PlanSaveResult, tags=["계획"])
def update_plan(plan_id: int, body: PlanUpdate, request: Request):
    try:
        res = _c(request).plans.update(plan_id, body)
    except ValueError:
        raise HTTPException(422, "수정 값이 올바르지 않습니다.")
    if res is None:
        raise HTTPException(404, "그런 이동 계획이 없습니다.")
    return res


@router.delete("/plans/{plan_id}", status_code=204, tags=["계획"])
def delete_plan(plan_id: int, request: Request):
    if not _c(request).plans.delete(plan_id):
        raise HTTPException(404, "그런 이동 계획이 없습니다.")
    return Response(status_code=204)


@router.post("/plans/{plan_id}/calendar", tags=["계획"])
def register_plan_calendar(plan_id: int, request: Request):
    """캘린더 등록(F3023). Tool과 같은 함수를 쓰며 계획 ID만 받는다.
    JSON 요청만 받는다: 다른 사이트의 폼 전송(사전 확인 없이 보내지는 요청)으로 실제 캘린더에 일정이 생기지 않게."""
    from backend.tools.calendar_tools import register_calendar

    if not request.headers.get("content-type", "").startswith("application/json"):
        raise HTTPException(415, "Content-Type: application/json 요청만 받습니다.")
    r = register_calendar(plan_id)
    if not r["ok"]:
        status = {"NOT_FOUND": 404, "CONFLICT": 409, "BAD_ARGUMENT": 400}.get(r["error"]["code"], 502)
        raise HTTPException(status, r["error"]["message"])
    return r["data"]


# ---------------------------------------------------------------- 실행 로그 (수정 API 없음, F3014)
@router.get("/logs", tags=["실행 로그"])
def list_logs(request: Request):
    return _c(request).events.list_sessions()


@router.get("/logs/{session_id}", tags=["실행 로그"])
def get_log(session_id: str, request: Request):
    c = _c(request)
    events = c.events.get_session(session_id)
    if not events:
        raise HTTPException(404, "그런 실행 로그가 없습니다.")
    run_ids = list(dict.fromkeys(e["run_id"] for e in events))
    return {"session_id": session_id, "events": events,
            "runs": [{**(c.runs.get(r) or {"run_id": r}), "anomaly": c.anomalies.get(r)} for r in run_ids]}


@router.delete("/logs/{session_id}", status_code=204, tags=["실행 로그"])
def delete_log(session_id: str, request: Request):
    if not _c(request).events.delete_session(session_id):
        raise HTTPException(404, "그런 실행 로그가 없습니다.")
    return Response(status_code=204)


@router.get("/runs/{run_id}/anomaly", tags=["실행 로그"])
def get_anomaly(run_id: str, request: Request):
    a = _c(request).anomalies.get(run_id)
    if a is None:
        raise HTTPException(404, "판정 결과가 없습니다.")
    return a


# ---------------------------------------------------------------- 메타
@router.get("/tools", tags=["메타"])
def tools():
    return catalog()


@router.get("/config/status", tags=["메타"])
def config_status(request: Request):
    """키는 설정 여부(boolean)만, 값은 절대 내보내지 않는다(NF3002)."""
    s = _c(request).settings
    return {"keys": s.key_status(), "quota": default_budget().usage(), "model": s.LLM_MODEL,
            "agent_mode": s.AGENT_MODE, "calendar": s.CALENDAR_BACKEND}
