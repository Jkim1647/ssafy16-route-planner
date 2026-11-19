// 페이지 사이에 유지되는 상태: 대화 내용(페이지를 옮겨도 남음), 서버 상태, 알림.
import { reactive } from "vue";
import { api } from "./api.js";

function newBuilder() {
  return { date: new Date(Date.now() + 86400000).toLocaleDateString("sv-SE"), budget: "", priority: "cheapest", stops: [] };
}

const WELCOME = { role: "agent", text: "출발지·도착지와 \"언제까지 도착\" 또는 \"언제부터 출발\"을 알려 주세요." };

function savedSession() {
  try { return sessionStorage.getItem("rp.session") || null; } catch { return null; }
}

export const store = reactive({
  sessionId: savedSession(),
  messages: [WELCOME],
  lastEvents: [],
  lastMeta: "",
  sending: false,
  selected: null,          // 지도에 크게 보여 줄 경로 카드
  status: null,            // /config/status
  statusError: "",
  toasts: [],
  auth: null,              // /auth/me {user, auth_required, google_configured}
  places: [],              // 저장한 장소(대화의 질문 만들기 패널에서 사용)
  builder: newBuilder(),
  pendingQuestion: "",
  sidePanel: "builder",    // 대화 화면 오른쪽 칸: builder(질문 만들기) · map · trace — 결과가 없을 땐 질문 만들기부터     // 다른 화면(계획 재확인·일정 제안)에서 대화로 넘겨 바로 보낼 질문   // 조건으로 질문 만들기(들를 곳·날짜·시각) — 페이지를 옮겨도 유지
});

export async function loadMe() {
  try { store.auth = await api("/auth/me"); } catch { store.auth = { user: null, auth_required: false, google_configured: false }; }
}

export async function loadPlaces() {
  try { store.places = await api("/places"); } catch { store.places = []; }
}

export function setSession(id) {
  store.sessionId = id;
  try { id ? sessionStorage.setItem("rp.session", id) : sessionStorage.removeItem("rp.session"); } catch { /* 저장 불가 환경 */ }
}

export function resetChat() {
  setSession(null);
  store.messages = [{ role: "agent", text: "새 대화를 시작했어요. 이동 조건을 알려 주세요." }];
  store.lastEvents = [];
  store.lastMeta = "";
  store.selected = null;
  store.sidePanel = "builder";
}

export async function loadStatus() {
  try {
    store.status = await api("/config/status");
    store.statusError = "";
  } catch (e) {
    store.statusError = e.message;
  }
}

let toastId = 0;
export function toast(text, kind = "ok", link = null) {
  const id = ++toastId;
  store.toasts.push({ id, text, kind, link });
  setTimeout(() => { store.toasts = store.toasts.filter((t) => t.id !== id); }, link ? 12000 : 6000);  // 링크가 있으면 누를 시간을 더 준다
}
