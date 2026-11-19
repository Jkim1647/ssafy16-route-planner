// 공유받은 계획(/s/:token): 로그인 없이 읽기 전용. 서버는 사용자·캘린더 정보를 빼고 보낸다.
import { computed, ref, watch } from "vue";
import { api } from "../api.js";
import { busTypeLabel, dateLabel, legColor, legLabel, mins, won } from "../format.js";
import RouteMap from "../components/RouteMap.js";
import ModeIcon from "../components/ModeIcon.js";
import { RouteBar } from "../components/common.js";

export default {
  name: "SharedPlanPage",
  components: { RouteMap, ModeIcon, RouteBar },
  props: { token: String },
  setup(props) {
    const plan = ref(null);
    const error = ref("");
    watch(() => props.token, async (t) => {
      plan.value = null; error.value = "";
      try { plan.value = await api(`/shared/${encodeURIComponent(t)}`); } catch (e) { error.value = e.message; }
    }, { immediate: true });
    const totalMin = computed(() => (plan.value?.legs || []).reduce((s, l) => s + (l.minutes || 0), 0));
    return { plan, error, totalMin, dateLabel, legColor, legLabel, mins, won, busTypeLabel };
  },
  template: `
    <section class="page">
      <p class="eyebrow">공유받은 이동 계획 · 읽기 전용</p>
      <div v-if="error" class="empty-state"><p>{{ error }}</p></div>
      <p v-else-if="!plan" class="hint">불러오는 중…</p>
      <template v-else>
        <div class="page-head"><div>
          <p class="eyebrow">{{ dateLabel(plan.date) }}</p>
          <h2>{{ plan.title }}</h2>
          <p class="big-times">{{ plan.leave_at }} 출발 → {{ plan.arrive_at }} 도착 · {{ won(plan.total_fare) }}</p>
        </div></div>
        <div class="detail-grid">
          <div class="panel">
            <p v-if="plan.home_hidden" class="hint">🔒 공유한 사람의 집 위치는 동네 수준으로만 보여요.</p>
            <RouteMap v-if="plan.points && plan.points.length" :points="plan.points" :legs="plan.legs" height="380px" />
            <p v-else class="hint">지도 정보가 없는 계획이에요.</p>
          </div>
          <div class="panel">
            <RouteBar class="detail-bar" :legs="plan.legs" />
            <ol class="leg-timeline">
              <li v-for="(l, i) in plan.legs" :key="i" :class="l.mode">
                <span class="step-icon" :style="{ background: legColor(l) }"><ModeIcon :mode="l.mode" :size="14" /></span>
                <span class="leg-name"><span v-if="busTypeLabel(l)" class="bus-type">{{ busTypeLabel(l) }}</span>{{ legLabel(l) }}</span>
                <span class="leg-min">{{ l.minutes ?? '?' }}분</span>
              </li>
            </ol>
            <p class="hint">구간 이동 합계 {{ mins(totalMin) }}(환승 대기 제외). 좌석·실시간 지연은 확인하지 않은 계획이에요.</p>
          </div>
        </div>
      </template>
    </section>`,
};
