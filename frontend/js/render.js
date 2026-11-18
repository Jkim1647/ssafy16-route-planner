// DOM 그리기 도우미. 사용자·서버 텍스트는 항상 textContent로 넣는다(innerHTML 금지).
function el(tag, attrs = {}, ...children) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") n.className = v;
    else if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
    else n.setAttribute(k, v === true ? "" : v);
  }
  for (const c of children.flat()) {
    if (c === null || c === undefined || c === false) continue;
    n.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return n;
}

const MODE_LABEL = { walk: "도보", subway: "지하철", bus: "버스", train: "열차", taxi: "택시", car: "자동차" };
const won = (n) => (n === null || n === undefined ? "확인 불가" : n.toLocaleString("ko-KR") + "원");
const mins = (m) => (m === null || m === undefined ? "?" : m >= 60 ? `${Math.floor(m / 60)}시간 ${m % 60}분` : `${m}분`);

function legChip(leg) {
  const label = leg.mode === "train" ? leg.name : `${MODE_LABEL[leg.mode] || leg.mode}${leg.name ? " " + leg.name : ""}`;
  return el("li", { class: leg.mode }, `${label} ${leg.minutes ?? "?"}분`);
}

function renderCard(c, onSave) {
  const b = c.basis || {};
  const basis = b.train_dep
    ? `${b.dep_station || ""} ${b.train_dep} 출발 열차 − 승차 여유 ${b.board_buffer_min}분 − 역까지 ${b.access_min ?? "?"}분 = ${c.leave_at} 출발 · ` +
      `${b.arr_station || ""} ${b.train_arr} 도착 + 목적지까지 ${b.egress_min ?? "?"}분 = ${c.arrive_at} 도착`
    : `이동 ${mins(b.segment_min)} 기준`;
  const fareParts = [b.access_fare, b.train_fare, b.egress_fare].some((v) => v !== undefined)
    ? ` (역까지 ${won(b.access_fare)} + 열차 ${won(b.train_fare)} + 목적지까지 ${won(b.egress_fare)})` : "";
  return el("div", { class: "card" },
    el("div", { class: "card-head" },
      el("strong", {}, `${c.index}. ${c.label || "추천"}`),
      el("span", { class: "times" }, `${c.leave_at} → ${c.arrive_at}`)),
    el("p", { class: "sub" }, `${c.date} · ${mins(c.total_min)} · 환승 ${c.transfers}회 · 총 ${won(c.total_fare)}`),
    el("ul", { class: "legs" }, (c.legs || []).map(legChip)),
    el("p", { class: "basis" }, "판단 근거: " + basis + fareParts),
    (c.warnings || []).map((w) => el("p", { class: "warn" }, "⚠ " + w)),
    onSave ? el("button", { onclick: () => onSave(c) }, "이 경로로 저장") : null);
}

function renderExcluded(title, items) {
  if (!items || !items.length) return null;
  return el("details", { class: "excluded" },
    el("summary", {}, `${title} ${items.length}건`),
    el("ul", {}, items.map((x) => el("li", {}, `${x.summary} — ${x.reason || "추정 시간표"}`))));
}

// 실행 이벤트 → 타임라인
function renderTrace(listEl, events) {
  listEl.replaceChildren();
  const starts = {};
  for (const e of events) {
    const badge = el("span", { class: "badge " + (e.agent || "main") }, e.agent === "main" ? "Agent" : cap(e.agent));
    if (e.type === "node_start") {  // 단계는 시작 순서대로 그리고, 끝날 때 소요시간·결과를 채운다
      const li = el("li", { class: "node" }, badge, NODE_LABEL[e.node] || e.node, el("span", { class: "ms" }, "…"));
      starts[e.node] = li;
      listEl.append(li);
      continue;
    }
    if (e.type === "node_end") {
      const p = e.payload || {};
      const li = starts[e.node];
      if (!li) continue;
      li.querySelector(".ms").textContent = `${e.duration_ms ?? 0}ms`;
      const extra = p.intent ? `의도: ${p.intent} — ${p.intent_reason || ""}` : p.missing && p.missing.length ? `누락: ${p.missing.join(", ")}` : "";
      if (extra) li.append(el("div", { class: "detail" }, extra));
    } else if (e.type === "plan_tasks") {
      const tasks = (e.payload.tasks || []).map((t) => t.tool);
      listEl.append(el("li", { class: "node" }, badge, "작업 목록",
        el("div", { class: "detail" }, [...new Set(tasks)].join(" → "))));
    } else if (e.type === "tool_call") {
      // 결과 줄에서 함께 표시
    } else if (e.type === "tool_result") {
      const p = e.payload;
      const call = events.find((x) => x.type === "tool_call" && x.seq === e.seq - 1);
      const args = call ? shortArgs(call.payload.args) : "";
      listEl.append(el("li", { class: "tool" + (p.ok ? "" : " fail") }, badge, `Tool ${p.tool}`,
        p.cached ? el("span", { class: "ms cached" }, "캐시") : el("span", { class: "ms" }, `${e.duration_ms}ms`),
        el("div", { class: "detail" }, args),
        el("div", { class: "detail" }, p.ok ? p.summary : el("span", { class: "code" }, `${p.code} · ${p.message || ""}`))));
    } else if (e.type === "replan") {
      listEl.append(el("li", { class: "replan" }, `재계획 ${e.payload.count}: ${e.payload.strategy}`,
        el("div", { class: "detail" }, e.payload.reason)));
    } else if (e.type === "llm_decision") {
      const p = e.payload;
      listEl.append(el("li", { class: "llm" }, badge, `LLM 판단 · ${p.decision}`,
        el("div", { class: "detail" }, `${p.value || ""} ${p.reason ? "— " + p.reason : ""}`)));
    } else if (e.type === "worker_decision" || e.type === "verify") {
      listEl.append(el("li", { class: "llm" }, badge, e.type === "verify" ? "검증(로깅 Agent)" : "Worker 판단",
        el("div", { class: "detail" }, JSON.stringify(e.payload))));
    } else if (e.type === "error") {
      listEl.append(el("li", { class: "tool fail" }, "오류", el("div", { class: "detail" }, e.payload.type)));
    }
  }
  if (!listEl.children.length) listEl.append(el("li", { class: "empty" }, "표시할 단계가 없어요."));
}

const NODE_LABEL = { analyze: "1. 의도·조건 분석", plan: "2. 계획 수립", execute: "3. Tool 실행", judge: "4. 제약 판단",
  replan: "재계획", respond: "5. 응답 생성", clarify: "되묻기", action: "저장·등록" };
const cap = (s) => (s ? s[0].toUpperCase() + s.slice(1) : "");

function shortArgs(a) {
  if (!a) return "";
  return Object.entries(a).map(([k, v]) => `${k}=${typeof v === "number" ? Math.round(v * 1000) / 1000 : v}`).join(", ");
}
