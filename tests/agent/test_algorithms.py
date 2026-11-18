"""경로 선택 알고리즘: 파레토 최적(지배 후보 제외), 가장 늦게 출발, 지각 위험 점수."""
import datetime as dt

from backend.agent.conditions import Conditions
from backend.agent.judge import Leg, Option, pareto_front, rank, risk_for
from tests.agent.test_graph import DAY, A, Reply, env  # noqa: F401

D = dt.date(2026, 11, 21)


def opt(oid, leave, arrive, fare, rides=1):
    legs = [Leg("bus", f"버스{i}", 10, None, "odsay") for i in range(rides)]
    t = lambda hm: dt.datetime.combine(D, dt.time.fromisoformat(hm))  # noqa: E731
    return Option(oid, "intercity", legs, t(leave), t(arrive), fare)


def test_pareto_removes_options_worse_in_every_way():
    a = opt("a", "09:00", "12:00", 40000)
    b = opt("b", "08:30", "12:30", 45000)          # a보다 일찍 나가고 늦게 도착하고 비싸다 → 지배됨
    c = opt("c", "08:00", "11:00", 30000)          # 더 일찍 나가지만 더 일찍 도착·더 쌈 → 남음
    d = opt("d", "09:00", "12:00", 40000, rides=3)  # a와 같고 환승만 많음 → 지배됨
    assert [o.id for o in pareto_front([a, b, c, d])] == ["a", "c"]


def test_pareto_keeps_unknown_fare_comparable_by_time_only():
    a = opt("a", "09:00", "12:00", None)
    b = opt("b", "08:00", "13:00", 30000)
    assert {o.id for o in pareto_front([a, b])} == {"a", "b"}


def test_rank_adds_latest_departure_card():
    early_cheap = opt("cheap", "06:00", "10:00", 30000)
    fast = opt("fast", "08:00", "10:30", 50000)
    late = opt("late", "10:00", "13:20", 45000, rides=2)
    picked = rank(pareto_front([early_cheap, fast, late]), "cheapest")
    labels = {o.id: o.basis["label"] for o in picked}
    assert labels["late"] == "늦게 출발" and labels["cheap"] == "최저가"


def test_risk_levels_from_slack_and_transfers():
    c = Conditions(origin="a", destination="b", date=D, arrive_by="14:00")
    roomy = risk_for(opt("x", "09:00", "13:00", 1), c)
    assert roomy == {"level": "넉넉", "absorb_min": 60, "text": "60분까지 늦어져도 제시간 도착"}
    assert risk_for(opt("y", "09:00", "13:40", 1), c)["level"] == "보통"
    assert risk_for(opt("w", "06:00", "07:36", 1), c)["text"] == "6시간 24분까지 늦어져도 제시간 도착"
    tight = risk_for(opt("z", "09:00", "13:50", 1, rides=5), c)
    assert tight["level"] == "빠듯" and "환승 4회" in tight["text"]


def test_risk_none_without_deadline():
    assert risk_for(opt("x", "09:00", "13:00", 1), Conditions(origin="a", destination="b", date=D,
                                                               depart_after="08:00")) is None


def test_cards_carry_risk_and_decision_counts_dominated(env):
    world, llm, make, _ = env
    llm.responses = [A("plan_trip", origin="첨단동", destination="강남역", date=DAY, arrive_by="14:00"), Reply(text="ok")]
    res = make()("x")
    assert all(c["risk"]["level"] in ("넉넉", "보통", "빠듯") for c in res.cards)
    assert "dominated" in res.decision
