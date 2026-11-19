"""요청 조건(F3005)과 후속 요청 병합(F3010). 추출하지 못한 값은 None으로 두고 지어내지 않는다."""
import datetime as dt
from typing import Literal

from pydantic import BaseModel, field_validator

from backend.schemas import _check_hhmm


class Conditions(BaseModel):
    """한 대화의 이동 요청 조건. analyze 단계가 채우고 merge로 후속 요청을 반영하며, judge·trip이 읽는다.
    시각은 HH:MM 문자열이고, 모르는 값은 None으로 둔다(지어내지 않음).
    """
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
    """되묻기 전에 빠진 것을 고른다. 출발지·도착지·날짜·시각(arrive_by·depart_after 중 하나) 중 없는 키 목록,
    다 있으면 이미 지난 요청인지 보고 ["past_deadline"], 문제없으면 [].
    마감이 출발 하한보다 이르면 다음 날 마감으로 보아 '지남'으로 치지 않는다.
    """
    missing = [k for k in ("origin", "destination", "date") if getattr(c, k) is None]
    if c.arrive_by is None and c.depart_after is None:
        missing.append("time")
    if missing:
        return missing
    if c.date < now.date():
        return ["past_deadline"]
    overnight = bool(c.arrive_by and c.depart_after and c.arrive_by <= c.depart_after)  # 마감이 다음 날
    if c.date == now.date() and c.arrive_by and not overnight and c.arrive_by <= now.strftime("%H:%M"):
        return ["past_deadline"]
    return []
