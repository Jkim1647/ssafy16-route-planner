// 첫 방문 소개(단계별 넘김). "오늘 하루 보지 않기"는 브라우저에 오늘 날짜만 기억한다(저장 불가 환경이면 매번 보임).
import { computed, onBeforeUnmount, onMounted, ref, watch, nextTick } from "vue";
import ModeIcon from "./ModeIcon.js";
import { RouteBar } from "./common.js";

const KEY = "rp.introHiddenOn";
const today = () => new Date().toLocaleDateString("sv-SE");  // YYYY-MM-DD(로컬 날짜)

export function introHiddenToday() {
  try { return localStorage.getItem(KEY) === today(); } catch { return false; }
}
function hideToday() {
  try { localStorage.setItem(KEY, today()); } catch { /* 저장 불가 환경 */ }
}

// 소개용 예시 구간(실제 조회 결과 형태와 같은 모양)
const SAMPLE_LEGS = [
  { mode: "walk", minutes: 8 }, { mode: "bus", name: "1002", minutes: 29, line_code: 15 }, { mode: "walk", minutes: 2 },
  { mode: "train", name: "KTX-산천", minutes: 117, source: "tago_train" }, { mode: "walk", minutes: 6 },
  { mode: "subway", name: "수도권 수인.분당선", minutes: 12 }, { mode: "walk", minutes: 2 },
  { mode: "subway", name: "수도권 2호선", minutes: 3 }, { mode: "walk", minutes: 1 },
];

const STEPS = [
  { title: "말하듯이 조건을 한 번에", body: "어디서 어디로, 언제까지, 얼마 이하로. 회의·약속 같은 내 일정도 함께 따져요.", art: "ask" },
  { title: "도착 시각에서 거꾸로 계산해요", body: "문 앞에서 문 앞까지 버스·열차·지하철을 이어 붙여, 몇 시에 집을 나서야 하는지 알려 줘요.", art: "timeline" },
  { title: "고른 이유와 뺀 이유를 보여 줘요", body: "마감까지 여유, 남는 예산, 일정 겹침 여부를 경로마다 표시하고, 맞는 게 없으면 다시 찾아요.", art: "checks" },
  { title: "지도로 확인하고 계획으로 저장", body: "노선 색으로 동선을 보고, 고른 경로를 이동 계획으로 저장해 캘린더에 넣을 수 있어요.", art: "map" },
  { title: "확인한 값만 써요", body: "시간표·요금은 공공·지도 API로 확인한 값만 쓰고, 좌석·실시간 지연처럼 확인할 수 없는 건 그렇다고 밝혀요.", art: "trust" },
];

