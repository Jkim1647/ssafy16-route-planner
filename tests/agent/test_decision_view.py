"""차별점 표시: 경로 카드의 판단 결과(마감 여유·예산 남은 금액·일정 겹침)와 판단 요약."""
import datetime as dt

from backend.agent.conditions import Conditions
from backend.agent.judge import Busy, build_intercity_options, checks_for, exclusion_kind
from backend.tools import registry
from backend.tools.base import Tool, ok
from tests.agent.test_graph import DAY, A, Reply, env, tr  # noqa: F401
from tests.agent.test_judge import transit, train

D = dt.date(2026, 11, 21)


def opt():  # 10:00 열차 → 09:30 출발, 11:40+10 → 11:50 도착(역까지 20분, 목적지까지 10분)
    [o] = build_intercity_options([train("10:00", "11:30")], [transit(20)], [transit(10)])
    return o


def kinds(checks):
    return [c["kind"] for c in checks]


def test_checks_show_deadline_slack_and_budget_left():
    o = opt()
    c = Conditions(origin="a", destination="b", date=D, arrive_by="14:00", budget=60000)
    checks = checks_for(o, c, busy=[], calendar_checked=False)
    assert kinds(checks) == ["deadline", "budget"]
    assert o.arrive_at == dt.datetime(2026, 11, 21, 11, 40)  # 11:30 도착 + 목적지까지 10분
    assert checks[0]["text"] == "마감 14:00까지 여유 2시간 20분"
    assert checks[1]["text"] == f"예산 60,000원 중 {60000 - o.total_fare:,}원 남음"


def test_checks_calendar_and_depart_after():
    o = opt()
    c = Conditions(origin="a", destination="b", date=D, depart_after="08:00")
    busy = [Busy("회의", dt.datetime(2026, 11, 21, 7, 0), dt.datetime(2026, 11, 21, 8, 0)),
            Busy("점심", dt.datetime(2026, 11, 21, 12, 30), dt.datetime(2026, 11, 21, 13, 30))]
    checks = checks_for(o, c, busy=busy, calendar_checked=True)
    assert kinds(checks) == ["depart", "calendar"]
    assert checks[0]["text"] == "08:00 이후 출발"
    assert checks[1]["text"] == "그날 일정 2건과 안 겹침"


def test_checks_calendar_empty_day():
    checks = checks_for(opt(), Conditions(origin="a", destination="b", date=D, arrive_by="14:00"), [], True)
    assert checks[-1] == {"kind": "calendar", "text": "그날 일정 없음"}


def test_exclusion_kinds():
    assert exclusion_kind("도착 13:25 > 마감 13:50") == "마감"
    assert exclusion_kind("총 50,000원 > 예산 45,000원") == "예산"
    assert exclusion_kind("캘린더 '회의' 07:00–08:00과 겹침") == "일정"
    assert exclusion_kind("출발 05:18 < 가능 시각 10:00") == "출발 시각"
    assert exclusion_kind("강수확률 70% 시간대 도보 12분 (비 회피 요청)") == "날씨"


def test_cards_and_decision_summary_from_graph(env, monkeypatch):
    world, llm, make, _ = env
    tools = dict(registry._TOOLS)
    tools["get_free_busy"] = Tool("get_free_busy", "d", {"type": "object", "properties": {}},
                                  lambda date, days=1: ok({"backend": "local", "busy": []}), "local")
    monkeypatch.setattr(registry, "_TOOLS", tools)
    llm.responses = [A("plan_trip", origin="첨단동", destination="강남역", date=DAY, arrive_by="14:00", budget=45000),
                     Reply(text="ok")]
    res = make()("x")
    assert res.cards and kinds(res.cards[0]["checks"]) == ["deadline", "budget", "calendar"]
    d = res.decision
    assert d["checked"] >= d["passed"] >= 1
    assert d["excluded_by"].get("예산", 0) >= 1  # 50,000원 열차는 예산 초과
