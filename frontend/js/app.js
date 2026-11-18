// 화면 동작: 탭 전환, 대화, 계획 관리, 실행 로그.
const $ = (id) => document.getElementById(id);
let sessionId = null;
let lastConditions = null;

// ---------------------------------------------------------------- 탭
document.querySelectorAll(".tab").forEach((t) =>
  t.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((x) => { x.classList.toggle("active", x === t); x.setAttribute("aria-selected", x === t); });
    document.querySelectorAll(".tabpanel").forEach((p) => (p.hidden = p.id !== "tab-" + t.dataset.tab));
    if (t.dataset.tab === "plans") loadPlans();
    if (t.dataset.tab === "logs") loadLogs();
  }));

// ---------------------------------------------------------------- 상태(키 누락·호출 한도)
async function loadStatus() {
  try {
    const s = await api("/config/status");
    const missing = Object.entries(s.keys).filter(([, v]) => !v).map(([k]) => k);
    $("banner").hidden = !missing.length;
    if (missing.length) $("banner").textContent = `API 키가 설정되지 않았어요: ${missing.join(", ")} — .env 파일을 확인해 주세요.`;
    const q = s.quota || {};
    $("quota").textContent = `모델 ${s.model} · ODsay 오늘 ${q.odsay?.used ?? "?"}/${q.odsay?.limit ?? "?"}회 · ITS 이번 달 ${q.its?.used ?? "?"}/${q.its?.limit ?? "?"}회`;
  } catch (e) {
    $("banner").hidden = false;
    $("banner").textContent = e.message;
  }
}

// ---------------------------------------------------------------- 대화
function addMsg(kind, ...children) {
  const m = el("div", { class: "msg " + kind }, ...children);
  $("messages").append(m);
  $("messages").scrollTop = $("messages").scrollHeight;
  return m;
}

$("chat-form").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const text = $("chat-input").value.trim();
  if (!text) return;
  $("chat-input").value = "";
  addMsg("user", el("p", {}, text));
  const pending = addMsg("agent pending", el("p", {}, "경로를 계산하는 중이에요"));
  $("send").disabled = true;
  $("trace-meta").textContent = "처리 중…";
  try {
    const r = await api("/chat", { method: "POST", body: { message: text, session_id: sessionId } });
    sessionId = r.session_id;
    const cond = r.events.find((e) => e.type === "node_end" && e.node === "analyze")?.payload?.conditions;
    if (cond) lastConditions = cond;
    const snap = lastConditions;  // 이 카드들을 만든 조건(나중 대화가 바꿔도 유지)
    pending.remove();
    addMsg("agent",
      el("p", {}, r.reply),
      r.cards.filter((c) => c.leave_at).map((c) => renderCard(c, (x) => saveCard(x, snap))),
      r.cards.filter((c) => c.type === "source").map((c) => el("p", { class: "hint" }, `출처: ${c.title}${c.page ? " p." + c.page : ""}`)),
      renderExcluded("제외된 후보", r.excluded),
      renderExcluded("판단하지 않은 후보", r.undetermined),
      renderExcluded("추정 시간표(통과 아님)", r.estimated));
    renderTrace($("trace"), r.events);
    $("trace-meta").textContent = `재계획 ${r.replan_count}회 · LLM ${r.llm_calls}회 · ${elapsed(r.events)}ms`;
    loadStatus();
  } catch (e) {
    pending.remove();
    addMsg("agent error", el("p", {}, e.message));
    $("trace-meta").textContent = "";
  } finally {
    $("send").disabled = false;
    $("chat-input").focus();
  }
});

function elapsed(events) {
  if (events.length < 2) return 0;
  return new Date(events[events.length - 1].ts) - new Date(events[0].ts);
}

$("new-chat").addEventListener("click", () => {
  sessionId = null;
  lastConditions = null;
  $("messages").replaceChildren(el("div", { class: "msg agent" }, el("p", {}, "새 대화를 시작했어요. 이동 조건을 알려 주세요.")));
  $("trace").replaceChildren(el("li", { class: "empty" }, "요청을 보내면 단계와 Tool 호출이 순서대로 표시됩니다."));
  $("trace-meta").textContent = "";
});

async function saveCard(c, conds) {
  const title = conds ? `${conds.origin} → ${conds.destination}` : `${c.leave_at} 출발 이동`;
  try {
    const r = await api("/plans", { method: "POST", body: {
      title, date: c.date, leave_at: c.leave_at, arrive_at: c.arrive_at,
      origin_name: conds?.origin || "-", destination_name: conds?.destination || "-",
      legs: c.legs, total_fare: c.total_fare } });
    const overlap = r.overlaps.length
      ? ` 같은 날 시간이 겹치는 계획이 있어요: ${r.overlaps.map((p) => `${p.title} ${p.leave_at}~${p.arrive_at}`).join(", ")}` : "";
    addMsg("agent", el("p", {}, `이동 계획으로 저장했어요(${r.plan.date} ${r.plan.leave_at}~${r.plan.arrive_at}).${overlap}`));
  } catch (e) {
    addMsg("agent error", el("p", {}, e.message));
  }
}

// ---------------------------------------------------------------- 이동 계획
async function loadPlans(notice) {
  const rows = $("plan-rows");
  try {
    const plans = await api("/plans");
    rows.replaceChildren(...plans.map(planRow));
    $("plans-empty").hidden = plans.length > 0;
    $("plan-notice").hidden = true;  // 이전 오류 알림을 지운다
  } catch (e) {
    showNotice(e.message);
  }
  if (notice) showNotice(notice.text, notice.ok);
}

