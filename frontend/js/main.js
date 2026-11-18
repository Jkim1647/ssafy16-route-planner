// 앱 시작: 라우터(주소별 페이지)와 상단바·상태 배너·알림.
import { createApp, computed, onMounted, ref } from "vue";
import { createRouter, createWebHashHistory } from "vue-router";
import { loadStatus, store } from "./store.js";
import ChatPage from "./pages/ChatPage.js";
import PlansPage from "./pages/PlansPage.js";
import PlanDetailPage from "./pages/PlanDetailPage.js";
import { LogDetailPage, LogsPage } from "./pages/LogsPage.js";
import IntroGuide, { introHiddenToday } from "./components/IntroGuide.js";

const NotFound = {
  template: `<section class="page empty-state"><p>없는 페이지예요.</p><router-link to="/" class="button">대화로 가기</router-link></section>`,
};

const routes = [
  { path: "/", component: ChatPage, meta: { title: "대화" } },
  { path: "/plans", component: PlansPage, meta: { title: "이동 계획" } },
  { path: "/plans/:id(\\d+)", component: PlanDetailPage, props: true, meta: { title: "이동 계획 상세" } },
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
    const introOpen = ref(!introHiddenToday());
    const missing = computed(() => (store.status ? Object.entries(store.status.keys).filter(([, v]) => !v).map(([k]) => k) : []));
    const quota = computed(() => {
      const q = store.status?.quota || {};
      return store.status
        ? `모델 ${store.status.model} · ODsay 오늘 ${q.odsay?.used ?? "?"}/${q.odsay?.limit ?? "?"}회 · ITS 이번 달 ${q.its?.used ?? "?"}/${q.its?.limit ?? "?"}회`
        : "";
    });
    onMounted(loadStatus);
    return { store, missing, quota, introOpen };
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
        <router-link to="/plans" active-class="active">이동 계획</router-link>
        <router-link to="/logs" active-class="active">실행 로그</router-link>
        <button type="button" class="nav-intro" @click="introOpen = true">소개</button>
      </nav>
    </header>
    <div v-if="store.statusError" class="banner">{{ store.statusError }}</div>
    <div v-else-if="missing.length" class="banner">API 키가 설정되지 않았어요: {{ missing.join(', ') }} — .env 파일을 확인해 주세요.</div>
    <div class="quota" aria-live="polite">{{ quota }}</div>
    <main id="main" tabindex="-1"><router-view /></main>
    <IntroGuide :open="introOpen" @close="introOpen = false" />
    <div class="toasts" aria-live="polite">
      <div v-for="t in store.toasts" :key="t.id" class="toast" :class="t.kind">
        {{ t.text }} <router-link v-if="t.link" :to="t.link.to">{{ t.link.text }}</router-link>
      </div>
    </div>`,
};

createApp(App).use(router).mount("#app");
