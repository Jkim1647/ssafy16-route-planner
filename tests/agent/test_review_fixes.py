"""최종 리뷰 지적 사항(Critical·Important) 재현 테스트."""
import datetime as dt

from backend.agent.conditions import Conditions, missing_fields
from backend.agent.graph import AnalyzeOut, Changes, numbers_ok
from backend.agent.judge import build_intercity_options, evaluate
from backend.tools import registry
from backend.tools.base import Tool, ok
from tests.agent.test_graph import DAY, TRIP, A, Reply, env, tr  # noqa: F401
from tests.agent.test_judge import T, transit, train
from tests.helpers import Resp, load, route_get

CARD = {"leave_at": "09:20", "arrive_at": "12:20", "total_fare": 45000,
        "legs": [{"fare": 42000}], "basis": {"train_dep": "10:00", "train_arr": "11:50"}}


# 1. Critical — 숫자 가드
def test_numbers_guard_catches_time_followed_by_hangul():
    assert numbers_ok("15:30에 출발해요", [CARD]) is False
    assert numbers_ok("09:20에 출발해 12:20까지 도착, 45,000원", [CARD]) is True


def test_numbers_guard_rejects_unverifiable_korean_numbers():
    assert numbers_ok("오후 3시 도착", [CARD]) is False
    assert numbers_ok("약 9만원이에요", [CARD]) is False


# 2. 재계획 때 이미 조회한 대중교통 구간은 상한에 세지 않고 재사용
def test_replan_reuses_transit_without_run_cap(env):
    world, llm, make, _ = env
    world.trains = [tr("13:00", "15:00")]
    llm.responses = [A("plan_trip", **TRIP)]
    res = make()("x")
    after_replan = False
    reused = 0
    for e in res.events:
        if e["type"] == "replan":
            after_replan = True
        if after_replan and e["type"] == "tool_result" and e["payload"]["tool"] == "get_transit_route":
            reused += e["payload"]["cached"]
    assert reused >= 1


# 3. 결과 없는 검색 뒤 "1번 저장"은 이전 여정 카드를 저장하지 않음
def test_save_after_no_option_does_not_use_stale_cards(env):
    world, llm, make, db = env
    from backend.db.repositories import PlanRepo
    turn = make()
    llm.responses = [A("plan_trip", **TRIP), Reply(text="ok")]
    assert turn("x").cards
    world.trains = [tr("13:00", "15:00")]
    llm.responses = [A("modify", arrive_by="12:00")]
    assert not turn("12시까지로").cards
    llm.responses = [AnalyzeOut(intent="save_plan", intent_reason="저장", changes=Changes(), option_ref=1)]
    res = turn("1번 저장")
    assert PlanRepo(db).list() == [] and res.status == "clarify"


# 4. 자정을 넘기는 시간 범위
def test_overnight_window_deadline_next_day():
    c = Conditions(origin="a", destination="b", date=dt.date(2026, 11, 21), depart_after="22:00", arrive_by="02:30")
    [o] = build_intercity_options([train("23:00", "01:30", arr_day=dt.date(2026, 11, 22))], [transit(20)], [transit(10)])
    j = evaluate([o], c, [], dt.datetime(2026, 11, 18, 11, 0))
    assert j.passed == [o]


def test_overnight_window_today_not_past_deadline():
    now = dt.datetime(2026, 11, 18, 21, 0)
    c = Conditions(origin="a", destination="b", date=now.date(), depart_after="22:00", arrive_by="02:00")
    assert missing_fields(c, now) == []


def test_excluded_reason_shows_date_when_day_differs():
    c = Conditions(origin="a", destination="b", date=dt.date(2026, 11, 21), arrive_by="23:00")
    [o] = build_intercity_options([train("22:00", "01:30", arr_day=dt.date(2026, 11, 22))], [transit(20)], [transit(10)])
    reason = evaluate([o], c, [], dt.datetime(2026, 11, 18, 11, 0)).excluded[0][1]
    assert "11-22 01:40" in reason