function planRow(p) {
  const tr = el("tr", {},
    el("td", { class: "num" }, p.date),
    el("td", { class: "num" }, `${p.leave_at} → ${p.arrive_at}`),
    el("td", {}, p.title, el("div", { class: "basis" }, (p.legs || []).map((l) => l.mode === "train" ? l.name : MODE_LABEL[l.mode]).filter(Boolean).join(" · "))),
    el("td", { class: "num" }, won(p.total_fare)),
    el("td", { class: "num" }, p.created_at.replace("T", " ").slice(0, 16)),
    el("td", { class: "actions" },
      p.calendar_event_id ? el("span", { class: "basis" }, "캘린더 등록됨 ")
        : el("button", { class: "ghost", onclick: () => addToCalendar(p) }, "캘린더"), " ",
      el("button", { class: "ghost", onclick: () => editPlan(p, tr) }, "수정"), " ",
      el("button", { class: "danger", onclick: () => deletePlan(p) }, "삭제")));
  return tr;
}

function editPlan(p, tr) {
  document.querySelectorAll(".edit-row").forEach((r) => r.remove());
  const row = $("edit-tpl").content.firstElementChild.cloneNode(true);
  const f = row.querySelector("form");
  for (const k of ["title", "date", "leave_at", "arrive_at"]) f.elements[k].value = p[k];
  f.querySelector(".cancel").addEventListener("click", () => row.remove());
  f.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const body = Object.fromEntries(["title", "date", "leave_at", "arrive_at"].map((k) => [k, f.elements[k].value]));
    try {
      const r = await api(`/plans/${p.id}`, { method: "PUT", body });
      const msg = r.overlaps.length
        ? `수정했어요. 같은 날 겹치는 계획: ${r.overlaps.map((o) => `${o.title} ${o.leave_at}~${o.arrive_at}`).join(", ")}`
        : "수정했어요.";
      loadPlans({ text: msg, ok: !r.overlaps.length });
    } catch (e) {
      showNotice(e.message);
    }
  });
  tr.after(row);
}

async function addToCalendar(p) {
  try {
    const r = await api(`/plans/${p.id}/calendar`, { method: "POST" });
    loadPlans({ text: `캘린더(${r.backend})에 등록했어요.`, ok: true });
  } catch (e) {
    showNotice(e.message);
  }
}

async function deletePlan(p) {
  if (!confirm(`'${p.title}' (${p.date} ${p.leave_at}) 계획을 삭제할까요?`)) return;
  try {
    await api(`/plans/${p.id}`, { method: "DELETE" });
    loadPlans({ text: "삭제했어요.", ok: true });
  } catch (e) {
    showNotice(e.message);
  }
}

function showNotice(text, ok) {
  const n = $("plan-notice");
  n.hidden = false;
  n.className = "notice" + (ok ? " ok" : "");
  n.textContent = text;
}
$("reload-plans").addEventListener("click", () => loadPlans());

// ---------------------------------------------------------------- 실행 로그
let currentLog = null;

async function loadLogs() {
  try {
    const sessions = await api("/logs");
    $("log-list").replaceChildren(...sessions.map((s) => el("li", {},
      el("button", { class: s.session_id === currentLog ? "active" : "", onclick: () => openLog(s.session_id) },
        s.first_message || s.session_id,
        el("span", { class: "small" }, `${s.last_ts.replace("T", " ").slice(5, 16)} · 요청 ${s.run_count}건${s.warn_count ? ` · 이상 ${s.warn_count}` : ""}`)))));
    if (!sessions.length) $("log-list").replaceChildren(el("li", { class: "empty" }, "저장된 실행 로그가 없어요."));
  } catch (e) {
    $("log-list").replaceChildren(el("li", { class: "empty" }, e.message));
  }
}

async function openLog(sid) {
  currentLog = sid;
  try {
    const d = await api(`/logs/${sid}`);
    $("log-title").textContent = `실행 로그 · ${sid}`;
    $("delete-log").hidden = false;
    $("log-runs").replaceChildren(...d.runs.map((r) => el("div", { class: "run-summary" },
      `"${r.user_message || ""}" · ${r.status || ""} · 재계획 ${r.replan_count ?? 0} · LLM ${r.llm_calls ?? 0}`,
      r.anomaly ? el("span", { class: "verdict " + r.anomaly.verdict }, VERDICT[r.anomaly.verdict]) : null,
      r.anomaly && r.anomaly.findings.length ? el("div", { class: "basis" }, r.anomaly.findings.map((f) => `${f.rule}: ${f.detail}`).join(" / ")) : null,
      r.anomaly && r.anomaly.diagnosis ? el("div", { class: "basis" }, "LLM 진단: " + r.anomaly.diagnosis) : null)));
    renderTrace($("log-trace"), d.events);
    loadLogs();
  } catch (e) {
    $("log-trace").replaceChildren(el("li", { class: "empty" }, e.message));
  }
}
const VERDICT = { ok: "이상 없음", warn: "이상 징후", undetermined: "판정 불가" };

$("delete-log").addEventListener("click", async () => {
  if (!currentLog || !confirm("이 세션의 실행 로그를 삭제할까요? 되돌릴 수 없어요.")) return;
  try {
    await api(`/logs/${currentLog}`, { method: "DELETE" });
    currentLog = null;
    $("log-trace").replaceChildren(el("li", { class: "empty" }, "삭제했어요."));
    $("log-runs").replaceChildren();
    $("delete-log").hidden = true;
    loadLogs();
  } catch (e) {
    alert(e.message);
  }
});
$("reload-logs").addEventListener("click", loadLogs);

loadStatus();
