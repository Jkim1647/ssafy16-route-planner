"""이상 징후 판정(F3020). 판정은 규칙(LLM 없음), 이상(warn)으로 판정된 실행에만 LLM이 원인을 진단한다.

규칙
- DUPLICATE_CALL   : 한 실행에서 같은 Tool을 같은 입력으로 2회 이상 실제 호출(캐시 적중·재시도 제외)
- UNPLANNED_CALL   : 작업 목록(plan_tasks)에 없는 작업 ID이거나, 작업의 Tool과 다른 Tool 호출(재시도 제외)
- EXCESSIVE_REPLAN : 재계획 2회 이상
근거 이벤트(plan_tasks·tool_call)가 하나도 없으면 '이상 없음'이 아니라 '판정 불가'.
"""
from __future__ import annotations

import json
import logging

from pydantic import BaseModel

log = logging.getLogger(__name__)
REPLAN_WARN = 2


class Diagnosis(BaseModel):
    """diagnose의 LLM 구조화 출력(원인 진단 문장)."""
    text: str


def _pairs(events: list[dict]) -> list[tuple[dict, dict | None]]:
    out, pending = [], None
    for e in events:
        if e["type"] == "tool_call":
            if pending:
                out.append((pending, None))
            pending = e
        elif e["type"] == "tool_result" and pending:
            out.append((pending, e))
            pending = None
    if pending:
        out.append((pending, None))
    return out


def judge_run(events: list[dict], max_replan: int) -> dict:
    """한 run의 이벤트를 규칙으로 판정해 {verdict: ok|warn|undetermined, findings: [{rule, detail, event_seqs}]}를 돌려준다.
    재계획 경고 기준은 REPLAN_WARN이고, max_replan은 '상한 도달' 표시에만 쓴다.
    """
    plans = [e for e in events if e["type"] == "plan_tasks"]
    pairs = _pairs(events)
    if not plans and not pairs:
        return {"verdict": "undetermined", "findings": []}
    planned = {t["id"]: t["tool"] for p in plans for t in p["payload"].get("tasks", [])}
    findings = []

    seen: dict[str, list[int]] = {}
    for call, result in pairs:
        p = call["payload"]
        if p.get("retry_of") or (result and result["payload"].get("cached")):
            continue
        key = p["tool"] + json.dumps(p.get("args", {}), sort_keys=True, ensure_ascii=False)
        seen.setdefault(key, []).append(call["seq"])
    for key, seqs in seen.items():
        if len(seqs) > 1:
            tool = key.split("{", 1)[0]
            findings.append({"rule": "DUPLICATE_CALL", "detail": f"{tool}를 같은 입력으로 {len(seqs)}회 호출",
                             "event_seqs": seqs})

    for call, _ in pairs:
        p = call["payload"]
        if p.get("retry_of"):
            continue
        if planned.get(p.get("task_id")) != p["tool"]:
            findings.append({"rule": "UNPLANNED_CALL", "detail": f"계획에 없던 호출: {p['tool']} (task {p.get('task_id')})",
                             "event_seqs": [call["seq"]]})

    replans = [e for e in events if e["type"] == "replan"]
    if len(replans) >= REPLAN_WARN:
        findings.append({"rule": "EXCESSIVE_REPLAN",
                         "detail": f"재계획 {len(replans)}회 (상한 {max_replan})" + (" — 상한 도달" if len(replans) >= max_replan else ""),
                         "event_seqs": [e["seq"] for e in replans]})
    return {"verdict": "warn" if findings else "ok", "findings": findings}


DIAG_PROMPT = """너는 Agent 실행 로그를 검토하는 진단기다. 아래 규칙 판정 결과와 이벤트 요약을 읽고,
어느 쪽(Planner/계획, Worker/실행기, Tool) 문제인지와 무엇을 고치면 되는지 한국어 3문장 이내로 써라.
판정 결과: {findings}
이벤트 요약: {events}"""


def diagnose(llm, events: list[dict], findings: list[dict]) -> str | None:
    """warn 판정의 원인을 LLM이 짧게 진단한다(최대 500자). 이벤트는 핵심 필드만 추려 60개까지 넘긴다.
    실패하면 None — 판정과 실행 로그에는 영향이 없다.
    """
    brief = [{"seq": e["seq"], "type": e["type"], "node": e.get("node"),
              **{k: e["payload"].get(k) for k in ("tool", "task_id", "args", "code", "cached", "strategy", "reason")
                 if k in (e.get("payload") or {})}}
             for e in events if e["type"] in ("plan_tasks", "tool_call", "tool_result", "replan")][:60]
    try:
        out = llm.with_structured_output(Diagnosis).invoke(
            [("system", DIAG_PROMPT.format(findings=json.dumps(findings, ensure_ascii=False),
                                           events=json.dumps(brief, ensure_ascii=False)))])
        return out.text.strip()[:500]
    except Exception:  # 진단 실패해도 판정과 실행 로그는 그대로 남는다
        log.warning("anomaly diagnosis failed", exc_info=True)
        return None


def evaluate_and_store(run_id: str, event_repo, anomaly_repo, llm_factory, max_replan: int) -> dict:
    """run이 끝난 뒤(run_turn의 after_run) 이벤트를 읽어 판정·저장하고, warn이면 진단을 덧붙인다.
    LLM 생성·진단 실패는 무시하고 판정 결과 dict를 돌려준다.
    """
    events = event_repo.get_run(run_id)
    result = judge_run(events, max_replan)
    anomaly_repo.save(run_id, result["verdict"], result["findings"])
    if result["verdict"] == "warn":
        try:
            text = diagnose(llm_factory(), events, result["findings"])
        except Exception:
            text = None
        if text:
            anomaly_repo.set_diagnosis(run_id, text)
    return result
