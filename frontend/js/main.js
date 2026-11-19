// 앱 시작: 라우터(주소별 페이지)와 상단바·상태 배너·알림.
import { createApp, computed, onMounted, ref } from "vue";
import { createRouter, createWebHashHistory } from "vue-router";
import { API_BASE, api } from "./api.js";
import { loadMe, loadPlaces, loadStatus, store } from "./store.js";
import ChatPage from "./pages/ChatPage.js";
import PlansPage from "./pages/PlansPage.js";
import PlanDetailPage from "./pages/PlanDetailPage.js";
import { LogDetailPage, LogsPage } from "./pages/LogsPage.js";
import PlacesPage from "./pages/PlacesPage.js";
import IntroGuide, { introHiddenToday } from "./components/IntroGuide.js";

const NotFound = {
  template: `<section class="page empty-state"><p>없는 페이지예요.</p><router-link to="/" class="button">대화로 가기</router-link></section>`,
};

const routes = [
  { path: "/", component: ChatPage, meta: { title: "대화" } },
  { path: "/plans", component: PlansPage, meta: { title: "이동 계획" } },
  { path: "/plans/:id(\\d+)", component: PlanDetailPage, props: true, meta: { title: "이동 계획 상세" } },
  { path: "/trip", redirect: "/" },  // 여러 동선은 대화 화면의 '조건으로 질문 만들기'로 합침(옛 주소 호환)
  { path: "/places", component: PlacesPage, meta: { title: "내 장소" } },
  { path: "/logs", component: LogsPage, meta: { title: "실행 로그" } },
  { path: "/logs/:sid", component: LogDetailPage, props: true, meta: { title: "실행 로그 상세" } },
  { path: "/:rest(.*)*", component: NotFound, meta: { title: "없는 페이지" } },
];

const router = createRouter({ history: createWebHashHistory(), routes, scrollBehavior: () => ({ top: 0 }) });
router.afterEach((to) => {
  document.title = `${to.meta.title} · 이동 플래너`;
  requestAnimationFrame(() => document.getElementById("main")?.focus({ preventScroll: true }));
});

const App = {
  components: { IntroGuide },
  setup() {
    const introOpen = ref(!introHiddenToday() && (location.hash === "" || location.hash === "#/"));
    // 안내는 대화 화면의 요소를 비추므로, 다른 페이지에서 누르면 대화 화면으로 옮긴 뒤 연다
    async function openIntro() {
      if (router.currentRoute.value.path !== "/") await router.push("/");
      introOpen.value = false;
      setTimeout(() => (introOpen.value = true), 0);
    }
    const missing = computed(() => (store.status ? Object.entries(store.status.keys).filter(([, v]) => !v).map(([k]) => k) : []));
    const quota = computed(() => {
      const q = store.status?.quota || {};
      return store.status
        ? `모델 ${store.status.model} · ODsay 오늘 ${q.odsay?.used ?? "?"}/${q.odsay?.limit ?? "?"}회 · ITS 이번 달 ${q.its?.used ?? "?"}/${q.its?.limit ?? "?"}회`
        : "";
    });
    // 로그인: 로그인이 필수인데 안 했으면 로그인 화면만 보여 준다(데이터 API는 서버가 401로 막음)
    const needLogin = computed(() => !!store.auth && store.auth.auth_required && !store.auth.user);
    const loginUrl = API_BASE + "/auth/google/login";
    async function logout() {
      try { await api("/auth/logout", { method: "POST", body: {} }); } catch { /* 이미 만료 */ }
      location.reload();
    }
    window.addEventListener("rp:unauthorized", loadMe);
    onMounted(async () => { await loadMe(); loadStatus(); if (!needLogin.value) loadPlaces(); });
    return { store, missing, quota, introOpen, openIntro, needLogin, loginUrl, logout };
  },
  template: `
    <a href="#main" class="skip">본문으로 건너뛰기</a>
    <header class="topbar">
      <router-link to="/" class="brand">
        <h1>이동 플래너</h1>
        <p>확인한 시간표·요금으로만 계획하는 Agent</p>
      </router-link>
      <nav class="nav" aria-label="주 메뉴">
        <router-link to="/" exact-active-class="active">대화</router-link>
        <router-link to="/places" active-class="active" data-tour="places">내 장소</router-link>
        <router-link to="/plans" active-class="active" data-tour="plans">이동 계획</router-link>
        <router-link to="/logs" active-class="active" data-tour="logs">실행 로그</router-link>
        <button type="button" class="nav-intro" data-tour="help" @click="openIntro">소개</button>
        <span v-if="store.auth && store.auth.user" class="user-box" data-tour="user">
          <img v-if="store.auth.user.picture" :src="store.auth.user.picture" alt="" referrerpolicy="no-referrer">
          <span class="user-name">{{ store.auth.user.name || store.auth.user.email }}</span>
          <button type="button" class="ghost small" @click="logout">로그아웃</button>
        </span>
        <a v-else-if="store.auth && store.auth.google_configured" class="button small login-link" :href="loginUrl" data-tour="user">Google로 로그인</a>
      </nav>
    </header>
    <div v-if="store.statusError" class="banner">{{ store.statusError }}</div>
    <div v-else-if="missing.length" class="banner">API 키가 설정되지 않았어요: {{ missing.join(', ') }} — .env 파일을 확인해 주세요.</div>
    <div class="quota" aria-live="polite"><span data-tour="quota">{{ quota }}</span></div>
    <main v-if="needLogin" id="main" tabindex="-1" class="login-page">
      <section class="login-card">
        <h2>로그인이 필요해요</h2>
        <p class="hint">저장한 장소·이동 계획·실행 로그는 계정마다 따로 보관돼요. Google 계정으로 로그인해 주세요.</p>
        <a v-if="store.auth.google_configured" class="button google-btn" :href="loginUrl">Google 계정으로 로그인</a>
        <p v-else class="notice bad">Google 로그인이 아직 설정되지 않았어요(.env의 GOOGLE_CLIENT_ID·SECRET).</p>
      </section>
    </main>
    <main v-else id="main" tabindex="-1"><router-view /></main>
    <IntroGuide v-if="!needLogin" :open="introOpen" @close="introOpen = false" />
    <div class="toasts" aria-live="polite">
      <div v-for="t in store.toasts" :key="t.id" class="toast" :class="t.kind">
        {{ t.text }} <router-link v-if="t.link" :to="t.link.to">{{ t.link.text }}</router-link>
      </div>
    </div>`,
};

createApp(App).use(router).mount("#app");
