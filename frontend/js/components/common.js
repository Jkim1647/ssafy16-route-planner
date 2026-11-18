// 여러 페이지에서 쓰는 작은 컴포넌트: 경로 카드, 구간 칩, 실행 과정 타임라인, 접는 목록.
import { computed } from "vue";
import { basisText, buildTrace, legLabel, mins, won } from "../format.js";

export const LegChips = {
  name: "LegChips",
  props: { legs: { type: Array, default: () => [] } },
  setup() { return { legLabel }; },
  template: `
    <ol class="legs" aria-label="구간">
      <li v-for="(leg, i) in legs" :key="i" :class="leg.mode">
        <span class="leg-name">{{ legLabel(leg) }}</span> <span class="leg-min">{{ leg.minutes ?? '?' }}분</span>
      </li>
    </ol>`,
};

export const RouteCard = {
  name: "RouteCard",
  components: { LegChips },
  props: { card: Object, selected: Boolean, saving: Boolean },
  emits: ["select", "save"],
  setup(props) {
    return { won, mins, basis: computed(() => basisText(props.card)) };
  },
  template: `
    <article class="card" :class="{ selected }" @click="$emit('select', card)" tabindex="0"
             @keydown.enter.self="$emit('select', card)" :aria-pressed="selected">
      <header class="card-head">
        <strong>{{ card.index }}. {{ card.label || '추천' }}</strong>
        <span class="times">{{ card.leave_at }} → {{ card.arrive_at }}</span>
      </header>
      <p class="sub">{{ card.date }} · {{ mins(card.total_min) }} · 환승 {{ card.transfers }}회 · 총 {{ won(card.total_fare) }}</p>
      <LegChips :legs="card.legs" />
      <p class="basis">판단 근거: {{ basis }}</p>
      <p v-for="w in card.warnings" :key="w" class="warn">⚠ {{ w }}</p>
      <div class="card-actions">
        <button type="button" class="ghost small" @click.stop="$emit('select', card)">{{ selected ? '지도에 표시 중' : '지도에서 보기' }}</button>
        <button type="button" class="small" :disabled="saving" @click.stop="$emit('save', card)">{{ saving ? '저장 중…' : '이 경로로 저장' }}</button>
      </div>
    </article>`,
};

export const Excluded = {
  name: "Excluded",
  props: { title: String, items: { type: Array, default: () => [] } },
  template: `
    <details v-if="items && items.length" class="excluded">
      <summary>{{ title }} {{ items.length }}건</summary>
      <ul><li v-for="(x, i) in items" :key="i">{{ x.summary }} — {{ x.reason || '추정 시간표' }}</li></ul>
    </details>`,
};

export const TraceList = {
  name: "TraceList",
  props: { events: { type: Array, default: () => [] }, empty: { type: String, default: "표시할 단계가 없어요." } },
  setup(props) { return { items: computed(() => buildTrace(props.events)) }; },
  template: `
    <ol class="trace">
      <li v-if="!items.length" class="empty">{{ empty }}</li>
      <li v-for="(it, i) in items" :key="i" :class="it.kind">
        <span v-if="it.agent" class="badge" :class="it.role">{{ it.agent }}</span>{{ it.title }}
        <span v-if="it.ms" class="ms" :class="{ cached: it.cached }">{{ it.ms }}</span>
        <div v-for="(d, j) in it.details" :key="j" class="detail">{{ d }}</div>
        <div v-if="it.result" class="detail">{{ it.result }}</div>
        <div v-if="it.error" class="detail"><span class="code">{{ it.error }}</span></div>
      </li>
    </ol>`,
};