export default {
  name: "IntroGuide",
  components: { ModeIcon, RouteBar },
  props: { open: Boolean },
  emits: ["close"],
  setup(props, { emit }) {
    const i = ref(0);
    const dontShow = ref(false);
    const dialog = ref(null);
    const step = computed(() => STEPS[i.value]);
    const last = computed(() => i.value === STEPS.length - 1);

    function close() {
      if (dontShow.value) hideToday();
      emit("close");
    }
    function next() { last.value ? close() : i.value++; }
    function prev() { if (i.value > 0) i.value--; }
    function onKey(e) {
      if (!props.open) return;
      if (e.key === "Escape") close();
      else if (e.key === "ArrowRight") next();
      else if (e.key === "ArrowLeft") prev();
    }
    watch(() => props.open, (v) => { if (v) { i.value = 0; nextTick(() => dialog.value && dialog.value.focus()); } });
    onMounted(() => { window.addEventListener("keydown", onKey); if (props.open) nextTick(() => dialog.value && dialog.value.focus()); });
    onBeforeUnmount(() => window.removeEventListener("keydown", onKey));
    return { i, step, last, dontShow, dialog, STEPS, SAMPLE_LEGS, next, prev, close };
  },
  template: `
    <div v-if="open" class="intro-backdrop" @click.self="close">
      <section ref="dialog" class="intro-dialog" role="dialog" aria-modal="true" aria-labelledby="intro-title" tabindex="-1">
        <header class="intro-head">
          <span class="intro-count">{{ i + 1 }} / {{ STEPS.length }}</span>
          <button type="button" class="ghost small" @click="close" aria-label="소개 닫기">건너뛰기</button>
        </header>

        <div class="intro-art" aria-hidden="true">
          <span class="art-label">예시 화면</span>
          <template v-if="step.art === 'ask'">
            <div class="art-bubble">토요일 오후 2시까지 광주 첨단동에서 서울 강남역, 6만원 이하</div>
            <div class="art-tags"><span>마감 14:00</span><span>예산 60,000원</span><span>내 일정 확인</span></div>
          </template>
          <template v-else-if="step.art === 'timeline'">
            <div class="art-times"><b>09:42</b> 출발 <span>→</span> <b>13:24</b> 도착 <em>마감 14:00</em></div>
            <RouteBar :legs="SAMPLE_LEGS" />
            <div class="art-modes"><ModeIcon mode="walk" :size="18" /><ModeIcon mode="bus" :size="18" /><ModeIcon mode="train" :size="18" /><ModeIcon mode="subway" :size="18" /></div>
          </template>
          <template v-else-if="step.art === 'checks'">
            <ul class="checks art-checks">
              <li><span class="ok-mark">✓</span>마감 14:00까지 여유 36분</li>
              <li><span class="ok-mark">✓</span>예산 60,000원 중 16,800원 남음</li>
              <li><span class="ok-mark">✓</span>그날 일정 1건과 안 겹침</li>
            </ul>
            <p class="decision">후보 71개 검토 → 6개 조건 통과 · 제외: 마감 초과 47 · 일정 겹침 18</p>
          </template>
          <template v-else-if="step.art === 'map'">
            <svg viewBox="0 0 320 140" class="art-map">
              <rect width="320" height="140" rx="10" fill="#eef1ee"/>
              <polyline points="30,115 60,100 80,80" fill="none" stroke="#E60012" stroke-width="4"/>
              <line x1="80" y1="80" x2="230" y2="35" stroke="#1f5f4a" stroke-width="6"/>
              <polyline points="230,35 255,45 265,60" fill="none" stroke="#F5A200" stroke-width="4"/>
              <polyline points="265,60 285,55 295,40" fill="none" stroke="#00A84D" stroke-width="4"/>
              <circle cx="30" cy="115" r="7" fill="#3d4fa1"/><circle cx="295" cy="40" r="7" fill="#a1302b"/>
            </svg>
            <div class="art-tags"><span>저장</span><span>캘린더 등록</span><span>겹치는 계획 알림</span></div>
          </template>
          <template v-else>
            <div class="art-trust"><span>공공데이터·지도 API</span><span class="arrow">→</span><span>규칙 계산</span><span class="arrow">→</span><span>LLM은 이해·설명만</span></div>
            <p class="hint">좌석 잔여·실시간 지연: 확인 불가로 안내</p>
          </template>
        </div>

        <h2 id="intro-title">{{ step.title }}</h2>
        <p class="intro-body">{{ step.body }}</p>

        <div class="intro-dots" role="tablist" aria-label="소개 단계">
          <button v-for="(s, n) in STEPS" :key="n" type="button" role="tab" :aria-selected="n === i"
                  :aria-label="(n + 1) + '단계: ' + s.title" :class="{ on: n === i }" @click="i = n"></button>
        </div>

        <footer class="intro-foot">
          <label class="check"><input type="checkbox" v-model="dontShow"> 오늘 하루 보지 않기</label>
          <div class="actions">
            <button type="button" class="ghost" :disabled="i === 0" @click="prev">이전</button>
            <button type="button" @click="next">{{ last ? '시작하기' : '다음' }}</button>
          </div>
        </footer>
      </section>
    </div>`,
};
