// 여러 페이지에서 쓰는 작은 컴포넌트: 경로 카드, 수단 막대·아이콘 줄, 실행 과정 타임라인, 접는 목록.
import { computed } from "vue";
import { basisText, buildTrace, mins, shortLegName, won } from "../format.js";
import ModeIcon from "./ModeIcon.js";

// 구간을 소요 시간 비율대로 이어 붙인 색 막대. 짧은 구간도 보이도록 최소 너비를 둔다.
export const RouteBar = {
  name: "RouteBar",
  components: { ModeIcon },
  props: { legs: { type: Array, default: () => [] } },
  setup(props) {
    const total = computed(() => props.legs.reduce((s, l) => s + (l.minutes || 0), 0) || 1);
    return { total };
  },
  template: `
    <div class="route-bar" aria-hidden="true">
      <span v-for="(l, i) in legs" :key="i" class="seg" :class="l.mode"
            :style="{ flexGrow: Math.max(l.minutes || 1, 1) }" :title="(l.name || l.mode) + ' ' + (l.minutes ?? '?') + '분'">
        <ModeIcon v-if="(l.minutes || 0) / total >= 0.1" :mode="l.mode" :size="12" />
        <span v-if="(l.minutes || 0) / total >= 0.16" class="seg-min">{{ l.minutes }}분</span>
      </span>
    </div>`,
};

// 수단 아이콘 + 노선 이름을 순서대로. 도보는 아이콘과 분만 작게.
export const LegSteps = {
  name: "LegSteps",
  components: { ModeIcon },
  props: { legs: { type: Array, default: () => [] } },
  setup() { return { shortLegName }; },
  template: `
    <ol class="leg-steps" aria-label="구간 순서">
      <li v-for="(l, i) in legs" :key="i" :class="l.mode">
        <span class="step-icon"><ModeIcon :mode="l.mode" :size="14" /></span>
        <span v-if="l.mode === 'walk'" class="step-min">{{ l.minutes ?? '?' }}분</span>
        <span v-else class="step-name">{{ shortLegName(l) }}<span class="step-min"> {{ l.minutes ?? '?' }}분</span></span>
      </li>
    </ol>`,
};

export const RouteCard = {
  name: "RouteCard",
  components: { RouteBar, LegSteps },
  props: { card: Object, selected: Boolean, saving: Boolean },
  emits: ["select", "save"],
  setup(props) {
    return { won, mins, basis: computed(() => basisText(props.card)) };
  },
  template: `
    <article class="card" :class="{ selected }" @click="$emit('select', card)" tabindex="0"
             @keydown.enter.self="$emit('select', card)" :aria-pressed="selected"
             :aria-label="(card.label || '추천') + ' ' + card.leave_at + ' 출발 ' + card.arrive_at + ' 도착'">
      <header class="card-top">
        <span class="pill" :class="'pill-' + (card.index || 1)">{{ card.label || '추천' }}</span>
        <span v-if="card.warnings && card.warnings.length" class="pill warn-pill" :title="card.warnings.join(' / ')">주의 {{ card.warnings.length }}</span>
      </header>
      <div class="card-main">
        <div class="duration"><strong>{{ mins(card.total_min) }}</strong></div>
        <div class="card-facts">
          <span class="clock">{{ card.leave_at }} 출발 → {{ card.arrive_at }} 도착</span>
          <span>환승 {{ card.transfers }}회</span>
          <span class="fare">{{ won(card.total_fare) }}</span>
        </div>
      </div>
      <RouteBar :legs="card.legs" />
      <LegSteps :legs="card.legs" />
      <p v-for="w in card.warnings" :key="w" class="warn">⚠ {{ w }}</p>
      <details class="basis-box" @click.stop>
        <summary>판단 근거</summary>
        <p class="basis">{{ card.date }} · {{ basis }}</p>
      </details>
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
