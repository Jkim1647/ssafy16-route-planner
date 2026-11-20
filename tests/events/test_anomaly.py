from backend.db.database import init_db
from backend.db.repositories import AnomalyRepo, EventRepo
from backend.events.anomaly import Diagnosis, diagnose, evaluate_and_store, judge_run
from tests.fakes import FakeLLM


def ev(seq, type_, **payload):
    return {"session_id": "s", "run_id": "r", "seq": seq, "ts": "t", "agent": "main", "type": type_,
            "node": None, "payload": payload, "duration_ms": 1}


PLAN = ev(1, "plan_tasks", tasks=[{"id": "t1", "tool": "search_places"}, {"id": "t5", "tool": "search_trains"}])


def call(seq, tool, task="t1", cached=False, retry_of=None, **args):
    p = {"task_id": task, "tool": tool, "args": args}
    if retry_of:
        p["retry_of"] = retry_of
    return [ev(seq, "tool_call", **p), ev(seq + 1, "tool_result", task_id=task, tool=tool, ok=True, cached=cached)]


def rules(result):
    return {f["rule"] for f in result["findings"]}


def test_normal_run_ok():
    events = [PLAN, *call(2, "search_places", q="a"), *call(4, "search_places", q="b")]
    assert judge_run(events, 3) == {"verdict": "ok", "findings": []}


def test_duplicate_detected():
    events = [PLAN, *call(2, "search_places", q="a"), *call(4, "search_places", q="a")]
    r = judge_run(events, 3)
    assert r["verdict"] == "warn" and rules(r) == {"DUPLICATE_CALL"}
    assert r["findings"][0]["event_seqs"] == [2, 4]


def test_cached_not_duplicate():
    events = [PLAN, *call(2, "search_places", q="a"), *call(4, "search_places", cached=True, q="a")]
    assert judge_run(events, 3)["verdict"] == "ok"


def test_unplanned_detected():
    events = [PLAN, *call(2, "get_weather", task="t10", lat=1)]
    r = judge_run(events, 3)
    assert rules(r) == {"UNPLANNED_CALL"} and "get_weather" in r["findings"][0]["detail"]


def test_task_tool_mismatch_is_unplanned():
    events = [PLAN, *call(2, "search_trains", task="t1", a=1)]
    assert rules(judge_run(events, 3)) == {"UNPLANNED_CALL"}


def test_retry_not_unplanned_or_duplicate():
    events = [PLAN, *call(2, "search_places", q="a"), *call(4, "search_places", retry_of=2, q="a")]
    assert judge_run(events, 3)["verdict"] == "ok"


def test_excessive_replan():
    events = [PLAN, *call(2, "search_places", q="a"), ev(4, "replan", count=1), ev(5, "replan", count=2)]
    r = judge_run(events, 3)
    assert rules(r) == {"EXCESSIVE_REPLAN"}


def test_no_evidence_undetermined():
    assert judge_run([ev(1, "run_start"), ev(2, "run_end")], 3)["verdict"] == "undetermined"


def test_replanned_plans_accumulate_tasks():
    plan2 = ev(6, "plan_tasks", tasks=[{"id": "t13", "tool": "find_terminals"}])
    events = [PLAN, *call(2, "search_places", q="a"), ev(4, "replan", count=1), plan2, *call(7, "find_terminals", task="t13", x=1)]
    assert "UNPLANNED_CALL" not in rules(judge_run(events, 3))


def test_diagnose_called_only_on_warn(tmp_path):
    db = str(tmp_path / "a.db")
    init_db(db)
    repo = EventRepo(db)
    for e in [PLAN, *call(2, "search_places", q="a"), *call(4, "search_places", q="b")]:
        repo.append(e)
    llm = FakeLLM()
    out = evaluate_and_store("r", repo, AnomalyRepo(db), lambda: llm, 3)
    assert out["verdict"] == "ok" and llm.prompts == []
    assert AnomalyRepo(db).get("r")["diagnosis"] is None


def test_diagnosis_stored_separately(tmp_path):
    db = str(tmp_path / "a.db")
    init_db(db)
    repo = EventRepo(db)
    for e in [PLAN, *call(2, "search_places", q="a"), *call(4, "search_places", q="a")]:
        repo.append(e)
    llm = FakeLLM([Diagnosis(text="실행기가 장소 검색 결과를 재사용하지 않았다. 캐시 키를 확인하라.")])
    out = evaluate_and_store("r", repo, AnomalyRepo(db), lambda: llm, 3)
    saved = AnomalyRepo(db).get("r")
    assert out["verdict"] == "warn" and len(saved["findings"]) == 1
    assert saved["diagnosis"].startswith("실행기가")


def test_diagnosis_failure_keeps_verdict(tmp_path):
    db = str(tmp_path / "a.db")
    init_db(db)
    repo = EventRepo(db)
    for e in [PLAN, *call(2, "search_places", q="a"), *call(4, "search_places", q="a")]:
        repo.append(e)
    llm = FakeLLM([RuntimeError("gms down")])
    evaluate_and_store("r", repo, AnomalyRepo(db), lambda: llm, 3)
    saved = AnomalyRepo(db).get("r")
    assert saved["verdict"] == "warn" and saved["diagnosis"] is None


def test_diagnose_returns_none_on_error():
    assert diagnose(FakeLLM([RuntimeError("x")]), [], []) is None


def test_diagnose_sends_a_user_turn():
    # Claude는 system 메시지만 있는 요청을 400으로 거절한다(2026-11-20 시나리오 재실행: 진단이 매번 None)
    llm = FakeLLM([Diagnosis(text="같은 인자로 두 번 호출")])
    assert diagnose(llm, [], [{"rule": "DUPLICATE"}]) == "같은 인자로 두 번 호출"
    assert any(m[0] != "system" for m in llm.prompts[0])
