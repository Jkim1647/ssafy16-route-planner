// 여러 동선: 지점을 순서대로 놓고(드래그 앤 드롭·↑↓) 한꺼번에 길찾기. 구간마다 기존 판단을 그대로 쓰고 LLM은 쓰지 않는다.
import { computed, onMounted, ref } from "vue";
import { api } from "../api.js";
import { dateLabel, mins, won } from "../format.js";
import { loadPlaces, store, toast } from "../store.js";
import RouteMap from "../components/RouteMap.js";
import { RouteCard } from "../components/common.js";
import { KIND_ICON } from "./PlacesPage.js";

const iso = (d) => d.toLocaleDateString("sv-SE");
let seq = 0;

export default {
  name: "TripPage",
  components: { RouteMap, RouteCard },
  setup() {
    const tomorrow = new Date(Date.now() + 86400000);
    const date = ref(iso(tomorrow));
    const departAfter = ref("08:00");
    const budget = ref("");
    const priority = ref("cheapest");
    const stops = ref([]);
    const q = ref("");
    const found = ref([]);
    const busy = ref(false);
    const result = ref(null);
    const error = ref("");
    const sel = ref({ leg: 0, card: 0 });
    const dragFrom = ref(null);
    const seconds = ref(0);

    function add(p) {
      stops.value.push({ key: ++seq, name: p.name, address: p.address, x: p.x, y: p.y, label: p.label || null,
        kind: p.kind || "pin", arrive_by: "", stay_min: 0 });
      found.value = [];
      q.value = "";
    }
    async function search() {
      if (!q.value.trim()) return;
      try { found.value = await api(`/places/search?q=${encodeURIComponent(q.value.trim())}`); } catch (e) { toast(e.message, "bad"); }
    }
    const move = (i, d) => {
      const j = i + d;
      if (j < 0 || j >= stops.value.length) return;
      const s = stops.value.splice(i, 1)[0];
      stops.value.splice(j, 0, s);
    };
    const remove = (i) => stops.value.splice(i, 1);
    function onDrop(i) {
      if (dragFrom.value === null || dragFrom.value === i) return;
      const s = stops.value.splice(dragFrom.value, 1)[0];
      stops.value.splice(i, 0, s);
      dragFrom.value = null;
    }

    async function run() {
      busy.value = true; error.value = ""; result.value = null; seconds.value = 0;
      const timer = setInterval(() => seconds.value++, 1000);
      try {
        result.value = await api("/trips/plan", { method: "POST", body: {
          date: date.value, depart_after: departAfter.value || null, priority: priority.value,
          budget: budget.value ? Number(budget.value) : null,
          stops: stops.value.map((s) => ({ name: s.label ? `${s.label}(${s.name})` : s.name, address: s.address,
            x: s.x, y: s.y, arrive_by: s.arrive_by || null, stay_min: Number(s.stay_min) || 0 })) } });
        const first = result.value.legs.findIndex((l) => l.cards && l.cards.length);
        sel.value = { leg: Math.max(first, 0), card: 0 };
        loadStatusSafe();
      } catch (e) {
        error.value = e.message;
      } finally {
        clearInterval(timer);
        busy.value = false;
      }
    }
    function loadStatusSafe() { import("../store.js").then((m) => m.loadStatus()); }

    const selCard = computed(() => result.value?.legs[sel.value.leg]?.cards?.[sel.value.card] || null);

    async function saveAll() {
      const legs = result.value.legs.filter((l) => l.status === "done");
      let n = 0;
      for (const l of legs) {
        const c = l.cards[0];
        try {
          await api("/plans", { method: "POST", body: { title: `여러 동선 ${l.index}/${result.value.legs.length}: ${l.from} → ${l.to}`.slice(0, 100),
            date: c.date, leave_at: c.leave_at, arrive_at: c.arrive_at, origin_name: l.from.slice(0, 100), destination_name: l.to.slice(0, 100),
            legs: c.legs, total_fare: c.total_fare, points: c.points || [] } });
          n++;
        } catch (e) { toast(e.message, "bad"); }
      }
      if (n) toast(`구간 ${n}개를 이동 계획으로 저장했어요.`, "ok", { to: "/plans", text: "계획 보기" });
    }
    async function saveOne(card, leg) {
      try {
        await api("/plans", { method: "POST", body: { title: `${leg.from} → ${leg.to}`.slice(0, 100), date: card.date,
          leave_at: card.leave_at, arrive_at: card.arrive_at, origin_name: leg.from.slice(0, 100), destination_name: leg.to.slice(0, 100),
          legs: card.legs, total_fare: card.total_fare, points: card.points || [] } });
        toast("이 구간을 이동 계획으로 저장했어요.", "ok", { to: "/plans", text: "계획 보기" });
      } catch (e) { toast(e.message, "bad"); }
    }

    onMounted(loadPlaces);
    const canRun = computed(() => stops.value.length >= 2 && stops.value.length <= 6 && !busy.value);
    return { store, date, departAfter, budget, priority, stops, q, found, busy, result, error, sel, selCard, dragFrom, seconds,
      canRun, add, search, move, remove, onDrop, run, saveAll, saveOne, dateLabel, mins, won, KIND_ICON };
  },
  template: `
    <section class="page trip-page">
      <div class="page-head">
        <div>
          <h2>여러 동선</h2>
          <p class="hint">들를 곳을 순서대로 놓고 한꺼번에 찾아요. 끌어서 순서를 바꾸고, 곳마다 도착 마감이나 머무는 시간을 정할 수 있어요.
            앞 구간 도착 + 머무는 시간이 다음 구간의 출발 시각이 돼요.</p>
        </div>
      </div>
      <div class="trip-grid">
        <div class="panel">
          <div class="trip-opts">
            <label>날짜 <input type="date" v-model="date"></label>
            <label>첫 출발 <input type="time" v-model="departAfter"></label>
            <label>전체 예산(원) <input type="number" min="0" step="1000" v-model="budget" placeholder="선택"></label>
            <label>우선 <select v-model="priority"><option value="cheapest">최저가</option><option value="fastest">최단 소요</option><option value="fewest_transfers">환승 최소</option></select></label>
          </div>

          <div class="saved-chips" v-if="store.places.length">
            <span class="hint">내 장소</span>
            <button v-for="p in store.places" :key="p.id" type="button" class="chip" @click="add(p)" :disabled="stops.length >= 6">
              {{ KIND_ICON[p.kind] }} {{ p.label }}</button>
          </div>
          <p v-else class="hint">자주 가는 곳은 <router-link to="/places">내 장소</router-link>에 저장해 두면 바로 고를 수 있어요.</p>
          <form class="search-row" @submit.prevent="search">
            <label class="sr-only" for="trip-q">장소 검색해 추가</label>
            <input id="trip-q" v-model="q" maxlength="50" placeholder="장소 검색해 추가(예: 강남역)" :disabled="stops.length >= 6">
            <button type="submit" class="ghost" :disabled="!q.trim() || stops.length >= 6">검색</button>
          </form>
          <ul v-if="found.length" class="result-list">
            <li v-for="(r, i) in found" :key="i"><button type="button" class="result" @click="add(r)"><strong>{{ r.name }}</strong><span class="basis">{{ r.address }}</span></button></li>
          </ul>

          <ol class="stop-list" aria-label="들를 곳(순서)">
            <li v-for="(s, i) in stops" :key="s.key" draggable="true" :class="{ dragging: dragFrom === i }"
                @dragstart="dragFrom = i" @dragend="dragFrom = null" @dragover.prevent @drop.prevent="onDrop(i)">
              <span class="grip" aria-hidden="true" title="끌어서 순서 바꾸기">⋮⋮</span>
              <span class="stop-no">{{ i + 1 }}</span>
              <span class="stop-main"><strong>{{ s.label ? KIND_ICON[s.kind] + ' ' + s.label : s.name }}</strong>
                <span class="basis">{{ s.label ? s.name : s.address }}</span></span>
              <span v-if="i > 0" class="stop-opts">
                <label>도착 마감 <input type="time" v-model="s.arrive_by"></label>
                <label v-if="i < stops.length - 1">머묾(분) <input type="number" min="0" max="720" step="10" v-model="s.stay_min"></label>
              </span>
              <span v-else class="stop-opts basis">출발</span>
              <span class="stop-move">
                <button type="button" class="ghost small" :disabled="i === 0" @click="move(i, -1)" :aria-label="(i + 1) + '번 위로'">↑</button>
                <button type="button" class="ghost small" :disabled="i === stops.length - 1" @click="move(i, 1)" :aria-label="(i + 1) + '번 아래로'">↓</button>
                <button type="button" class="danger small" @click="remove(i)" :aria-label="(i + 1) + '번 빼기'">✕</button>
              </span>
            </li>
            <li v-if="!stops.length" class="empty">내 장소나 검색으로 두 곳 이상 추가하세요(최대 6곳).</li>
          </ol>
          <button type="button" class="run-trip" :disabled="!canRun" @click="run">
            {{ busy ? '찾는 중… ' + seconds + '초' : '한꺼번에 길찾기' }}</button>
          <p class="hint">구간마다 대중교통 조회를 쓰므로 구간이 많으면 하루 조회 한도에 닿을 수 있어요(넘으면 택시 기준으로 안내).</p>
          <p v-if="error" class="notice bad">{{ error }}</p>
        </div>

        <div class="panel trip-result">
          <template v-if="result">
            <div class="trip-summary">
              <strong>{{ result.start_at || '?' }} 출발 → {{ result.end_at || '?' }} 도착</strong>
              <span>총 {{ won(result.total_fare) }}</span>
              <button type="button" class="small" @click="saveAll" :disabled="!result.legs.some(l => l.status === 'done')">전체를 계획으로 저장</button>
            </div>
            <p v-for="w in result.warnings" :key="w" class="warn">⚠ {{ w }}</p>
            <RouteMap v-if="selCard" :points="selCard.points || []" :legs="selCard.legs" height="320px" />
            <ol class="leg-results">
              <li v-for="(l, li) in result.legs" :key="l.index" :class="l.status">
                <div class="leg-head">
                  <strong>{{ l.index }}구간 · {{ l.from }} → {{ l.to }}</strong>
                  <span class="basis">{{ l.depart_after ? l.depart_after + ' 이후 출발' : '' }}{{ l.arrive_by ? ' · ' + l.arrive_by + '까지 도착' : '' }}</span>
                </div>
                <p v-if="l.status !== 'done'" class="hint">{{ l.reason }}</p>
                <RouteCard v-for="(c, ci) in (l.cards || []).slice(0, 1)" :key="ci" :card="c" :selected="sel.leg === li && sel.card === ci"
                           @select="sel = { leg: li, card: ci }" @save="saveOne($event, l)" />
                <details v-if="l.cards && l.cards.length > 1" class="excluded">
                  <summary>다른 경로 {{ l.cards.length - 1 }}개</summary>
                  <RouteCard v-for="(c, ci) in l.cards.slice(1)" :key="ci" :card="c" :selected="sel.leg === li && sel.card === ci + 1"
                             @select="sel = { leg: li, card: ci + 1 }" @save="saveOne($event, l)" />
                </details>
              </li>
            </ol>
          </template>
          <div v-else class="empty-state"><p>들를 곳을 정하고 '한꺼번에 길찾기'를 누르면 구간별 결과가 여기에 나와요.</p></div>
        </div>
      </div>
    </section>`,
};
