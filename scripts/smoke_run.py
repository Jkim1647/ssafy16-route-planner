"""실제 API·GMS로 대화 1턴 실행해 결과를 docs/evidence/에 저장. 사용: python scripts/smoke_run.py 이름 "메시지" [세션]"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.settings import get_settings  # noqa: E402

s = get_settings()
import backend.tools.catalog_all  # noqa: E402,F401
from backend.agent.graph import Deps, build_graph  # noqa: E402
from backend.agent.llm import get_llm  # noqa: E402
from backend.agent.service import run_turn  # noqa: E402
from backend.db.database import init_db  # noqa: E402
from backend.db.repositories import EventRepo, PlanRepo, RunRepo  # noqa: E402
from backend.events.bus import build_bus  # noqa: E402
from backend.tools.budget import default_budget  # noqa: E402

name, msg = sys.argv[1], sys.argv[2]
session = sys.argv[3] if len(sys.argv) > 3 else f"smoke-{name}"
init_db(s.DB_PATH)
deps = Deps(llm_factory=get_llm, plan_repo=PlanRepo(s.DB_PATH), settings=s)
g = build_graph(deps)
res = run_turn(g, deps, build_bus(EventRepo(s.DB_PATH)), RunRepo(s.DB_PATH), session, msg)
print("status", res.status, "| intent", res.intent, "| replans", res.replan_count, "| llm", res.llm_calls)
print(res.reply)
for c in res.cards:
    print(f" [{c['label']}] {c['leave_at']}→{c['arrive_at']} {c['total_fare']}원 {c['total_min']}분",
          [(lg['mode'], lg['name'], lg['minutes']) for lg in c['legs']], c['warnings'])
print(" excluded:", [e["reason"] for e in res.excluded[:3]], "| undetermined:", [e["reason"] for e in res.undetermined[:2]])
print(" tools:", [(e["payload"]["tool"], e["payload"]["summary"], "cache" if e["payload"]["cached"] else e["duration_ms"])
                  for e in res.events if e["type"] == "tool_result"])
print(" quota:", default_budget().usage())
out = Path("docs/evidence") / f"{name}.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(res.model_dump(), ensure_ascii=False, indent=1, default=str), encoding="utf-8")
