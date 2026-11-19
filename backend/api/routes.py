"""백엔드 API(F3017): 대화 · 계획 관리 · 실행 로그 · 메타 정보를 서로 다른 경로로 제공."""
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field

from backend.agent.service import TurnResult
from backend.db.repositories import PlaceConflict
from backend.schemas import PlaceIn, PlaceOut, PlanIn, PlanOut, PlanSaveResult, PlanUpdate, TripIn
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


@router.post("/plans/{plan_id}/recheck", tags=["계획"])
def recheck_plan_api(plan_id: int, request: Request):
    """저장한 계획 다시 확인(당일 재확인): 시간표·캘린더·날씨·행사·출발 시각. LLM 없음."""
    from backend.agent.recheck import recheck_plan
    from backend.calendar.base import get_calendar

    c = _c(request)
    plan = c.plans.get(plan_id)
    if plan is None:
        raise HTTPException(404, "그런 이동 계획이 없습니다.")
    return recheck_plan(plan, calendar=get_calendar(c.settings), now=c.deps.now())


@router.get("/suggestions/calendar", tags=["계획"])
def calendar_suggestions_api(request: Request):
    """앞으로 이틀 안의 장소 있는 캘린더 일정 → 경로 찾기 제안(LLM·경로 계산 없음)."""
    from backend.agent.suggest import calendar_suggestions
    from backend.calendar.base import get_calendar

    c = _c(request)
    return calendar_suggestions(get_calendar(c.settings), c.deps.now())


# ---------------------------------------------------------------- 여러 동선 한꺼번에
@router.post("/trips/plan", tags=["여러 동선"])
def plan_trip(body: TripIn, request: Request):
    """지점 2~6개를 순서대로 잇는 이동을 구간별로 계산(LLM 없음). 앞 구간 도착 + 머무는 시간 = 다음 출발 하한."""
    from backend.agent.trip import TripError
    try:
        return _c(request).plan_trip(body)
    except TripError as e:
        raise HTTPException(400, str(e))


# ---------------------------------------------------------------- 저장한 장소(집·교육장 등)
# ---------------------------------------------------------------- 지도
KoreaPoint = Annotated[list[Annotated[float, Field(ge=33, le=132)]], Field(min_length=2, max_length=2)]


class ShapeIn(BaseModel):
    points: list[KoreaPoint] = Field(min_length=2, max_length=80)


@router.post("/map/road-shape", tags=["지도"])
def map_road_shape(body: ShapeIn):
    """버스 구간을 도로를 따라 그리기 위한 좌표(카카오 길찾기, 캐시). 정류장 좌표 [[경도, 위도], ...]를 받는다."""
    from backend.tools.kakao_mobility import road_shape
    for x, y in body.points:
        if not (124 <= x <= 132 and 33 <= y <= 39):
            raise HTTPException(422, "국내 좌표만 받을 수 있습니다.")
    r = road_shape(body.points)
    if not r["ok"]:
        raise HTTPException(404 if r["error"]["code"] in ("NO_DATA", "BAD_ARGUMENT") else 502, r["error"]["message"])
    return r["data"]


class WalkIn(BaseModel):
    points: list[KoreaPoint] = Field(min_length=2, max_length=2)


@router.post("/map/walk-shape", tags=["지도"])
def map_walk_shape(body: WalkIn):
    """도보 구간을 실제 길을 따라 그리기 위한 좌표(OpenStreetMap 보행 경로, FOSSGIS OSRM, 캐시). 그림에만 쓴다."""
    from backend.tools.osm_walk import walk_shape
    r = walk_shape(*body.points)
    if not r["ok"]:
        code = r["error"]["code"]
        raise HTTPException(422 if code == "BAD_ARGUMENT" else 404 if code in ("NO_DATA", "DISABLED") else 502,
                            r["error"]["message"])
    return r["data"]


@router.get("/places", response_model=list[PlaceOut], tags=["장소"])
def list_places(request: Request):
    return _c(request).places.list()


@router.get("/places/search", tags=["장소"])
def search_place(request: Request, q: str = Query(min_length=1, max_length=50)):
    """장소 이름 검색(카카오 로컬, 캐시 사용). 저장할 장소를 고를 때 쓴다."""
    from backend.tools.registry import get_tool
    r = get_tool("search_places").run(query=q)
    if not r["ok"]:
        code = r["error"]["code"]
        raise HTTPException(404 if code in ("NO_DATA", "AMBIGUOUS_PLACE") else 502, r["error"]["message"])
    return [{k: p.get(k) for k in ("name", "address", "x", "y")} for p in r["data"]["places"][:5]]


@router.post("/places", response_model=PlaceOut, status_code=201, tags=["장소"])
def create_place(body: PlaceIn, request: Request):
    try:
        return _c(request).places.create(body)
    except PlaceConflict:
        raise HTTPException(409, f"'{body.label}' 이름의 장소가 이미 있어요.")


@router.put("/places/{place_id}", response_model=PlaceOut, tags=["장소"])
def update_place(place_id: int, body: PlaceIn, request: Request):
    try:
        p = _c(request).places.update(place_id, body)
    except PlaceConflict:
        raise HTTPException(409, f"'{body.label}' 이름의 장소가 이미 있어요.")
    if p is None:
        raise HTTPException(404, "그런 장소가 없습니다.")
    return p


@router.delete("/places/{place_id}", status_code=204, tags=["장소"])
def delete_place(place_id: int, request: Request):
    if not _c(request).places.delete(place_id):
        raise HTTPException(404, "그런 장소가 없습니다.")
    return Response(status_code=204)


# ---------------------------------------------------------------- 실행 로그 (수정 API 없음, F3014)
@router.get("/logs", tags=["실행 로그"])
def list_logs(request: Request):
    return _c(request).events.list_sessions()


@router.get("/logs/{session_id}", tags=["실행 로그"])
def get_log(session_id: str, request: Request):
    c = _c(request)
    if not c.events.owns_session(session_id):
        raise HTTPException(404, "그런 실행 로그가 없습니다.")
    events = c.events.get_session(session_id)
    if not events:
        raise HTTPException(404, "그런 실행 로그가 없습니다.")
    run_ids = list(dict.fromkeys(e["run_id"] for e in events))
    return {"session_id": session_id, "events": events,
            "runs": [{**(c.runs.get(r) or {"run_id": r}), "anomaly": c.anomalies.get(r)} for r in run_ids]}


@router.delete("/logs/{session_id}", status_code=204, tags=["실행 로그"])
def delete_log(session_id: str, request: Request):
    if not _c(request).events.owns_session(session_id) or not _c(request).events.delete_session(session_id):
        raise HTTPException(404, "그런 실행 로그가 없습니다.")
    return Response(status_code=204)


@router.get("/runs/{run_id}/anomaly", tags=["실행 로그"])
def get_anomaly(run_id: str, request: Request):
    from backend.auth.context import current_user_id
    run = _c(request).runs.get(run_id)
    if run is None or run.get("user_id", "local") != current_user_id():
        raise HTTPException(404, "그런 실행이 없습니다.")
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
