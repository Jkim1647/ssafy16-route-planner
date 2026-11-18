"""구조 비교 실험(F3021): 같은 요청을 세 조건으로 실행해 재계획·LLM 호출·응답 시간을 비교한다.

조건: single / planner_worker(WORKER_LLM=off) / planner_worker(WORKER_LLM=on)
실제 API·GMS를 쓰되 외부 API는 캐시를 거친다. 결과는 docs/비교결과.md.
사용: python scripts/compare_modes.py
"""
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.settings import get_settings  # noqa: E402

get_settings()
os.environ["CALENDAR_BACKEND"] = "local"  # 실제 일정에 따라 결과가 달라지지 않게(재현 가능한 실험)
import backend.tools.catalog_all  # noqa: E402,F401
from backend.agent.graph import Deps, build_graph  # noqa: E402
from backend.agent.llm import get_llm  # noqa: E402
from backend.agent.service import run_turn  # noqa: E402
from backend.db.database import init_db  # noqa: E402
from backend.db.repositories import EventRepo, PlanRepo, RunRepo  # noqa: E402
from backend.events.bus import build_bus  # noqa: E402

REQUESTS = [
    ("S1 충족", "토요일 오후 2시까지 광주 첨단동에서 서울 강남역 가야 해. 6만원 이하로"),
    ("S2 재계획", "토요일 오전 7시 이후에 출발해서 오전 10시 30분까지 광주 첨단동에서 서울 강남역 가야 해"),
    ("S3 상한", "토요일 오전 10시까지 광주 첨단동에서 서울 강남역 가야 해. 4만3천원 이하로"),
    ("S7 조건 변경", "토요일 오후 2시까지 광주 첨단동에서 서울 강남역, 출발은 오전 10시 이후로"),
]
CONDITIONS = [("single", "single", "on"), ("PW·Worker LLM off", "planner_worker", "off"),
              ("PW·Worker LLM on", "planner_worker", "on")]


def run_one(mode: str, worker_llm: str, msg: str) -> dict:
    os.environ["AGENT_MODE"], os.environ["WORKER_LLM"] = mode, worker_llm
    s = get_settings()
    init_db(s.DB_PATH)
    deps = Deps(llm_factory=get_llm, plan_repo=PlanRepo(s.DB_PATH), settings=s)
    g = build_graph(deps)
    t0 = time.perf_counter()
    res = run_turn(g, deps, build_bus(EventRepo(s.DB_PATH)), RunRepo(s.DB_PATH), None, msg)
    ms = int((time.perf_counter() - t0) * 1000)
    src = {}
    for e in res.events:
        if e["type"] == "replan":
            src[e["payload"].get("source", "no_option")] = src.get(e["payload"].get("source", "no_option"), 0) + 1
    worker_llm_n = sum(1 for e in res.events if e["type"] == "worker_decision" and e["payload"].get("llm"))
    calls = sum(1 for e in res.events if e["type"] == "tool_call")
    return {"status": res.status, "replans": res.replan_count, "replan_src": src, "llm": res.llm_calls,
            "worker_llm": worker_llm_n, "tool_calls": calls, "ms": ms, "cards": len(res.cards),
            "verify": [e["payload"]["verdict"] for e in res.events if e["type"] == "verify"]}


if __name__ == "__main__":
    rows = []
    for label, msg in REQUESTS:
        for cname, mode, wl in CONDITIONS:
            r = run_one(mode, wl, msg)
            rows.append((label, cname, r))
            print(label, cname, json.dumps(r, ensure_ascii=False))
    lines = ["# 구조 비교 결과 (F3021)", "",
             f"모델 {get_settings().LLM_MODEL} · 같은 요청을 세 조건으로 실행 · 외부 API는 캐시 사용(응답 시간에 영향).", "",
             "| 요청 | 조건 | 결과 | 재계획(사유별) | LLM 호출 | Worker LLM | Tool 호출 | 응답 ms | 추천 카드 | 검증 |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for label, cname, r in rows:
        src = ", ".join(f"{k} {v}" for k, v in r["replan_src"].items()) or "-"
        lines.append(f"| {label} | {cname} | {r['status']} | {r['replans']} ({src}) | {r['llm']} | {r['worker_llm']} | "
                     f"{r['tool_calls']} | {r['ms']} | {r['cards']} | {'/'.join(r['verify']) or '-'} |")
    (ROOT / "docs" / "비교결과.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("saved docs/비교결과.md")
