"""대표 시나리오(명세 4.7) + 검증용 실행(4.3·4.6)을 실제 API·GMS로 돌려 docs/evidence/에 기록한다.

사용: python scripts/run_scenarios.py [출력 폴더]  — 기본 docs/evidence. 기존 증거를 덮지 않으려면 다른 폴더를 준다.
"""
import datetime as dt
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
EVID = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "docs" / "evidence"
EVID.mkdir(parents=True, exist_ok=True)

from backend.settings import get_settings  # noqa: E402

get_settings()
os.environ.setdefault("CALENDAR_BACKEND", "local")
from backend.calendar.local import LocalCalendar  # noqa: E402
from backend.container import Container  # noqa: E402
from backend.events.anomaly import judge_run  # noqa: E402

SAT = dt.date(2026, 11, 21)
TRIP = "토요일 오후 2시까지 광주 첨단동에서 서울 강남역 가야 해. 6만원 이하로"


def container(**env):
    for k, v in env.items():
        os.environ[k] = v
    return Container.build()


def summarize(sid, title, expected, res, c):
    tools = [e["payload"]["tool"] for e in res.events if e["type"] == "tool_call"]
    anomaly = c.anomalies.get(res.run_id) if c.settings.LOGGING_ENABLED else None
    row = {"id": sid, "title": title, "expected": expected, "status": res.status, "intent": res.intent,
           "replans": res.replan_count, "llm_calls": res.llm_calls, "tool_calls": len(tools),
           "tools": sorted(set(tools)), "cards": [(x.get("label"), x.get("leave_at"), x.get("arrive_at"), x.get("total_fare"))
                                                 for x in res.cards if x.get("leave_at")],
           "excluded_sample": [x["reason"] for x in res.excluded[:3]], "warnings": res.warnings,
           "reply": res.reply, "run_id": res.run_id, "session_id": res.session_id,
           "anomaly": anomaly and {"verdict": anomaly["verdict"], "rules": [f["rule"] for f in anomaly["findings"]],
                                   "diagnosis": anomaly["diagnosis"]}}
    (EVID / f"{sid}.json").write_text(json.dumps({"summary": row, "result": res.model_dump()}, ensure_ascii=False,
                                                 indent=1, default=str), encoding="utf-8")
    print(f"[{sid}] {res.status} replans={res.replan_count} llm={res.llm_calls} tools={len(tools)} cards={len(row['cards'])}")
    return row


rows = []
c = container(AGENT_MODE="single", LOGGING_ENABLED="true", DEBUG_FORCE="", ODSAY_API_KEY=os.environ.get("ODSAY_API_KEY", ""))
r1 = c.chat(None, TRIP)
rows.append(summarize("S1", "제약을 한 번에 충족", "추천 카드 1개 이상, 재계획 0", r1, c))
rows.append(summarize("S7", "후속 요청(조건 하나만 변경)", "날짜·도착지·마감 유지, 출발 하한만 추가",
                      c.chat(r1.session_id, "같은 조건에서 출발은 오전 10시 이후로 해줘"), c))
rows.append(summarize("S2", "재계획 필요", "재계획 1회 이상 후 통과",
                      c.chat(None, "토요일 오전 7시 이후에 출발해서 오전 10시 30분까지 광주 첨단동에서 서울 강남역 가야 해"), c))
rows.append(summarize("S3", "재계획 상한 도달", "재계획 3회 후 멈추고 조건 조정 질문",
                      c.chat(None, "토요일 오전 10시까지 광주 첨단동에서 서울 강남역 가야 해. 4만3천원 이하로"), c))
rows.append(summarize("S5", "Tool이 필요 없는 요청", "Tool 호출 0, 사용법 안내",
                      c.chat(None, "안녕! 이거 어떻게 쓰는 거야?"), c))
rows.append(summarize("S6", "조건 부족 → 되묻기", "Tool 호출 0, 출발지·날짜 질문",
                      c.chat(None, "2시까지 서울 가야 해"), c))
rows.append(summarize("S8", "규정 질문(RAG)", "약관 근거 문단과 출처",
                      c.chat(None, "KTX 출발 30분 전에 승차권 반환하면 위약금 얼마야?"), c))

cal = LocalCalendar(c.settings.DB_PATH)
cal.add("팀 회의(검증용)", dt.datetime.combine(SAT, dt.time(7, 0)), dt.datetime.combine(SAT, dt.time(8, 0)))
rows.append(summarize("S9", "캘린더 일정 반영", "07:00–08:00 회의와 겹치는 이동은 제외",
                      c.chat(None, TRIP), c))

# S10: 같은 날 겹치는 계획 저장 → 저장은 되고 겹침 알림
from backend.schemas import PlanIn  # noqa: E402

cards = [x for x in r1.cards if x.get("leave_at")]
saved = []
for x in cards[:2]:
    res = c.plans.create(PlanIn(title="첨단동 → 강남역(검증)", date=dt.date.fromisoformat(x["date"]), leave_at=x["leave_at"],
                                arrive_at=x["arrive_at"], origin_name="광주 첨단동", destination_name="서울 강남역",
                                legs=x["legs"], total_fare=x["total_fare"]))
    saved.append({"plan_id": res.plan.id, "overlaps": [p.id for p in res.overlaps]})
(EVID / "S10.json").write_text(json.dumps({"saved": saved}, ensure_ascii=False, indent=1), encoding="utf-8")
print("[S10]", saved)

# S4: Tool 하나 실패(ODsay 키 제거) → 택시 기준 대체, 나머지 진행
key = os.environ.pop("ODSAY_API_KEY", "")
c4 = container(ODSAY_API_KEY="")
rows.append(summarize("S4", "Tool 하나 실패(ODsay 키 없음)", "택시 기준으로 대체해 응답, 재계획 없음",
                      c4.chat(None, "토요일 오후 3시까지 광주 첨단동에서 서울 강남역 가야 해"), c4))
os.environ["ODSAY_API_KEY"] = key

# 4.3: 로깅 Agent 없이 실행
c5 = container(LOGGING_ENABLED="false")
r = c5.chat("no-logger-check", TRIP)
(EVID / "no_logger.json").write_text(json.dumps({"status": r.status, "cards": len(r.cards),
                                                 "stored_events": len(c5.events.get_session("no-logger-check"))},
                                                ensure_ascii=False), encoding="utf-8")
print("[no_logger]", r.status, len(r.cards), "stored", len(c5.events.get_session("no-logger-check")))

# 4.6 F3020: 이상 실행 3종
for mode in ("duplicate", "unplanned", "replan"):
    cx = container(LOGGING_ENABLED="true", DEBUG_FORCE=mode)
    rows.append(summarize(f"F3020-{mode}", f"이상 징후 재현: {mode}", "warn + LLM 진단", cx.chat(None, TRIP), cx))
os.environ["DEBUG_FORCE"] = ""

# 4.6 F3021: Planner·Worker 모드 대표 요청
cpw = container(AGENT_MODE="planner_worker", WORKER_LLM="on", LOGGING_ENABLED="true")
rows.append(summarize("F3021-PW", "Planner·Worker 모드", "planner/worker/logger 역할 이벤트, 정상 경로 Worker LLM 0",
                      cpw.chat(None, TRIP), cpw))
os.environ["AGENT_MODE"] = "single"

(EVID / "scenarios.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
print("done")
