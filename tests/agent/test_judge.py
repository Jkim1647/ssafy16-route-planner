import datetime as dt

from backend.agent.conditions import Conditions
from backend.agent.judge import (Busy, Leg, Option, Segment, apply_warnings, build_intercity_options,
                                 build_intracity_options, evaluate, is_intracity, rank, segments_for)

D = dt.date(2026, 11, 21)
NOW = dt.datetime(2026, 11, 18, 11, 0)


def T(hhmm, day=D):
    h, m = map(int, hhmm.split(":"))
    return dt.datetime.combine(day, dt.time(h, m))


def train(dep, arr, fare=42000, no="101", arr_day=D):
    return {"train_no": no, "grade": "KTX", "dep_at": T(dep).isoformat(), "arr_at": T(arr, arr_day).isoformat(),
            "fare": fare}


def transit(minutes, fare=1250, walk=5, rides=1):
    legs = [Leg("walk", None, walk, None, "odsay")] + [Leg("bus", f"버스{i}", (minutes - walk) // rides, None, "odsay")
                                                       for i in range(rides)]
    return Segment("transit", minutes, fare, legs, None)


def taxi(minutes, fare=15000, note=None):
    return Segment("taxi", minutes, fare, [Leg("taxi", "택시", minutes, fare, "kakao_mobility")], note)


def cond(**kw):
    return Conditions(**{"origin": "a", "destination": "b", "date": D, **kw})


def test_leave_and_arrive_formula():
    [o] = build_intercity_options([train("07:02", "09:00")], [transit(20)], [transit(25)])
    assert o.leave_at == T("06:32") and o.arrive_at == T("09:25")
    assert o.total_fare == 1250 + 42000 + 1250
    assert o.basis["board_buffer_min"] == 10


def test_bus_trunk_leg_mode():
    bus = {**train("07:00", "11:00", fare=30000, no="R1-0700"), "grade": "고속버스 우등", "kind": "bus"}
    [o] = build_intercity_options([bus], [transit(20)], [transit(25)])
    trunk = [lg for lg in o.legs if lg.source == "tago_bus"]
    assert trunk and trunk[0].mode == "bus" and trunk[0].name == "고속버스 우등 R1-0700"


def test_arrive_by_with_buffer():
    [o] = build_intercity_options([train("07:02", "09:00")], [transit(20)], [transit(25)])
    j = evaluate([o], cond(arrive_by="09:30"), [], NOW)
    assert j.passed == [] and j.excluded[0][1] == "도착 09:25 > 마감 09:20"
    [o2] = build_intercity_options([train("07:02", "08:55")], [transit(20)], [transit(25)])
    assert evaluate([o2], cond(arrive_by="09:30"), [], NOW).passed == [o2]


def test_depart_after_excluded():
    [o] = build_intercity_options([train("07:02", "09:00")], [transit(20)], [transit(25)])
    j = evaluate([o], cond(depart_after="07:00"), [], NOW)
    assert j.excluded[0][1] == "출발 06:32 < 가능 시각 07:00"


def test_budget_exceeded_and_none_fare_undetermined():
    [o] = build_intercity_options([train("07:02", "09:00", fare=66000)], [transit(20)], [transit(25)])
    j = evaluate([o], cond(arrive_by="12:00", budget=50000), [], NOW)
    assert j.excluded[0][1] == "총 68,500원 > 예산 50,000원"
    [n] = build_intercity_options([train("07:02", "09:00", fare=None)], [transit(20)], [transit(25)])
    j2 = evaluate([n], cond(arrive_by="12:00", budget=50000), [], NOW)
    assert j2.undetermined[0][1] == "운임 정보 없음 — 예산 판단 불가"


def test_calendar_overlap_excluded():
    [o] = build_intercity_options([train("07:02", "09:00")], [transit(20)], [transit(25)])
    busy = [Busy("팀 회의", T("07:00"), T("08:00"))]
    j = evaluate([o], cond(arrive_by="12:00"), busy, NOW)
    assert j.excluded[0][1] == "캘린더 '팀 회의' 07:00–08:00과 겹침"


def test_destination_event_not_excluded():
    [o] = build_intercity_options([train("11:00", "13:15")], [transit(20)], [transit(25)])
    busy = [Busy("미팅", T("14:00"), T("15:00"))]
    assert evaluate([o], cond(arrive_by="14:00"), busy, NOW).passed == [o]


def test_estimated_never_passed():
    [o] = build_intercity_options([train("07:02", "09:00")], [transit(20)], [transit(25)])
    o.estimated = True
    j = evaluate([o], cond(arrive_by="12:00"), [], NOW)
    assert j.passed == [] and j.estimated == [o]


def test_transit_none_falls_back_to_taxi():
    segs = segments_for(None, {"duration_min": 18, "taxi_fare": 14000}, "NO_DATA")
    assert [s.kind for s in segs] == ["taxi"] and segs[0].note == "대중교통 정보 없음 → 택시 기준"
    segs2 = segments_for(None, {"duration_min": 18, "taxi_fare": 14000}, "RATE_LIMITED")
    assert segs2[0].note == "대중교통 조회 한도 초과 → 택시 기준"


def test_segments_none_when_both_missing():
    [s] = segments_for(None, None, "UPSTREAM_ERROR")
    assert s.minutes is None
    [o] = build_intercity_options([train("07:02", "09:00")], [s], [transit(25)])
    j = evaluate([o], cond(arrive_by="12:00"), [], NOW)
    assert j.undetermined[0][1] == "구간 소요시간 확인 불가"


def test_segments_transit_plus_taxi_variant():
    path = {"total_min": 44, "fare": 1250, "transfers": 0, "walk_min": 8,
            "legs": [{"mode": "walk", "name": None, "min": 1}, {"mode": "bus", "name": "1002", "min": 36},
                     {"mode": "walk", "name": None, "min": 7}]}
    segs = segments_for({"paths": [path]}, {"duration_min": 22, "taxi_fare": 17700}, None)
    assert [s.kind for s in segs] == ["transit", "taxi"]
    assert segs[0].minutes == 44 and segs[0].fare == 1250


def test_overnight_option_arrival_next_day():
    [o] = build_intercity_options([train("23:40", "02:10", arr_day=D + dt.timedelta(days=1))],
                                  [transit(20)], [transit(25)])
    assert o.arrive_at == T("02:35", D + dt.timedelta(days=1))
    j = evaluate([o], cond(arrive_by="23:59"), [], NOW)
    assert j.excluded and j.excluded[0][1].startswith("도착 11-22 02:35")


def test_intracity_when_close():
    assert is_intracity(126.85, 35.15, 126.855, 35.152, same_station=False) is True
    assert is_intracity(126.79, 35.13, 126.97, 37.55, same_station=False) is False
    assert is_intracity(126.79, 35.13, 126.97, 37.55, same_station=True) is True


def test_intracity_options_from_arrive_by():
    paths = [{"total_min": 30, "fare": 1500, "transfers": 1, "walk_min": 6,
              "legs": [{"mode": "walk", "name": None, "min": 6}, {"mode": "subway", "name": "1호선", "min": 24}]}]
    opts = build_intracity_options(paths, {"duration_min": 15, "taxi_fare": 9000}, cond(arrive_by="10:00"))
    assert {o.legs[1].mode if len(o.legs) > 1 else o.legs[0].mode for o in opts} == {"subway", "taxi"}
    sub = next(o for o in opts if o.total_fare == 1500)
    assert sub.arrive_at == T("09:50") and sub.leave_at == T("09:20")


def _opt(oid, fare, minutes, transfers):
    legs = [Leg("bus", str(i), 10, None, "x") for i in range(transfers + 1)]
    return Option(oid, "intercity", legs, T("08:00"), T("08:00") + dt.timedelta(minutes=minutes), fare)


def test_rank_max_three_unique():
    opts = [_opt("a", 30000, 200, 3), _opt("b", 50000, 120, 2), _opt("c", 45000, 180, 0), _opt("d", 31000, 210, 3)]
    r = rank(opts, "cheapest")
    assert [o.id for o in r] == ["a", "b", "c"]
    assert r[0].basis["label"] == "최저가" and r[1].basis["label"] == "최단 소요" and r[2].basis["label"] == "환승 최소"
    assert len(rank(opts[:1], "fastest")) == 1


def test_rain_warning_rule():
    o = Option("x", "intercity", [Leg("walk", None, 12, None, "odsay"), Leg("bus", "1", 20, None, "odsay")],
               T("08:00"), T("09:00"), 1000)
    [w] = apply_warnings([o], {"origin": {"pop": 70}}, [], [])
    assert len(w.warnings) == 1 and "70%" in w.warnings[0]
    o2 = Option("y", "intercity", list(o.legs), T("08:00"), T("09:00"), 1000)
    assert apply_warnings([o2], {"origin": {"pop": 50}}, [], [])[0].warnings == []


def test_rain_avoid_blocks():
    o = Option("x", "intercity", [Leg("walk", None, 12, None, "odsay")], T("08:00"), T("09:00"), 1000)
    [w] = apply_warnings([o], {"origin": {"pop": 70}}, [], ["비"])
    j = evaluate([w], cond(arrive_by="12:00"), [], NOW)
    assert j.excluded[0][1] == "강수확률 70% 시간대 도보 12분 (비 회피 요청)"


def test_road_event_warning_only_for_road_legs():
    ev = [{"type": "공사", "description": "국도22호선 시설물보수작업"}]
    road = Option("r", "intercity", [Leg("taxi", "택시", 20, 15000, "k")], T("08:00"), T("09:00"), 15000)
    rail = Option("s", "intercity", [Leg("walk", None, 5, None, "o")], T("08:00"), T("09:00"), 1000)
    out = apply_warnings([road, rail], {}, ev, [])
    assert "공사" in out[0].warnings[0] and out[1].warnings == []
