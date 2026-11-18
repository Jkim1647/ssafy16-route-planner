// 표시용 변환(순수 함수). 화면에 넣는 값은 모두 Vue 텍스트 바인딩으로 들어가 이스케이프된다.
export const MODE_LABEL = { walk: "도보", subway: "지하철", bus: "버스", train: "열차", taxi: "택시", car: "자동차" };
export const POINT_LABEL = { origin: "출발지", dep_station: "출발역", arr_station: "도착역", destination: "도착지" };
export const VERDICT = { ok: "이상 없음", warn: "이상 징후", undetermined: "판정 불가" };
const NODE_LABEL = { analyze: "1. 의도·조건 분석", plan: "2. 계획 수립", execute: "3. Tool 실행", verify: "검증(로깅 Agent)",
  judge: "4. 제약 판단", replan: "재계획", respond: "5. 응답 생성", clarify: "되묻기", action: "저장·등록" };

export const won = (n) => (n === null || n === undefined ? "확인 불가" : n.toLocaleString("ko-KR") + "원");
export const mins = (m) => (m === null || m === undefined ? "?" : m >= 60 ? `${Math.floor(m / 60)}시간 ${m % 60}분` : `${m}분`);
export const dateLabel = (iso) => {
  if (!iso) return "";
  const d = new Date(iso + "T00:00:00");
  return `${d.getMonth() + 1}월 ${d.getDate()}일 (${"일월화수목금토"[d.getDay()]})`;
};
export const legLabel = (leg) =>
  leg.mode === "train" ? leg.name || "열차" : `${MODE_LABEL[leg.mode] || leg.mode}${leg.name ? " " + leg.name : ""}`;

// 카드에 쓸 짧은 노선 이름: "지하철 수도권 2호선" → "2호선", 열차·버스는 이름 그대로.
export function shortLegName(leg) {
  const n = (leg.name || "").replace(/^지하철\s*/, "").replace(/^수도권\s*/, "").trim();
  return n || MODE_LABEL[leg.mode] || leg.mode;
}

export function basisText(c) {
  const b = c.basis || {};
  if (!b.train_dep) return `이동 ${mins(b.segment_min)} 기준(마감에서 거꾸로 계산)`;
  const fare = [b.access_fare, b.train_fare, b.egress_fare].some((v) => v !== undefined)
    ? ` (역까지 ${won(b.access_fare)} + 열차 ${won(b.train_fare)} + 목적지까지 ${won(b.egress_fare)})` : "";
  return `${b.dep_station || ""} ${b.train_dep} 출발 열차 − 승차 여유 ${b.board_buffer_min}분 − 역까지 ${b.access_min ?? "?"}분 = ` +
    `${c.leave_at} 출발 · ${b.arr_station || ""} ${b.train_arr} 도착 + 목적지까지 ${b.egress_min ?? "?"}분 = ${c.arrive_at} 도착${fare}`;
}

function shortArgs(a) {
  if (!a) return "";
  return Object.entries(a).map(([k, v]) => `${k}=${typeof v === "number" ? Math.round(v * 1000) / 1000 : v}`).join(", ");
}

// 실행 이벤트 → 타임라인 항목. 단계는 시작 순서대로 두고, 끝날 때 소요시간·결과를 채운다.
export function buildTrace(events) {
  const items = [];
  const starts = {};
  const agent = (e) => (e.agent === "main" || !e.agent ? "Agent" : e.agent[0].toUpperCase() + e.agent.slice(1));
  for (const e of events || []) {
    const p = e.payload || {};
    if (e.type === "node_start") {
      const it = { kind: "node", agent: agent(e), role: e.agent, title: NODE_LABEL[e.node] || e.node, ms: "…", details: [] };
      starts[e.node] = it;
      items.push(it);
    } else if (e.type === "node_end" && starts[e.node]) {
      const it = starts[e.node];
      it.ms = `${e.duration_ms ?? 0}ms`;
      if (p.intent) it.details.push(`의도: ${p.intent} — ${p.intent_reason || ""}`);
      else if (p.missing && p.missing.length) it.details.push(`누락: ${p.missing.join(", ")}`);
    } else if (e.type === "plan_tasks") {
      const tools = [...new Set((p.tasks || []).map((t) => t.tool))];
      items.push({ kind: "node", agent: agent(e), role: e.agent, title: "작업 목록", details: [tools.join(" → ")] });
    } else if (e.type === "tool_result") {
      const call = (events || []).find((x) => x.type === "tool_call" && x.seq === e.seq - 1);
      items.push({ kind: p.ok ? "tool" : "tool fail", agent: agent(e), role: e.agent, title: `Tool ${p.tool}`,
        ms: p.cached ? "캐시" : `${e.duration_ms}ms`, cached: p.cached,
        details: [call ? shortArgs(call.payload.args) : ""], result: p.ok ? p.summary : null,
        error: p.ok ? null : `${p.code} · ${p.message || ""}` });
    } else if (e.type === "replan") {
      items.push({ kind: "replan", title: `재계획 ${p.count}: ${p.strategy}`, details: [p.reason] });
    } else if (e.type === "llm_decision") {
      items.push({ kind: "llm", agent: agent(e), role: e.agent, title: `LLM 판단 · ${p.decision}`,
        details: [`${p.value || ""} ${p.reason ? "— " + p.reason : ""}`] });
    } else if (e.type === "worker_decision" || e.type === "verify") {
      items.push({ kind: "llm", agent: agent(e), role: e.agent, title: e.type === "verify" ? "검증(로깅 Agent)" : "Worker 판단",
        details: [JSON.stringify(p)] });
    } else if (e.type === "error") {
      items.push({ kind: "tool fail", title: "오류", details: [p.type] });
    }
  }
  return items;
}

export const elapsedMs = (events) =>
  !events || events.length < 2 ? 0 : new Date(events[events.length - 1].ts) - new Date(events[0].ts);
