// 시간·요금 한눈에: 경로 카드를 출발 시각(가로)·총 요금(세로) 점으로. 점을 누르면 그 경로를 지도에 보여 준다.
import { computed } from "vue";
import { won } from "../format.js";
import { chartPoints, insight } from "../tradeoff.js";

const W = 360, H = 130, PAD = 24, LEFT = 44;  // 왼쪽은 요금 눈금 자리

export default {
  name: "TradeoffChart",
  props: { cards: { type: Array, required: true }, selected: { type: Object, default: null } },
  emits: ["select"],
  setup(props) {
    const pts = computed(() => chartPoints(props.cards, { w: W - LEFT + PAD, h: H, pad: PAD }).map((p) => ({ ...p, x: p.x + LEFT - PAD })));
    const summary = computed(() => insight(props.cards));
    const fares = computed(() => pts.value.map((p) => p.card.total_fare));
    const byX = computed(() => [...pts.value].sort((a, b) => a.x - b.x));
    const man = (n) => `${(n / 10000).toFixed(1)}만원`;
    return { pts, summary, fares, byX, W, H, PAD, LEFT, won, man };
  },
  template: `
    <figure v-if="pts.length" class="tradeoff">
      <figcaption>
        <strong>출발 시각 · 요금</strong>
        <span v-if="summary" class="tradeoff-insight">{{ summary }}</span>
      </figcaption>
      <svg :viewBox="'0 0 ' + W + ' ' + H" role="group" aria-label="경로별 출발 시각과 총 요금">
        <line :x1="LEFT" :y1="H - PAD" :x2="W - PAD" :y2="H - PAD" class="axis" />
        <line :x1="LEFT" :y1="PAD" :x2="LEFT" :y2="H - PAD" class="axis" />
        <text :x="LEFT - 4" :y="PAD + 3" class="tick" text-anchor="end">{{ man(Math.max(...fares)) }}</text>
        <text :x="LEFT - 4" :y="H - PAD" class="tick" text-anchor="end">{{ man(Math.min(...fares)) }}</text>
        <text :x="byX[0].x" :y="H - 6" class="tick" text-anchor="middle">{{ byX[0].card.leave_at }}</text>
        <text :x="byX[byX.length - 1].x" :y="H - 6" class="tick" text-anchor="middle">{{ byX[byX.length - 1].card.leave_at }}</text>
        <g v-for="(p, i) in pts" :key="i" class="pt" :class="{ on: p.card === selected }" role="button" tabindex="0"
           :aria-label="(p.card.label || '경로') + ', ' + p.card.leave_at + ' 출발, ' + won(p.card.total_fare)"
           @click="$emit('select', p.card)" @keydown.enter.prevent="$emit('select', p.card)" @keydown.space.prevent="$emit('select', p.card)">
          <circle :cx="p.x" :cy="p.y" :r="p.card === selected ? 7 : 5" />
          <text :x="p.x" :y="p.y - 10" text-anchor="middle" class="pt-label">{{ p.card.label }}</text>
        </g>
      </svg>
    </figure>`,
};
