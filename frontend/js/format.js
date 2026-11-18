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

// ---------------------------------------------------------------- 노선 색
// 지하철은 노선 고유색(이름으로 구분), 버스는 종류별 색(ODsay 버스 종류 코드). 모르면 수단 기본색.
const SUBWAY_SPECIAL = [
  [/신분당/, "#D4003B"], [/수인|분당/, "#F5A200"], [/경의|중앙/, "#77C4A3"], [/공항/, "#0090D2"], [/경춘/, "#0C8E72"],
  [/우이/, "#B0CE18"], [/신림/, "#6789CA"], [/서해/, "#8FC31F"], [/김포/, "#A17E46"], [/GTX/, "#9A6292"],
  [/인천\s*1/, "#7CA8D5"], [/인천\s*2/, "#ED8B00"], [/의정부/, "#FDA600"], [/에버라인|용인/, "#509F22"], [/경강/, "#0054A6"],
];
const SUBWAY_REGION = {
  광주: { 1: "#009088" }, 부산: { 1: "#F06A00", 2: "#81BF48", 3: "#BB8C00", 4: "#217DCB" },
  대구: { 1: "#D93F5C", 2: "#00AA80", 3: "#FFB100" }, 대전: { 1: "#007448" },
};
const SUBWAY_SEOUL = { 1: "#0052A4", 2: "#00A84D", 3: "#EF7C1C", 4: "#00A5DE", 5: "#996CAC", 6: "#CD7C2F",
  7: "#747F00", 8: "#E6186C", 9: "#BDB092" };
const BUS_TYPE = { 11: ["간선", "#3D5BAB"], 12: ["지선", "#5BB025"], 13: ["순환", "#F2B70A"], 14: ["광역", "#E60012"],
  15: ["급행", "#E60012"], 26: ["급행간선", "#E60012"], 4: ["직행좌석", "#E60012"], 3: ["마을", "#79C142"],
  5: ["공항", "#00A0E9"], 6: ["간선급행", "#3D5BAB"], 1: ["일반", "#009CDA"], 2: ["좌석", "#009CDA"] };
export const MODE_COLOR = { walk: "#aab3af", bus: "#4f9a3a", subway: "#3d4fa1", train: "#1f5f4a", taxi: "#c07a12", car: "#c07a12" };

function subwayColor(name) {
  const n = name || "";
  for (const [re, c] of SUBWAY_SPECIAL) if (re.test(n)) return c;  // 신분당을 분당보다 먼저 검사
  const num = (n.match(/(\d)\s*호선/) || [])[1];
  if (!num) return null;
  const region = Object.keys(SUBWAY_REGION).find((r) => n.includes(r));
  return region ? SUBWAY_REGION[region][num] || null : SUBWAY_SEOUL[num] || null;
}

export function legColor(leg) {
  if (!leg) return MODE_COLOR.walk;
  if (leg.mode === "subway") return subwayColor(leg.name) || MODE_COLOR.subway;
  if (leg.mode === "bus" && leg.source !== "tago_bus") return (BUS_TYPE[leg.line_code] || [])[1] || MODE_COLOR.bus;
  return MODE_COLOR[leg.mode] || MODE_COLOR.train;
}

export const busTypeLabel = (leg) => (leg && leg.mode === "bus" ? (BUS_TYPE[leg.line_code] || [])[0] || null : null);

// 밝은 노선색(노랑 등)을 글자에 쓸 때 흰 바탕에서 읽히도록 어둡게
export function textColor(hex) {
  const n = parseInt(hex.slice(1), 16);
  const r = (n >> 16) & 255, g = (n >> 8) & 255, b = n & 255;
  if (0.299 * r + 0.587 * g + 0.114 * b < 150) return hex;
  const k = 0.62;
  return `rgb(${Math.round(r * k)}, ${Math.round(g * k)}, ${Math.round(b * k)})`;
}
