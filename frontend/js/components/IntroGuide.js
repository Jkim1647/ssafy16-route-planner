// 첫 방문 안내(코치마크): 화면을 어둡게 하고 실제 요소를 하나씩 비추며 그 옆에 설명을 띄운다.
// "오늘 하루 보지 않기"는 브라우저에 오늘 날짜만 기억한다(저장 불가 환경이면 매번 보임).
// 대상은 템플릿의 data-tour 속성으로 찾고, 화면에 없는 대상(대화 시작 뒤 사라진 예시 등)은 건너뛴다.
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";

const KEY = "rp.introHiddenOn";
const today = () => new Date().toLocaleDateString("sv-SE");  // YYYY-MM-DD(로컬 날짜)

export function introHiddenToday() {
  try { return localStorage.getItem(KEY) === today(); } catch { return false; }
}
function hideToday() {
  try { localStorage.setItem(KEY, today()); } catch { /* 저장 불가 환경 */ }
}

const STEPS = [
  { target: "ask", title: "조건을 말하듯이 입력해요",
    body: "어디서 어디로, 언제까지(또는 언제부터), 얼마 이하로. 예: \"토요일 2시까지 첨단동에서 강남역, 6만원 이하\"" },
  { target: "examples", title: "처음이라면 예시를 눌러 보세요", body: "예시 질문을 누르면 바로 경로를 찾아요. 규정(환불 위약금) 질문도 할 수 있어요." },
  { target: "why", title: "길찾기 앱과 다른 점", body: "도착 마감·예산·내 캘린더 일정을 함께 따지고, 도착 시각에서 거꾸로 나갈 시각을 계산해요." },
  { target: "side", title: "지도와 실행 과정", body: "찾은 경로는 노선 색으로 지도에 그려요. '실행 과정'에서는 Agent가 어떤 순서로 무엇을 조회하고 판단했는지 볼 수 있어요." },
  { target: "trip", title: "여러 곳을 한꺼번에", body: "집 → 교육장 → 약속 장소처럼 들를 곳을 순서대로 놓고(끌어서 순서 변경) 한 번에 찾아요. 앞 구간 도착 + 머무는 시간이 다음 출발 시각이 돼요." },
  { target: "places", title: "자주 가는 곳은 이름으로", body: "집·교육장을 저장해 두면 대화에서 \"집에서 교육장까지\"처럼 말하거나 여러 동선에서 바로 고를 수 있어요." },
  { target: "plans", title: "고른 경로는 이동 계획으로", body: "경로 카드의 '이 경로로 저장'으로 저장하고, 여기서 수정·삭제·캘린더 등록을 해요. 겹치는 계획은 알려 줘요." },
  { target: "logs", title: "판단 기록과 이상 징후", body: "요청마다 단계·Tool 호출·재계획이 기록되고, 반복 호출이나 과도한 재계획은 이상 징후로 표시돼요." },
  { target: "quota", title: "외부 API 사용량", body: "무료 한도가 작은 API(대중교통 하루 30회 등)는 사용량을 보여 주고 한도 안에서만 불러요." },
  { target: "help", title: "언제든 다시 보기", body: "이 안내는 '소개' 버튼으로 다시 볼 수 있어요." },
];

export default {
  name: "IntroGuide",
  props: { open: Boolean },
  emits: ["close"],
  setup(props, { emit }) {
    const steps = ref([]);    // 지금 화면에 있는 대상만
    const i = ref(0);
    const rect = ref(null);
    const tip = ref(null);
    const tipPos = ref({ top: 0, left: 0, place: "below" });
    const dontShow = ref(false);
    const step = computed(() => steps.value[i.value]);
    const last = computed(() => i.value === steps.value.length - 1);

    const el = (s) => document.querySelector(`[data-tour="${s.target}"]`);
    const visible = (e) => e && e.offsetParent !== null && e.getBoundingClientRect().width > 0;

    async function measure() {
      if (!props.open || !step.value) return;
      const e = el(step.value);
      if (!visible(e)) return;
      const r = e.getBoundingClientRect();
      rect.value = { top: r.top - 6, left: r.left - 6, width: r.width + 12, height: r.height + 12 };
      await nextTick();
      const tw = tip.value ? tip.value.offsetWidth : 320, th = tip.value ? tip.value.offsetHeight : 160;
      const below = r.bottom + 14 + th < window.innerHeight;
      const place = below ? "below" : r.top - 14 - th > 0 ? "above" : "below";
      const top = place === "below" ? r.bottom + 14 : r.top - 14 - th;
      const left = Math.min(Math.max(12, r.left + r.width / 2 - tw / 2), window.innerWidth - tw - 12);
      tipPos.value = { top: Math.max(12, top), left, place, arrow: Math.min(Math.max(16, r.left + r.width / 2 - left), tw - 16) };
    }
    async function go(n) {
      i.value = n;
      const e = step.value && el(step.value);
      if (e) e.scrollIntoView({ block: "center", behavior: "instant" });
      await nextTick();
      requestAnimationFrame(measure);
    }
    function start() {
      steps.value = STEPS.filter((s) => visible(el(s)));
      if (!steps.value.length) { emit("close"); return; }
      go(0);
    }
    function close() {
      if (dontShow.value) hideToday();
      rect.value = null;
      emit("close");
    }
    const next = () => (last.value ? close() : go(i.value + 1));
    const prev = () => i.value > 0 && go(i.value - 1);
    function onKey(e) {
      if (!props.open) return;
      if (e.key === "Escape") close();
      else if (e.key === "ArrowRight") next();
      else if (e.key === "ArrowLeft") prev();
    }
    const onResize = () => requestAnimationFrame(measure);

    watch(() => props.open, (v) => { if (v) setTimeout(start, 300); });  // 페이지가 그려진 뒤 대상 측정
    onMounted(() => {
      window.addEventListener("keydown", onKey);
      window.addEventListener("resize", onResize);
      window.addEventListener("scroll", onResize, true);
      if (props.open) setTimeout(start, 400);
    });
    onBeforeUnmount(() => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("resize", onResize);
      window.removeEventListener("scroll", onResize, true);
    });
    return { steps, i, step, last, rect, tip, tipPos, dontShow, next, prev, close };
  },
  template: `
    <div v-if="open && rect && step" class="tour" role="dialog" aria-modal="true" aria-labelledby="tour-title">
      <div class="tour-block" @click="close"></div>
      <div class="tour-spot" :style="{ top: rect.top + 'px', left: rect.left + 'px', width: rect.width + 'px', height: rect.height + 'px' }"></div>
      <section ref="tip" class="tour-tip" :class="tipPos.place" :style="{ top: tipPos.top + 'px', left: tipPos.left + 'px' }">
        <span class="tour-arrow" :style="{ left: tipPos.arrow + 'px' }" aria-hidden="true"></span>
        <p class="tour-count">{{ i + 1 }} / {{ steps.length }}</p>
        <h2 id="tour-title">{{ step.title }}</h2>
        <p class="tour-body">{{ step.body }}</p>
        <footer class="tour-foot">
          <label class="check"><input type="checkbox" v-model="dontShow"> 오늘 하루 보지 않기</label>
          <div class="actions">
            <button type="button" class="ghost small" @click="close">건너뛰기</button>
            <button v-if="i > 0" type="button" class="ghost small" @click="prev">이전</button>
            <button type="button" class="small" @click="next">{{ last ? '시작하기' : '다음' }}</button>
          </div>
        </footer>
      </section>
    </div>`,
};
