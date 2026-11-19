// 출발 알림(화면): 1시간 안에 나가야 하는 계획을 상단에 띄우고, 허용하면 10분 전에 브라우저 알림을 한 번 보낸다.
// 화면이 열려 있을 때만 동작한다(서버 푸시 없음). 캘린더에 등록한 계획은 캘린더 앱의 15·5분 전 알림도 함께 온다.
import { onBeforeUnmount, onMounted, ref } from "vue";
import { api } from "../api.js";
import { notifyDue, notifyKey, upcomingDepartures } from "../reminder.js";

const SENT_KEY = "rp.notified";

function loadSent() {
  try { return new Set(JSON.parse(localStorage.getItem(SENT_KEY) || "[]")); } catch { return new Set(); }
}
function saveSent(sent) {
  try { localStorage.setItem(SENT_KEY, JSON.stringify([...sent].slice(-50))); } catch { /* 저장 불가 환경 */ }
}

export default {
  name: "DepartureBanner",
  setup() {
    const soon = ref([]);
    const canAsk = ref(typeof Notification !== "undefined" && Notification.permission === "default");
    let plans = [], timer = null, refresh = null;
    const sent = loadSent();

    async function load() {
      try { plans = await api("/plans"); } catch { plans = []; }
      tick();
    }
    function tick() {
      soon.value = upcomingDepartures(plans, new Date());
      if (typeof Notification === "undefined" || Notification.permission !== "granted") return;
      for (const u of soon.value) {
        if (!notifyDue(u, sent)) continue;
        new Notification(`${u.minutes}분 뒤 출발`, { body: `${u.plan.title} · ${u.plan.leave_at} 출발`, tag: notifyKey(u.plan) });
        sent.add(notifyKey(u.plan));
        saveSent(sent);
      }
    }
    async function ask() {
      try { await Notification.requestPermission(); } finally { canAsk.value = Notification.permission === "default"; tick(); }
    }
    onMounted(() => {
      load();
      timer = setInterval(tick, 30000);        // 남은 분 갱신
      refresh = setInterval(load, 5 * 60000);  // 다른 화면에서 저장·수정한 계획 반영
    });
    onBeforeUnmount(() => { clearInterval(timer); clearInterval(refresh); });
    return { soon, canAsk, ask };
  },
  template: `
    <div v-if="soon.length" class="departure" role="status" aria-live="polite">
      <span aria-hidden="true">⏰</span>
      <span v-for="u in soon" :key="u.plan.id" class="departure-item">
        <strong>{{ u.minutes ? u.minutes + '분 뒤' : '지금' }} 출발</strong>
        <router-link :to="'/plans/' + u.plan.id">{{ u.plan.title }} · {{ u.plan.leave_at }}</router-link>
      </span>
      <button v-if="canAsk" type="button" class="ghost small" @click="ask">10분 전에 알림 받기</button>
    </div>`,
};
