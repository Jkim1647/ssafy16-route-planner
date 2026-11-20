"""상호 점검(2026-11-20 13:47) 지적 사항 재현 테스트."""
import datetime as dt

from backend.agent.conditions import Conditions
from backend.agent.graph import Changes
from backend.agent.judge import build_intercity_options, build_intracity_options, evaluate, exclusion_kind
from backend.agent.recheck import recheck_plan
from backend.tools.base import fail
from backend.tools.budget import default_budget
from tests.agent.test_judge import T, taxi, train, transit
from tests.agent.test_recheck import NOW as RNOW, FakeCal, kinds, plan, tools  # noqa: F401

D = dt.date(2026, 11, 21)


# P1-1. 이미 출발한 후보: S3는 11-20 11:59 실행에서 '전날(11-20) 08:13 출발'이 추천됐다
def test_prev_day_option_already_departed_is_excluded():
    c = Conditions(origin="a", destination="b", date=D, arrive_by="09:50")
    prev = D - dt.timedelta(days=1)
    gone, later = build_intercity_options(
        [{**train("08:30", "13:00"), "dep_at": T("08:30", prev).isoformat(), "arr_at": T("13:00", prev).isoformat(), "train_no": "1"},
         {**train("18:00", "21:00"), "dep_at": T("18:00", prev).isoformat(), "arr_at": T("21:00", prev).isoformat(), "train_no": "2"}],
        [transit(20)], [transit(10)])
    j = evaluate([gone, later], c, [], dt.datetime(2026, 11, 20, 11, 59))
    assert j.passed == [later]
    assert [o for o, _ in j.excluded] == [gone]
    assert exclusion_kind(j.excluded[0][1]) == "출발 시각"


# P1-2. 자정을 넘기는 시내 이동: 22:00 이후 출발, 다음 날 02:30까지 도착, 20분 경로
def test_intracity_overnight_window_builds_next_day_times():
    c = Conditions(origin="a", destination="b", date=D, depart_after="22:00", arrive_by="02:30")
    paths = [{"total_min": 20, "fare": 1500, "legs": [{"mode": "walk", "name": None, "min": 5},
                                                      {"mode": "bus", "name": "심야", "min": 15}]}]
    [o] = build_intracity_options(paths, None, c)
    nxt = D + dt.timedelta(days=1)
    assert o.arrive_at == T("02:20", nxt) and o.leave_at == T("02:00", nxt)
    assert evaluate([o], c, [], dt.datetime(2026, 11, 20, 12, 0)).passed == [o]


# P1-3. 허용 교통수단·회피 수단이 판정에 반영된다
def test_analyze_schema_extracts_modes():
    assert "modes" in Changes.model_fields


def test_avoid_taxi_excludes_taxi_options():
    c = Conditions(origin="a", destination="b", date=D, arrive_by="14:00", avoid=["택시"])
    by_transit, by_taxi = build_intercity_options([train("10:00", "12:00")], [transit(30), taxi(15)], [transit(20)])
    j = evaluate([by_transit, by_taxi], c, [], dt.datetime(2026, 11, 20, 12, 0))
    assert j.passed == [by_transit]
    assert exclusion_kind(j.excluded[0][1]) == "수단"


def test_train_only_excludes_express_bus():
    c = Conditions(origin="a", destination="b", date=D, arrive_by="14:00", modes=["train"])
    bus = {**train("10:00", "12:00", no="B1"), "kind": "bus", "grade": "우등"}
    by_train, by_bus = build_intercity_options([train("10:00", "12:00"), bus], [transit(30)], [transit(20)])
    j = evaluate([by_train, by_bus], c, [], dt.datetime(2026, 11, 20, 12, 0))
    assert j.passed == [by_train]
    assert "고속버스" in j.excluded[0][1]


def test_express_bus_only_excludes_train():
    c = Conditions(origin="a", destination="b", date=D, arrive_by="14:00", modes=["express_bus"])
    bus = {**train("10:00", "12:00", no="B1"), "kind": "bus", "grade": "우등"}
    by_train, by_bus = build_intercity_options([train("10:00", "12:00"), bus], [transit(30)], [transit(20)])
    assert evaluate([by_train, by_bus], c, [], dt.datetime(2026, 11, 20, 12, 0)).passed == [by_bus]


# P2. 다시 확인: 확인하지 못한 항목이 있으면 '그대로 가도 돼요'(ok)가 아니다
def test_recheck_train_lookup_failure_is_not_ok(tools, monkeypatch):
    from backend.tools import registry
    registry._TOOLS["search_trains"].func = lambda **kw: fail("UPSTREAM_ERROR", "x")
    r = recheck_plan(plan(), calendar=FakeCal(), now=RNOW)
    assert r["status"] == "partial" and "train" in kinds(r, "unknown")


def test_recheck_calendar_failure_is_not_ok(tools):
    class Broken:
        def get_free_busy(self, day, days=1):
            raise RuntimeError("down")
    r = recheck_plan(plan(), calendar=Broken(), now=RNOW)
    assert r["status"] == "partial" and "calendar" in kinds(r, "unknown")


def test_recheck_queries_timetable_without_cache(tools):
    from backend.tools import registry
    seen = []
    orig = registry._TOOLS["search_trains"].func

    def spy(**kw):
        seen.append(getattr(default_budget(), "_bypass", False))
        return orig(**kw)
    registry._TOOLS["search_trains"].func = spy
    recheck_plan(plan(), calendar=FakeCal(), now=RNOW)
    assert seen == [True]


# P1-1 후속: 전날 출발 카드는 응답 문장에서도 날짜를 밝힌다(시각만 보면 요청일 출발로 읽힌다)
def test_reply_notes_cards_leaving_on_another_day():
    from backend.agent.graph import _day_note
    cards = [{"index": 1, "date": "2026-11-20"}, {"index": 2, "date": "2026-11-21"}, {"index": 3, "date": "2026-11-20"}]
    assert _day_note(cards, D) == "※ 1·3번은 요청일 전날(11-20) 출발이에요."
    assert _day_note([{"index": 1, "date": "2026-11-21"}], D) is None
