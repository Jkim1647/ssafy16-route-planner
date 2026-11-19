// 다가오는 일정으로 경로 제안: 장소가 있는 캘린더 일정을 보여 주고, 누르면 질문 만들기 패널에 '집 → 그 장소, 일정 시각까지'를 채운다.
// 경로 계산·LLM은 사용자가 패널에서 보낼 때만 한다.
import { onMounted, ref } from "vue";
import { api } from "../api.js";
import { dateLabel } from "../format.js";
import { store } from "../store.js";

let cache = null;  // 한 번 불러온 제안은 화면을 오가도 다시 부르지 않는다

export default {
  name: "CalendarSuggestions",
  setup() {
    const items = ref(cache || []);
    onMounted(async () => {
      if (cache) return;
      try { cache = await api("/suggestions/calendar"); } catch { cache = []; }
      items.value = cache;
    });
    function use(s) {
      const b = store.builder;
      const home = store.places.find((p) => p.kind === "home");
      const stop = (p, extra) => ({ key: Date.now() + Math.random(), name: p.name, address: p.address, x: p.x, y: p.y,
        label: p.label || null, kind: p.kind || "pin", depart: "", arrive_by: "", stay_min: 0, ...extra });
      b.stops.splice(0, b.stops.length, ...(home ? [stop(home)] : []), stop(s.place, { arrive_by: s.arrive_by }));
      b.date = s.date;
      store.sidePanel = "builder";
    }
    return { items, use, dateLabel };
  },
  template: `
    <div v-if="items.length" class="cal-suggest" aria-label="다가오는 일정">
      <span class="hint">다가오는 일정</span>
      <ul>
        <li v-for="(s, i) in items" :key="i">
          <span class="when">{{ dateLabel(s.date) }} {{ s.arrive_by }}</span>
          <strong>{{ s.title }}</strong> <span class="basis">· {{ s.location }}</span>
          <button v-if="s.place" type="button" class="ghost small" @click="use(s)">경로 찾기</button>
          <span v-else class="basis">(장소를 찾지 못했어요)</span>
        </li>
      </ul>
    </div>`,
};
