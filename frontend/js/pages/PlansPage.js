// 이동 계획 목록: 날짜별로 묶어 보여 주고, 다가오는/지난 계획을 거르고 검색한다. 행을 누르면 상세 페이지.
import { computed, onMounted, ref } from "vue";
import { api } from "../api.js";
import { dateLabel, legLabel, won } from "../format.js";

const todayIso = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};

export default {
  name: "PlansPage",
  setup() {
    const plans = ref([]);
    const loading = ref(true);
    const error = ref("");
    const filter = ref("upcoming");
    const q = ref("");

    async function load() {
      loading.value = true;
      try {
        plans.value = await api("/plans");
        error.value = "";
      } catch (e) {
        error.value = e.message;
      } finally {
        loading.value = false;
      }
    }

    const groups = computed(() => {
      const t = todayIso();
      const words = q.value.trim().toLowerCase();
      const rows = plans.value.filter((p) =>
        (filter.value === "all" || (filter.value === "upcoming" ? p.date >= t : p.date < t)) &&
        (!words || `${p.title} ${p.origin_name} ${p.destination_name}`.toLowerCase().includes(words)));
      const by = new Map();
      for (const p of rows) by.set(p.date, [...(by.get(p.date) || []), p]);
      return [...by.entries()].map(([date, items]) => ({ date, items }));
    });
    const counts = computed(() => {
      const t = todayIso();
      return { upcoming: plans.value.filter((p) => p.date >= t).length, past: plans.value.filter((p) => p.date < t).length,
        all: plans.value.length };
    });
    const summary = (p) => (p.legs || []).map((l) => (l.mode === "train" ? l.name : legLabel(l).split(" ")[0])).filter(Boolean).join(" · ");

    onMounted(load);
    return { plans, loading, error, filter, q, groups, counts, load, dateLabel, won, summary };
  },
  template: `
    <section class="page">
      <div class="page-head">
        <div>
          <h2>이동 계획</h2>
          <p class="hint">저장한 이동 계획이에요. 줄을 누르면 지도와 구간을 자세히 볼 수 있어요.</p>
        </div>
        <button type="button" class="ghost" @click="load" :disabled="loading">새로고침</button>
      </div>
      <div class="toolbar">
        <div class="segmented" role="tablist" aria-label="기간">
          <button v-for="f in [['upcoming','다가오는'],['past','지난'],['all','전체']]" :key="f[0]" type="button" role="tab"
                  :aria-selected="filter === f[0]" :class="{ active: filter === f[0] }" @click="filter = f[0]">
            {{ f[1] }} <span class="count">{{ counts[f[0]] }}</span></button>
        </div>
        <label class="search"><span class="sr-only">검색</span>
          <input v-model="q" type="search" placeholder="제목·출발지·도착지 검색"></label>
      </div>
      <div v-if="error" class="notice">{{ error }}</div>
      <p v-else-if="loading" class="hint">불러오는 중…</p>
      <div v-else-if="!groups.length" class="empty-state">
        <p v-if="!plans.length">아직 저장한 이동 계획이 없어요.</p>
        <p v-else>조건에 맞는 계획이 없어요.</p>
        <router-link v-if="!plans.length" to="/" class="button">대화에서 경로 찾기</router-link>
      </div>
      <div v-for="g in groups" :key="g.date" class="plan-group">
        <h3>{{ dateLabel(g.date) }}</h3>
        <ul class="plan-list">
          <li v-for="p in g.items" :key="p.id">
            <router-link :to="'/plans/' + p.id" class="plan-row">
              <span class="times">{{ p.leave_at }} → {{ p.arrive_at }}</span>
              <span class="what"><strong>{{ p.title }}</strong><span class="basis">{{ summary(p) }}</span></span>
              <span class="fare">{{ won(p.total_fare) }}</span>
              <span class="tags"><span v-if="p.calendar_event_id" class="tag ok">캘린더</span>
                <span v-if="p.points && p.points.length" class="tag">지도</span></span>
              <span class="chev" aria-hidden="true">›</span>
            </router-link>
          </li>
        </ul>
      </div>
    </section>`,
};
