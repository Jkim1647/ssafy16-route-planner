"""옵션 조립과 제약 판단(F3008). LLM을 쓰지 않는 순수 계산. 숫자는 전부 Tool 결과에서만 나온다.

출발해야 할 시각 = 열차 출발 − 승차 여유(10분) − 출발 구간 소요
도착 시각       = 열차 도착 + 도착 구간 소요
통과 조건       = 도착 ≤ 마감 − 여유, 출발 ≥ 출발 하한, 총요금 ≤ 예산, 캘린더 일정과 겹치지 않음
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from backend.agent.conditions import Conditions
from backend.tools.stations import haversine_km

BOARD_BUFFER_MIN = 10
INTRACITY_KM = 40
RAIN_POP = 60
WALK_WARN_MIN = 10
ROAD_MODES = {"taxi", "car", "bus"}
NOTE = {"RATE_LIMITED": "대중교통 조회 한도 초과 → 택시 기준",
        "RUN_CAP": "요청당 대중교통 조회 상한(4회) → 택시 기준"}


@dataclass
class Leg:
    mode: str  # walk | subway | bus | taxi | train
    name: str | None
    minutes: int | None
    fare: int | None
    source: str


@dataclass
class Segment:
    """장소↔역(또는 장소↔장소) 한 구간을 가는 한 가지 방법."""
    kind: str  # transit | taxi
    minutes: int | None
    fare: int | None
    legs: list[Leg]
    note: str | None = None


@dataclass
class Option:
    id: str
    kind: str  # intercity | intracity
    legs: list[Leg]
    leave_at: dt.datetime | None
    arrive_at: dt.datetime | None
    total_fare: int | None
    estimated: bool = False
    warnings: list[str] = field(default_factory=list)
    basis: dict = field(default_factory=dict)
    points: list[dict] = field(default_factory=list)  # 지도 표시용 지점(출발지·역·도착지 좌표)

    @property
    def transfers(self) -> int:
        return max(sum(1 for leg in self.legs if leg.mode != "walk") - 1, 0)

    @property
    def total_min(self) -> int | None:
        if self.leave_at is None or self.arrive_at is None:
            return None
        return int((self.arrive_at - self.leave_at).total_seconds() // 60)

    @property
    def walk_min(self) -> int:
        return sum(leg.minutes or 0 for leg in self.legs if leg.mode == "walk")


@dataclass
class Busy:
    title: str
    start: dt.datetime
    end: dt.datetime


@dataclass
class Judgment:
    passed: list[Option]
    excluded: list[tuple[Option, str]]
    undetermined: list[tuple[Option, str]]
    estimated: list[Option]


def _hm(t: dt.datetime) -> str:
    return t.strftime("%H:%M")


def is_intracity(ox: float, oy: float, dx: float, dy: float, same_station: bool) -> bool:
    return same_station or haversine_km(ox, oy, dx, dy) < INTRACITY_KM


def _transit_segment(path: dict) -> Segment:
    legs = [Leg(lg["mode"], lg.get("name"), lg.get("min"), None, "odsay") for lg in path.get("legs", [])]
    return Segment("transit", path.get("total_min"), path.get("fare"), legs)


def _taxi_segment(car: dict, note: str | None = None) -> Segment:
    return Segment("taxi", car.get("duration_min"), car.get("taxi_fare"),
                   [Leg("taxi", "택시", car.get("duration_min"), car.get("taxi_fare"), "kakao_mobility")], note)


def segments_for(transit: dict | None, car: dict | None, transit_error: str | None) -> list[Segment]:
    """한 구간의 이동 방법 후보. 대중교통이 없으면 택시로 대체하고 그 사실을 표시한다(설계 18-5)."""
    segs = []
    if transit and transit.get("paths"):
        segs.append(_transit_segment(transit["paths"][0]))
    if car and car.get("duration_min") is not None:
        note = None if segs else NOTE.get(transit_error or "", "대중교통 정보 없음 → 택시 기준")
        segs.append(_taxi_segment(car, note))
    return segs or [Segment("unknown", None, None, [], "구간 소요시간 확인 불가")]


def _sum_fares(*fares) -> int | None:
    return None if any(f is None for f in fares) else sum(fares)


def build_intercity_options(trains: list[dict], access: list[Segment], egress: list[Segment]) -> list[Option]:
    opts = []
    for t in trains:
        dep, arr = dt.datetime.fromisoformat(t["dep_at"]), dt.datetime.fromisoformat(t["arr_at"])
        is_bus = t.get("kind") == "bus"
        train_leg = Leg("bus" if is_bus else "train", f"{t.get('grade')} {t.get('train_no')}",
                        int((arr - dep).total_seconds() // 60), t.get("fare"), "tago_bus" if is_bus else "tago_train")
        for a in access:
            for e in egress:
                leave = dep - dt.timedelta(minutes=BOARD_BUFFER_MIN + a.minutes) if a.minutes is not None else None
                arrive = arr + dt.timedelta(minutes=e.minutes) if e.minutes is not None else None
                notes = [s.note for s in (a, e) if s.note and s.kind != "unknown"]
                opts.append(Option(
                    id=f"{t.get('train_no')}-{a.kind}-{e.kind}", kind="intercity", legs=[*a.legs, train_leg, *e.legs],
                    leave_at=leave, arrive_at=arrive, total_fare=_sum_fares(a.fare, t.get("fare"), e.fare),
                    estimated=bool(t.get("estimated")), warnings=notes,
                    basis={"board_buffer_min": BOARD_BUFFER_MIN, "access_min": a.minutes, "egress_min": e.minutes,
                           "train_dep": _hm(dep), "train_arr": _hm(arr), "train_fare": t.get("fare"),
                           "access_fare": a.fare, "egress_fare": e.fare}))
    return opts


def build_intracity_options(paths: list[dict], car: dict | None, conds: Conditions) -> list[Option]:
    segs = [_transit_segment(p) for p in paths]
    if car and car.get("duration_min") is not None:
        segs.append(_taxi_segment(car))
    opts = []
    for i, s in enumerate(segs):
        if s.minutes is None:
            continue
        if conds.arrive_by:
            arrive = dt.datetime.combine(conds.date, dt.time.fromisoformat(conds.arrive_by)) \
                - dt.timedelta(minutes=conds.buffer_min)
            leave = arrive - dt.timedelta(minutes=s.minutes)
        else:
            leave = dt.datetime.combine(conds.date, dt.time.fromisoformat(conds.depart_after))
            arrive = leave + dt.timedelta(minutes=s.minutes)
        opts.append(Option(f"local-{s.kind}-{i}", "intracity", list(s.legs), leave, arrive, s.fare,
                           basis={"segment_min": s.minutes}))
    return opts


def evaluate(options: list[Option], conds: Conditions, busy: list[Busy], now: dt.datetime) -> Judgment:
    j = Judgment([], [], [], [])
    # "22시 이후 출발, 02:30까지 도착"처럼 마감이 출발 하한보다 이르면 마감은 다음 날이다
    overnight = bool(conds.arrive_by and conds.depart_after and conds.arrive_by <= conds.depart_after)
    deadline = (dt.datetime.combine(conds.date, dt.time.fromisoformat(conds.arrive_by))
                + dt.timedelta(days=overnight, minutes=-conds.buffer_min)) if conds.arrive_by else None

    def when(t: dt.datetime) -> str:  # 요청 날짜와 다른 날이면 날짜도 밝힌다
        return _hm(t) if t.date() == conds.date else t.strftime("%m-%d %H:%M")
    lower = dt.datetime.combine(conds.date, dt.time.fromisoformat(conds.depart_after)) if conds.depart_after else None
    if conds.date == now.date():
        lower = max(lower, now) if lower else now
    for o in options:
        if o.estimated:
            j.estimated.append(o)
            continue
        if o.leave_at is None or o.arrive_at is None:
            j.undetermined.append((o, "구간 소요시간 확인 불가"))
            continue
        if deadline and o.arrive_at > deadline:
            j.excluded.append((o, f"도착 {when(o.arrive_at)} > 마감 {when(deadline)}"))
            continue
        if lower and o.leave_at < lower:
            j.excluded.append((o, f"출발 {when(o.leave_at)} < 가능 시각 {when(lower)}"))
            continue
        clash = next((b for b in busy if o.leave_at < b.end and b.start < o.arrive_at), None)
        if clash:
            j.excluded.append((o, f"캘린더 '{clash.title}' {_hm(clash.start)}–{_hm(clash.end)}과 겹침"))
            continue
        if o.basis.get("rain_block"):
            pop, walk = o.basis["rain_block"]
            j.excluded.append((o, f"강수확률 {pop}% 시간대 도보 {walk}분 (비 회피 요청)"))
            continue
        if conds.budget is not None:
            if o.total_fare is None:
                j.undetermined.append((o, "운임 정보 없음 — 예산 판단 불가"))
                continue
            if o.total_fare > conds.budget:
                j.excluded.append((o, f"총 {o.total_fare:,}원 > 예산 {conds.budget:,}원"))
                continue
        j.passed.append(o)
    return j


def _dur(m: int) -> str:
    return f"{m // 60}시간 {m % 60}분" if m >= 60 else f"{m}분"


def checks_for(o: Option, conds: Conditions, busy: list[Busy], calendar_checked: bool) -> list[dict]:
    """통과한 후보가 사용자 조건을 어떻게 만족하는지(판단 결과). 계산에 쓴 값만 쓴다."""
    out = []
    if conds.arrive_by and o.arrive_at:
        overnight = bool(conds.depart_after and conds.arrive_by <= conds.depart_after)
        deadline = dt.datetime.combine(conds.date, dt.time.fromisoformat(conds.arrive_by)) + dt.timedelta(days=overnight)
        slack = int((deadline - o.arrive_at).total_seconds() // 60)
        out.append({"kind": "deadline", "text": f"마감 {conds.arrive_by}까지 여유 {_dur(slack)}"})
    if conds.depart_after:
        out.append({"kind": "depart", "text": f"{conds.depart_after} 이후 출발"})
    if conds.budget is not None and o.total_fare is not None:
        out.append({"kind": "budget", "text": f"예산 {conds.budget:,}원 중 {conds.budget - o.total_fare:,}원 남음"})
    if calendar_checked:
        out.append({"kind": "calendar", "text": f"그날 일정 {len(busy)}건과 안 겹침" if busy else "그날 일정 없음"})
    return out


_EXCLUSION_KINDS = (("도착", "마감"), ("총 ", "예산"), ("캘린더", "일정"), ("출발", "출발 시각"), ("강수", "날씨"))


def exclusion_kind(reason: str) -> str:
    """제외 사유 문장(evaluate가 만든 것)을 요약용 분류로."""
    return next((k for prefix, k in _EXCLUSION_KINDS if reason.startswith(prefix)), "기타")


_KEYS = {
    "cheapest": ("최저가", lambda o: (o.total_fare if o.total_fare is not None else 10**9, o.total_min or 0)),
    "fastest": ("최단 소요", lambda o: (o.total_min or 10**9, o.total_fare or 10**9)),
    "fewest_transfers": ("환승 최소", lambda o: (o.transfers, o.total_min or 10**9)),
}


def rank(passed: list[Option], priority: str) -> list[Option]:
    order = [priority] + [k for k in _KEYS if k != priority]
    picked: list[Option] = []
    for k in order:
        label, key = _KEYS[k]
        best = next((o for o in sorted(passed, key=key) if o not in picked), None)
        if best is not None and len(picked) < 3:
            best.basis["label"] = label
            picked.append(best)
    return picked


def apply_warnings(options: list[Option], weather: dict[str, dict], road_events: list[dict],
                   avoid: list[str]) -> list[Option]:
    pops = [w.get("pop") for w in weather.values() if w and w.get("pop") is not None]
    pop = max(pops) if pops else None
    for o in options:
        walk = o.walk_min
        if pop is not None and pop >= RAIN_POP and walk >= WALK_WARN_MIN:
            if "비" in avoid:
                o.basis["rain_block"] = (pop, walk)
            else:
                o.warnings.append(f"강수확률 {pop}% — 도보 {walk}분 구간 주의")
        if road_events and any(leg.mode in ROAD_MODES for leg in o.legs):
            for ev in road_events[:2]:
                o.warnings.append(f"경로 주변 {ev.get('type')}: {ev.get('description')}")
    return options
