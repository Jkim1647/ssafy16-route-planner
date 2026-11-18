"""요청 조건(F3005)과 후속 요청 병합(F3010). 추출하지 못한 값은 None으로 두고 지어내지 않는다."""
import datetime as dt
from typing import Literal

from pydantic import BaseModel, field_validator

from backend.schemas import _check_hhmm


class Conditions(BaseModel):
    # 기준
    origin: str | None = None
    destination: str | None = None
    date: dt.date | None = None
    arrive_by: str | None = None
    depart_after: str | None = None
    # 선호
    priority: Literal["cheapest", "fastest", "fewest_transfers"] = "cheapest"
    modes: list[str] | None = None
    avoid: list[str] = []
    # 제약
    budget: int | None = None
    buffer_min: int = 10

    _v_times = field_validator("arrive_by", "depart_after")(_check_hhmm)


def merge(old: Conditions | None, changes: dict) -> Conditions:
    """바뀐 키만 갱신한다. None은 '지우기'가 아니라 '언급 없음'. 지우려면 _clear 목록."""
    base = (old or Conditions()).model_dump()
    for k, v in changes.items():
        if k in base and v is not None:
            base[k] = v
    for k in changes.get("_clear") or []:
        if k in base:
            base[k] = Conditions.model_fields[k].default
    return Conditions(**base)


def missing_fields(c: Conditions, now: dt.datetime) -> list[str]:
    missing = [k for k in ("origin", "destination", "date") if getattr(c, k) is None]
    if c.arrive_by is None and c.depart_after is None:
        missing.append("time")
    if missing:
        return missing
    if c.date < now.date():
        return ["past_deadline"]
    if c.date == now.date() and c.arrive_by and c.arrive_by <= now.strftime("%H:%M"):
        return ["past_deadline"]
    return []
