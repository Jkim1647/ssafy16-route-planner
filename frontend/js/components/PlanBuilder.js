// 조건으로 질문 만들기: 내 장소를 끌어 놓고(또는 눌러서) 순서·날짜(달력)·시각(시계)·예산을 정한다.
// 두 곳이면 대화 Agent가 읽는 질문 문장을 만들고, 세 곳 이상이면 여러 동선 계산 요청을 만든다.
import { computed, ref } from "vue";
import { api } from "../api.js";
import { buildQuestion } from "../question.js";
import { store, toast } from "../store.js";
import { KIND_ICON } from "../pages/PlacesPage.js";
import TimeInput from "./TimeInput.js";

const MAX_STOPS = 6;
const iso = (d) => d.toLocaleDateString("sv-SE");
let seq = 0;

export default {
  name: "PlanBuilder",
  components: { TimeInput },
  props: { busy: Boolean },
  emits: ["question", "trip"],
  setup(props, { emit }) {
    const b = store.builder;
    const q = ref("");
    const found = ref([]);
    const dragFrom = ref(null);   // 목록 안에서 옮기는 중인 순서
    const dragPlace = ref(null);  // 내 장소 칩을 끌어오는 중
    const overIndex = ref(null);

    function stopOf(p) {
      return { key: ++seq, name: p.name, address: p.address, x: p.x, y: p.y, label: p.label || null,
        kind: p.kind || "pin", depart: "", arrive_by: "", stay_min: 0 };
    }
    function add(p, at = b.stops.length) {
      if (b.stops.length >= MAX_STOPS) { toast(`최대 ${MAX_STOPS}곳까지 넣을 수 있어요.`, "warn"); return; }
      b.stops.splice(at, 0, stopOf(p));
      found.value = []; q.value = "";
    }
    async function search() {
      if (!q.value.trim()) return;
      try { found.value = await api(`/places/search?q=${encodeURIComponent(q.value.trim())}`); } catch (e) { toast(e.message, "bad"); }
    }
    function move(i, d) {
      const j = i + d;
      if (j < 0 || j >= b.stops.length) return;
      b.stops.splice(j, 0, b.stops.splice(i, 1)[0]);
    }
    const remove = (i) => b.stops.splice(i, 1);
    function drop(i) {  // i: 놓은 자리(목록 끝이면 길이)
      if (dragPlace.value) add(dragPlace.value, i);
      else if (dragFrom.value !== null && dragFrom.value !== i) {
        const s = b.stops.splice(dragFrom.value, 1)[0];
        b.stops.splice(Math.min(i, b.stops.length), 0, s);
      }
      dragFrom.value = null; dragPlace.value = null; overIndex.value = null;
    }
    function clear() { b.stops.splice(0); }
    // Firefox는 dataTransfer에 값을 넣어야 끌기를 시작한다
    function startDrag(e, text) { e.dataTransfer.effectAllowed = "copyMove"; e.dataTransfer.setData("text/plain", text); }

    const question = computed(() => buildQuestion(
      { date: b.date, stops: b.stops, budget: b.budget ? Number(b.budget) : null, priority: b.priority }, iso(new Date())));
    const isTrip = computed(() => b.stops.length >= 3);
    const tripReady = computed(() => isTrip.value && (b.stops[0].depart || b.stops[1].arrive_by));

    // 보내면 패널을 접어 결과가 보이게 한다(조건은 남아 있어 다시 펼쳐 고칠 수 있음)
    function useQuestion(sendNow) {
      if (!question.value.ok) return;
      if (sendNow) b.open = false;
      emit("question", question.value.text, sendNow);
    }
    function runTrip() {
      b.open = false;
      emit("trip", {
        date: b.date, depart_after: b.stops[0].depart || null, priority: b.priority,
        budget: b.budget ? Number(b.budget) : null,
        stops: b.stops.map((s) => ({ name: s.label ? `${s.label}(${s.name})` : s.name, address: s.address, x: s.x, y: s.y,
          arrive_by: s.arrive_by || null, stay_min: Number(s.stay_min) || 0 })),
      }, b.stops.map((s) => s.label || s.name).join(" → "));
    }
    return { b, store, q, found, dragFrom, dragPlace, overIndex, question, isTrip, tripReady, MAX_STOPS, KIND_ICON,
      add, search, move, remove, drop, clear, startDrag, useQuestion, runTrip };
  },
  template: `
    <details class="builder" :open="b.open" @toggle="b.open = $event.target.open" data-tour="builder">
      <summary>조건으로 질문 만들기 <span v-if="b.stops.length" class="badge">{{ b.stops.length }}곳</span></summary>
      <div class="builder-body">
        <!-- 넣을 곳 고르기: 내 장소 칩(끌기·누르기)과 검색을 한 줄에 -->
        <div class="builder-source">
          <button v-for="p in store.places" :key="p.id" type="button" class="chip" draggable="true"
                  @dragstart="startDrag($event, p.label); dragPlace = p" @dragend="dragPlace = null; overIndex = null" @click="add(p)"
                  :disabled="b.stops.length >= MAX_STOPS">{{ KIND_ICON[p.kind] }} {{ p.label }}</button>
          <router-link v-if="!store.places.length" to="/places" class="hint">내 장소 저장하기</router-link>
          <form class="search-row" @submit.prevent="search">
            <label class="sr-only" for="builder-q">다른 장소 검색해 추가</label>
            <input id="builder-q" v-model="q" maxlength="50" placeholder="다른 장소 검색" :disabled="b.stops.length >= MAX_STOPS">
            <button type="submit" class="ghost small" :disabled="!q.trim() || b.stops.length >= MAX_STOPS">검색</button>
          </form>
        </div>
        <ul v-if="found.length" class="result-list">
          <li v-for="(r, i) in found" :key="i"><button type="button" class="result" @click="add(r)"><strong>{{ r.name }}</strong><span class="basis">{{ r.address }}</span></button></li>
        </ul>

        <ol class="stop-list" aria-label="들를 곳(순서)" @dragover.prevent @drop.prevent="drop(b.stops.length)">
          <li v-for="(s, i) in b.stops" :key="s.key" draggable="true"
              :class="{ dragging: dragFrom === i, over: overIndex === i }"
              @dragstart="startDrag($event, s.name); dragFrom = i" @dragend="dragFrom = null; overIndex = null"
              @dragover.prevent="overIndex = i" @drop.prevent.stop="drop(i)">
            <span class="grip" aria-hidden="true" title="끌어서 순서 바꾸기">⋮⋮</span>
            <span class="stop-no">{{ i + 1 }}</span>
            <span class="stop-main"><strong>{{ s.label ? KIND_ICON[s.kind] + ' ' + s.label : s.name }}</strong>
              <span class="basis">{{ s.label ? s.name : s.address }}</span></span>
            <span class="stop-opts">
              <TimeInput v-if="i === 0" label="출발 시각" v-model="s.depart" />
              <TimeInput v-else label="도착 마감" v-model="s.arrive_by" />
              <label v-if="i > 0 && i < b.stops.length - 1">머묾(분) <input type="number" min="0" max="720" step="10" v-model="s.stay_min"></label>
            </span>
            <span class="stop-move">
              <button type="button" class="ghost small" :disabled="i === 0" @click="move(i, -1)" :aria-label="(i + 1) + '번 위로'">↑</button>
              <button type="button" class="ghost small" :disabled="i === b.stops.length - 1" @click="move(i, 1)" :aria-label="(i + 1) + '번 아래로'">↓</button>
              <button type="button" class="danger small" @click="remove(i)" :aria-label="(i + 1) + '번 빼기'">✕</button>
            </span>
          </li>
          <li class="empty" :class="{ over: dragPlace && overIndex === null }">
            {{ b.stops.length ? '+ 끝에 추가' : '출발지부터 끌어 놓거나 눌러서 추가' }}</li>
        </ol>

        <!-- 공통 조건 한 줄 -->
        <div class="builder-opts">
          <input type="date" v-model="b.date" aria-label="날짜">
          <label class="with-unit"><input type="number" min="0" step="1000" v-model="b.budget" placeholder="예산" aria-label="예산(원)"><span>원</span></label>
          <select v-model="b.priority" aria-label="우선"><option value="cheapest">최저가</option><option value="fastest">최단 소요</option><option value="fewest_transfers">환승 최소</option></select>
          <button type="button" class="ghost small clear" @click="clear" :disabled="!b.stops.length">비우기</button>
        </div>

        <!-- 결과 줄: 만들어질 질문(또는 여러 동선 안내)과 실행 버튼 -->
        <div class="builder-run">
          <template v-if="isTrip">
            <p class="question-preview" :class="{ off: !tripReady }">{{ tripReady ? '구간 ' + (b.stops.length - 1) + '개를 차례로 찾아요(앞 도착 + 머묾 → 다음 출발)' : '출발 시각이나 첫 도착 마감을 넣어 주세요' }}</p>
            <button type="button" :disabled="busy || !tripReady" @click="runTrip">길찾기</button>
          </template>
          <template v-else>
            <p class="question-preview" :class="{ off: !question.ok }">{{ question.ok ? '“' + question.text + '”' : question.reason }}</p>
            <button type="button" class="ghost" :disabled="!question.ok" @click="useQuestion(false)" title="입력창에 넣고 고치기">고치기</button>
            <button type="button" :disabled="busy || !question.ok" @click="useQuestion(true)">이 질문 보내기</button>
          </template>
        </div>
      </div>
    </details>`,
};