# 5. 날짜 없는 사실 질문이 죽지 않음 / 7. 사실 질문은 계획에 있는 Tool만 부름
def test_fact_query_without_date_uses_today_and_stays_in_plan(env):
    from backend.events.anomaly import judge_run
    world, llm, make, _ = env
    world.trains = [{**tr("12:00", "13:50"), "dep_at": "2026-11-18T12:00", "arr_at": "2026-11-18T13:50"},
                    {**tr("15:00", "16:50"), "dep_at": "2026-11-18T15:00", "arr_at": "2026-11-18T16:50"}]
    llm.responses = [A("fact_query", origin="첨단동", destination="강남역", arrive_by="14:00")]
    res = make()("첨단동에서 강남역 열차 몇 시?")
    assert res.status == "done" and "12:00" in res.reply and "15:00" not in res.reply
    assert judge_run(res.events, 3)["verdict"] == "ok"
    tools = {e["payload"]["tool"] for e in res.events if e["type"] == "tool_call"}
    assert tools <= {"search_places", "find_stations", "search_trains"}


# 6. 조건이 덜 채워진 뒤 규정 질문이 죽지 않음
def test_terms_query_after_partial_conditions(env, monkeypatch):
    world, llm, make, _ = env
    tools = dict(registry._TOOLS)
    tools["search_terms"] = Tool("search_terms", "d", {"type": "object", "properties": {}}, lambda question, k=4: ok(
        {"chunks": [{"text": "위약금 5%", "source": "k.md", "title": "약관", "page": 1, "distance": 0.1}]}), "local")
    monkeypatch.setattr(registry, "_TOOLS", tools)
    turn = make()
    llm.responses = [A("plan_trip", destination="강남역", arrive_by="14:00")]
    turn("강남역 2시까지")
    llm.responses = [A("terms_query", "규정")]
    res = turn("KTX 환불 위약금?")
    assert res.status == "done" and "약관" in res.reply


# 8. HTTP 200 오류 응답(resultCode)은 캐시하지 않음
def test_tago_auth_error_not_cached(monkeypatch):
    from backend.tools.tago_train import search_trains
    bodies = [{"response": {"header": {"resultCode": "30", "resultMsg": "SERVICE_KEY_IS_NOT_REGISTERED_ERROR"}}},
              load("tago_train_plus1")]
    route_get(monkeypatch, [(lambda u, p: "TrainInfo" in u, lambda u, p: Resp(bodies.pop(0)))])
    assert search_trains("A", "B", "2026-11-19")["error"]["code"] == "INVALID_KEY"
    assert search_trains("A", "B", "2026-11-19")["ok"]  # 키를 고친 뒤 바로 다시 조회됨


def test_kma_error_not_cached(monkeypatch):
    from backend.tools import kma_weather
    monkeypatch.setattr(kma_weather, "now", lambda: dt.datetime(2026, 11, 18, 11, 34))
    bodies = [{"response": {"header": {"resultCode": "22", "resultMsg": "LIMITED"}}}, load("kma")]
    route_get(monkeypatch, [(lambda u, p: "VilageFcst" in u, lambda u, p: Resp(bodies.pop(0)))])
    assert kma_weather.get_weather(35.13, 126.79, "2026-11-19T15:00")["error"]["code"] == "UPSTREAM_ERROR"
    assert kma_weather.get_weather(35.13, 126.79, "2026-11-19T15:00")["ok"]


# 실제 확인에서 발견: 오늘 열차를 물으면 이미 떠난 열차는 빼야 한다(NOW = 11:00)
def test_fact_query_today_hides_departed_trains(env):
    world, llm, make, _ = env
    world.trains = [{**tr("10:00", "11:50"), "dep_at": "2026-11-18T10:00", "arr_at": "2026-11-18T11:50"},
                    {**tr("15:00", "16:50"), "dep_at": "2026-11-18T15:00", "arr_at": "2026-11-18T16:50"}]
    llm.responses = [A("fact_query", origin="첨단동", destination="강남역")]
    res = make()("첨단동에서 강남역 열차 몇 시?")
    assert "15:00" in res.reply and "10:00" not in res.reply
