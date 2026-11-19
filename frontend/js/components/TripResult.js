// 여러 동선 결과(대화 안에 표시): 전체 요약 + 구간별 대표 경로 카드, 구간별·전체 저장.
import { api } from "../api.js";
import { won } from "../format.js";
import { toast } from "../store.js";
import { RouteCard } from "./common.js";

export default {
  name: "TripResult",
  components: { RouteCard },
  props: { trip: { type: Object, required: true }, selected: { type: Object, default: null } },
  emits: ["select"],
  setup(props) {
    const body = (card, leg, title) => ({ title: title.slice(0, 100), date: card.date, leave_at: card.leave_at,
      arrive_at: card.arrive_at, origin_name: leg.from.slice(0, 100), destination_name: leg.to.slice(0, 100),
      legs: card.legs, total_fare: card.total_fare, points: card.points || [] });

    async function saveAll() {
      const legs = props.trip.legs.filter((l) => l.status === "done");
      let n = 0;
      for (const l of legs) {
        try {
          await api("/plans", { method: "POST", body: body(l.cards[0], l, `여러 동선 ${l.index}/${props.trip.legs.length}: ${l.from} → ${l.to}`) });
          n++;
        } catch (e) { toast(e.message, "bad"); }
      }
      if (n) toast(`구간 ${n}개를 이동 계획으로 저장했어요.`, "ok", { to: "/plans", text: "계획 보기" });
    }
    async function saveOne(card, leg) {
      try {
        await api("/plans", { method: "POST", body: body(card, leg, `${leg.from} → ${leg.to}`) });
        toast("이 구간을 이동 계획으로 저장했어요.", "ok", { to: "/plans", text: "계획 보기" });
      } catch (e) { toast(e.message, "bad"); }
    }
    return { saveAll, saveOne, won };
  },
  template: `
    <div class="trip-result">
      <div class="trip-summary">
        <strong>{{ trip.start_at || '?' }} 출발 → {{ trip.end_at || '?' }} 도착</strong>
        <span>총 {{ won(trip.total_fare) }}</span>
        <button type="button" class="small" @click="saveAll" :disabled="!trip.legs.some(l => l.status === 'done')">전체를 계획으로 저장</button>
      </div>
      <p v-for="w in trip.warnings" :key="w" class="warn">⚠ {{ w }}</p>
      <ol class="leg-results">
        <li v-for="l in trip.legs" :key="l.index" :class="l.status">
          <div class="leg-head">
            <strong>{{ l.index }}구간 · {{ l.from }} → {{ l.to }}</strong>
            <span class="basis">{{ l.depart_after ? l.depart_after + ' 이후 출발' : '' }}{{ l.arrive_by ? ' · ' + l.arrive_by + '까지 도착' : '' }}</span>
          </div>
          <p v-if="l.status !== 'done'" class="hint">{{ l.reason }}</p>
          <RouteCard v-for="c in (l.cards || []).slice(0, 1)" :key="c.index + c.leave_at" :card="c" :selected="c === selected"
                     @select="$emit('select', $event)" @save="saveOne($event, l)" />
          <details v-if="l.cards && l.cards.length > 1" class="excluded">
            <summary>다른 경로 {{ l.cards.length - 1 }}개</summary>
            <RouteCard v-for="c in l.cards.slice(1)" :key="c.index + c.leave_at" :card="c" :selected="c === selected"
                       @select="$emit('select', $event)" @save="saveOne($event, l)" />
          </details>
        </li>
      </ol>
    </div>`,
};
