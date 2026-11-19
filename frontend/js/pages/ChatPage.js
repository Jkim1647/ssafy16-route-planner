// 대화 페이지: 요청 → 경로 카드 + 지도 + 실행 과정. 페이지를 옮겨도 대화는 store에 남는다.
import { computed, nextTick, onBeforeUnmount, ref } from "vue";
import { api } from "../api.js";
import { elapsedMs } from "../format.js";
import { loadStatus, resetChat, setSession, store, toast } from "../store.js";
import RouteMap from "../components/RouteMap.js";
import { Excluded, RouteCard, TraceList } from "../components/common.js";
import PlanBuilder from "../components/PlanBuilder.js";
import TripResult from "../components/TripResult.js";
import TradeoffChart from "../components/TradeoffChart.js";
import CalendarSuggestions from "../components/CalendarSuggestions.js";

const EXAMPLES = [
  "토요일 오후 2시까지 광주 첨단동에서 서울 강남역, 6만원 이하",
  "내일 오후 6시까지 용산역에서 광주송정역, 환승 적게",
  "KTX 출발 30분 전에 반환하면 위약금 얼마야?",
];

export default {
  name: "ChatPage",
  components: { RouteMap, RouteCard, Excluded, TraceList, PlanBuilder, TripResult, TradeoffChart, CalendarSuggestions },
  setup() {
    const input = ref("");
    const inputEl = ref(null);
    const list = ref(null);
    const panel = ref(store.selected ? "map" : "trace");
    const seconds = ref(0);
    const savingKey = ref(null);
    let timer = null;

    const selectedMsg = computed(() => store.messages.find((m) => m.cards && m.cards.includes(store.selected)));
    const mapPoints = computed(() => (store.selected && store.selected.points) || []);
    const otherPoints = computed(() => (selectedMsg.value ? selectedMsg.value.cards : [])
      .filter((c) => c !== store.selected && c.points && c.points.length).map((c) => c.points));

    async function scrollDown() {
      await nextTick();
      if (list.value) list.value.scrollTop = list.value.scrollHeight;
    }

    async function send(text) {
      const msg = (text ?? input.value).trim();
      if (!msg || store.sending) return;
      input.value = "";
      store.messages.push({ role: "user", text: msg });
      store.sending = true;
      seconds.value = 0;
      timer = setInterval(() => seconds.value++, 1000);
      scrollDown();
      try {
        const r = await api("/chat", { method: "POST", body: { message: msg, session_id: store.sessionId } });
        setSession(r.session_id);
        const cond = r.events.find((e) => e.type === "node_end" && e.node === "analyze")?.payload?.conditions || null;
        const cards = r.cards.filter((c) => c.leave_at);
        store.messages.push({ role: "agent", text: r.reply, cards, conds: cond, decision: r.decision,
          sources: r.cards.filter((c) => c.type === "source"), excluded: r.excluded, undetermined: r.undetermined,
          estimated: r.estimated });
        store.lastEvents = r.events;
        store.lastMeta = `재계획 ${r.replan_count}회 · LLM ${r.llm_calls}회 · ${elapsedMs(r.events)}ms`;
        store.selected = cards[0] || null;
        panel.value = cards.length ? "map" : "trace";
        loadStatus();
      } catch (e) {
        store.messages.push({ role: "agent", text: e.message, error: true });
      } finally {
        clearInterval(timer);
        store.sending = false;
        scrollDown();
        nextTick(() => inputEl.value && inputEl.value.focus());
      }
    }

    async function save(card, conds) {
      const key = card.index + card.leave_at;
      savingKey.value = key;
      try {
        const r = await api("/plans", { method: "POST", body: {
          title: conds ? `${conds.origin} → ${conds.destination}` : `${card.leave_at} 출발 이동`,
          date: card.date, leave_at: card.leave_at, arrive_at: card.arrive_at,
          origin_name: conds?.origin || "-", destination_name: conds?.destination || "-",
          legs: card.legs, total_fare: card.total_fare, points: card.points || [] } });
        const overlap = r.overlaps.length
          ? ` 같은 날 겹치는 계획이 ${r.overlaps.length}건 있어요.` : "";
        toast(`이동 계획으로 저장했어요(${r.plan.date} ${r.plan.leave_at}~${r.plan.arrive_at}).${overlap}`,
          r.overlaps.length ? "warn" : "ok", { to: `/plans/${r.plan.id}`, text: "계획 보기" });
      } catch (e) {
        toast(e.message, "bad");
      } finally {
        savingKey.value = null;
      }
    }

    // 판단 요약: "후보 12개 검토 → 3개 통과 · 마감 초과 4 · 예산 초과 5 제외"
    function decisionText(d) {
      if (!d || !d.checked) return "";
      const LABEL = { 마감: "마감 초과", 예산: "예산 초과", 일정: "일정 겹침", "출발 시각": "출발 시각 전", 날씨: "비 회피" };
      const why = Object.entries(d.excluded_by || {}).sort((a, b) => b[1] - a[1])
        .map(([k, n]) => `${LABEL[k] || k} ${n}`).join(" · ");
      return `후보 ${d.checked}개 검토 → ${d.passed}개 조건 통과` + (why ? ` · 제외: ${why}` : "") +
        (d.dominated ? ` · 모든 면에서 더 나은 경로가 있는 ${d.dominated}개는 추천에서 뺌` : "") +
        (d.undetermined ? ` · 판단 불가 ${d.undetermined}` : "");
    }

    // 조건 패널이 만든 질문: 바로 보내거나 입력창에 넣어 고치게 한다
    function useQuestion(text, sendNow) {
      if (sendNow) { send(text); return; }
      input.value = text;
      nextTick(() => inputEl.value && inputEl.value.focus());
    }

    // 세 곳 이상: 대화 Agent는 한 구간만 다루므로 여러 동선 계산(LLM 없음)을 바로 부르고 결과를 대화에 붙인다
    async function runTrip(body, route) {
      if (store.sending) return;
      store.messages.push({ role: "user", text: `여러 동선: ${route} (${body.date})` });
      store.sending = true;
      seconds.value = 0;
      timer = setInterval(() => seconds.value++, 1000);
      scrollDown();
      try {
        const r = await api("/trips/plan", { method: "POST", body });
        const done = r.legs.filter((l) => l.status === "done").length;
        store.messages.push({ role: "agent", trip: r,
          text: done === r.legs.length ? `구간 ${r.legs.length}개를 모두 찾았어요. 구간마다 대표 경로를 보여 드려요.`
            : `구간 ${r.legs.length}개 중 ${done}개를 찾았어요. 못 찾은 구간은 이유를 확인해 주세요.` });
        store.selected = r.legs.find((l) => l.cards && l.cards.length)?.cards[0] || null;
        store.lastEvents = [];
        store.lastMeta = `여러 동선 · 구간 ${r.legs.length}개 · LLM 0회`;
        panel.value = store.selected ? "map" : "trace";
        loadStatus();
      } catch (e) {
        store.messages.push({ role: "agent", text: e.message, error: true });
      } finally {
        clearInterval(timer);
        store.sending = false;
        scrollDown();
      }
    }

    function select(card) { store.selected = card; panel.value = "map"; }
    function newChat() { resetChat(); panel.value = "trace"; }

    onBeforeUnmount(() => clearInterval(timer));
    scrollDown();
    if (store.pendingQuestion) {  // 계획 재확인·일정 제안에서 넘어온 질문은 바로 보낸다
      const q = store.pendingQuestion;
      store.pendingQuestion = "";
      nextTick(() => send(q));
    }
    return { store, input, inputEl, list, panel, seconds, savingKey, EXAMPLES, mapPoints, otherPoints,
      send, save, select, newChat, decisionText, useQuestion, runTrip };
  },
  template: `
    <section class="chat-page">
      <div class="chat-col">
        <div class="panel-head">
          <h2>대화</h2>
          <button type="button" class="ghost" @click="newChat" :disabled="store.sending">새 대화</button>
        </div>
        <div ref="list" class="messages" aria-live="polite">
          <div v-for="(m, i) in store.messages" :key="i" class="msg" :class="[m.role, { error: m.error }]">
            <p>{{ m.text }}</p>
            <p v-if="decisionText(m.decision)" class="decision">{{ decisionText(m.decision) }}</p>
            <template v-if="m.cards && m.cards.length">
              <TradeoffChart v-if="m.cards.length >= 2" :cards="m.cards" :selected="store.selected" @select="select" />
              <RouteCard v-for="c in m.cards" :key="c.index + c.leave_at" :card="c" :selected="c === store.selected"
                         :saving="savingKey === c.index + c.leave_at" @select="select" @save="save($event, m.conds)" />
            </template>
            <TripResult v-if="m.trip" :trip="m.trip" :selected="store.selected" @select="select" />
            <p v-for="s in m.sources || []" :key="s.title + s.page" class="hint">출처: {{ s.title }}<span v-if="s.page"> p.{{ s.page }}</span></p>
            <Excluded title="제외된 후보" :items="m.excluded" />
            <Excluded title="판단하지 않은 후보" :items="m.undetermined" />
            <Excluded title="추정 시간표(통과 아님)" :items="m.estimated" />
          </div>
          <div v-if="store.sending" class="msg agent pending" role="status">
            <p>경로를 계산하는 중이에요 · {{ seconds }}초</p>
            <p class="hint">조건 분석 → 시간표·구간 조회 → 마감·예산·일정 판단 순서로 진행해요. 보통 5~15초 걸려요.</p>
          </div>
        </div>
        <!-- 첫 화면 안내: 하는 일(한 줄 키워드)과 예시 질문을 한 상자에. 질문 만들기 패널을 펼치면 접는다 -->
        <section v-if="store.messages.length <= 1 && !store.sending && !store.builder.open" class="intro" aria-label="이 서비스가 하는 일">
          <ul class="intro-points" data-tour="why">
            <li title="도착 마감·예산·내 캘린더 일정을 함께 따져 맞는 경로만 남겨요">⏱ 마감·예산·일정을 한 번에</li>
            <li title="문 앞에서 문 앞까지 이어 붙여 몇 시에 나서야 하는지 알려 줘요">↩ 나갈 시각을 거꾸로</li>
            <li title="마감까지 여유·남는 예산을 보여 주고, 맞는 게 없으면 다시 찾아요">✓ 고른 이유·뺀 이유</li>
            <li title="시간표·요금은 공공·지도 API로 확인한 값만 쓰고, 좌석·지연은 확인 불가로 밝혀요">🔎 확인한 값만</li>
          </ul>
          <CalendarSuggestions />
          <div class="examples" data-tour="examples">
            <span class="hint">예시</span>
            <button v-for="ex in EXAMPLES" :key="ex" type="button" class="chip" @click="send(ex)">{{ ex }}</button>
          </div>
        </section>
        <PlanBuilder :busy="store.sending" @question="useQuestion" @trip="runTrip" />
        <form class="composer" @submit.prevent="send()" data-tour="ask">
          <label for="chat-input" class="sr-only">메시지</label>
          <input id="chat-input" ref="inputEl" v-model="input" autocomplete="off" maxlength="500" :disabled="store.sending"
                 placeholder="예) 내일 오후 6시까지 용산역에서 광주송정역, 환승 적게">
          <button type="submit" :disabled="store.sending || !input.trim()">보내기</button>
        </form>
      </div>
      <aside class="side-col" data-tour="side">
        <div class="segmented" role="tablist" aria-label="오른쪽 보기">
          <button type="button" role="tab" :aria-selected="panel === 'map'" :class="{ active: panel === 'map' }" @click="panel = 'map'">지도</button>
          <button type="button" role="tab" :aria-selected="panel === 'trace'" :class="{ active: panel === 'trace' }" @click="panel = 'trace'">실행 과정</button>
          <span class="meta">{{ store.sending ? '처리 중…' : store.lastMeta }}</span>
        </div>
        <div v-if="panel === 'map'" class="side-body">
          <p v-if="store.selected" class="map-title">{{ store.selected.index }}. {{ store.selected.label }} · {{ store.selected.leave_at }} → {{ store.selected.arrive_at }}</p>
          <RouteMap :points="mapPoints" :legs="store.selected ? store.selected.legs : []" :others="otherPoints"
                    height="max(420px, calc(100vh - 330px))" />
          <p v-if="!store.selected" class="hint">경로를 찾으면 출발지·역·도착지가 지도에 표시돼요. 카드를 누르면 그 경로를 크게 보여 줘요.</p>
        </div>
        <div v-else class="side-body">
          <TraceList :events="store.lastEvents" empty="요청을 보내면 단계와 Tool 호출이 순서대로 표시됩니다." />
        </div>
      </aside>
    </section>`,
};
