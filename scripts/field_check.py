"""2일차 실사용 점검: 실제 API·GMS로 자주 쓸 법한 요청 6건을 돌려 docs/evidence/field_check.json에 남긴다.

사용: python scripts/field_check.py   (ODsay 하루 30회 안에서 — 실행 전후 사용량을 함께 기록)
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.settings import get_settings  # noqa: E402

get_settings()
os.environ["CALENDAR_BACKEND"] = "local"  # 실제 Google 일정이 기록에 남지 않게
os.environ["DEBUG_FORCE"] = ""
from backend.container import Container  # noqa: E402
from backend.tools.budget import default_budget  # noqa: E402

CASES = [
    ("C1", "부산행(장거리·행사)", None, "내일 오후 3시까지 광주 유스퀘어에서 부산 벡스코 가야 해"),
    ("C2", "광주 시내", None, "내일 오전 9시까지 광주 첨단동에서 광주 유스퀘어 가야 해"),
    ("C3", "'모레' 날짜 해석", None, "모레 오전 11시까지 광주 첨단동에서 서울 강남역 가야 해"),
    ("C4", "후속 변경(도착지만)", "C3", "도착지를 서울역으로 바꿔줘"),
    ("C5", "예산 초과", None, "내일 오후 2시까지 광주 첨단동에서 서울 강남역 가야 해. 2만원 이하로"),
    ("C6", "열차 없는 시각 → 고속버스", None, "내일 오전 6시 30분까지 광주 유스퀘어에서 서울 센트럴시티 가야 해"),
]


def row(cid, title, res):
    tools = [e["payload"]["tool"] for e in res.events if e["type"] == "tool_call"]
    return {"id": cid, "title": title, "status": res.status, "intent": res.intent, "replans": res.replan_count,
            "llm_calls": res.llm_calls, "tool_calls": len(tools), "tools": sorted(set(tools)),
            "conditions": res.conditions if hasattr(res, "conditions") else None,
            "cards": [{"label": x.get("label"), "leave_at": x.get("leave_at"), "arrive_at": x.get("arrive_at"),
                       "fare": x.get("total_fare"), "modes": [lg["mode"] for lg in x.get("legs", [])],
                       "warnings": x.get("warnings")} for x in res.cards],
            "excluded_sample": [x["reason"] for x in res.excluded[:3]], "reply": res.reply,
            "run_id": res.run_id, "session_id": res.session_id}


def main():
    c = Container.build()
    before = default_budget().usage()
    rows, sessions = [], {}
    for cid, title, follow, msg in CASES:
        res = c.chat(sessions.get(follow), msg)
        sessions[cid] = res.session_id
        r = row(cid, title, res)
        r["message"] = msg
        rows.append(r)
        print(f"[{cid}] {res.status} replans={res.replan_count} llm={res.llm_calls} tools={r['tool_calls']} "
              f"cards={len(res.cards)}")
    out = {"before": before, "after": default_budget().usage(), "rows": rows}
    (ROOT / "docs" / "evidence" / "field_check.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")


if __name__ == "__main__":
    main()
