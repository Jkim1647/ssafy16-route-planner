"""API 요청·응답 모델(Pydantic)."""
import datetime as dt
import re

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

_HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def _check_hhmm(v):
    if v is not None and not _HHMM.match(v):
        raise ValueError("시각은 HH:MM 형식이어야 합니다.")
    return v


Coord = Annotated[list[float], Field(min_length=2, max_length=2)]  # [경도, 위도]


class LegIn(BaseModel):
    """계획에 저장하는 구간(경로 카드의 legs와 같은 모양). 크기 상한으로 저장소 남용을 막는다."""
    model_config = ConfigDict(extra="ignore")
    mode: str = Field(max_length=20)
    name: str | None = Field(default=None, max_length=100)
    minutes: int | None = Field(default=None, ge=0, le=10_000)
    fare: int | None = Field(default=None, ge=0, le=10_000_000)
    source: str | None = Field(default=None, max_length=30)
    path: list[Coord] | None = Field(default=None, max_length=400)
    line_code: int | None = None


class PointIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    kind: str = Field(max_length=20)
    name: str = Field(max_length=100)
    x: float
    y: float


class PlanIn(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    date: dt.date
    leave_at: str
    arrive_at: str
    origin_name: str = Field(min_length=1, max_length=100)
    destination_name: str = Field(min_length=1, max_length=100)
    legs: list[LegIn] = Field(default=[], max_length=30)
    total_fare: int | None = Field(default=None, ge=0, le=10_000_000)
    source_run_id: str | None = Field(default=None, max_length=40)
    points: list[PointIn] = Field(default=[], max_length=10)  # 지도 표시용 지점

    _v_times = field_validator("leave_at", "arrive_at")(_check_hhmm)


class PlanUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=100)
    date: dt.date | None = None
    leave_at: str | None = None
    arrive_at: str | None = None
    origin_name: str | None = None
    destination_name: str | None = None

    _v_times = field_validator("leave_at", "arrive_at")(_check_hhmm)


class PlanOut(PlanIn):
    id: int
    calendar_event_id: str | None = None
    created_at: dt.datetime
    updated_at: dt.datetime


class PlaceIn(BaseModel):
    """저장한 장소. label은 대화에서 부르는 이름(예: 집, 교육장)으로 사용자마다 하나씩."""
    label: str = Field(min_length=1, max_length=20)
    kind: str = Field(default="pin", pattern="^(home|school|work|pin)$")
    name: str = Field(min_length=1, max_length=100)
    address: str | None = Field(default=None, max_length=200)
    x: float = Field(ge=-180, le=180)
    y: float = Field(ge=-90, le=90)


class PlaceOut(PlaceIn):
    id: int


class PlanSaveResult(BaseModel):
    plan: PlanOut
    overlaps: list[PlanOut]
