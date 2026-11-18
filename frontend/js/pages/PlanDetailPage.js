// 이동 계획 상세(/plans/:id): 지도, 구간, 캘린더 등록, 수정, 삭제.
import { computed, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { api } from "../api.js";
import { dateLabel, legLabel, mins, won, POINT_LABEL } from "../format.js";
import { toast } from "../store.js";
import RouteMap from "../components/RouteMap.js";

export default {
  name: "PlanDetailPage",
  components: { RouteMap },
  props: { id: String },
  setup(props) {
    const router = useRouter();
    const plan = ref(null);
    const error = ref("");
    const editing = ref(false);
    const form = ref({});
    const busy = ref(false);
    const notice = ref(null);
    const confirmDelete = ref(false);

    async function load() {
      error.value = "";
      plan.value = null;
      try {
        plan.value = await api(`/plans/${props.id}`);
      } catch (e) {
        error.value = e.message;
      }
    }
    watch(() => props.id, load, { immediate: true });

    const totalMin = computed(() => (plan.value?.legs || []).reduce((s, l) => s + (l.minutes || 0), 0));

    function startEdit() {
      const p = plan.value;
      form.value = { title: p.title, date: p.date, leave_at: p.leave_at, arrive_at: p.arrive_at };
      editing.value = true;
    }
    async function saveEdit() {
      busy.value = true;
      try {
        const r = await api(`/plans/${props.id}`, { method: "PUT", body: form.value });
        plan.value = r.plan;
        editing.value = false;
        notice.value = r.overlaps.length
          ? { kind: "warn", text: "수정했어요. 겹치는 계획: " + r.overlaps.map((o) => `${o.title} ${o.date} ${o.leave_at}~${o.arrive_at}`).join(", ") }
          : { kind: "ok", text: "수정했어요." };
      } catch (e) {
        notice.value = { kind: "bad", text: e.message };
      } finally {
        busy.value = false;
      }
    }
    async function addCalendar() {
      busy.value = true;
      try {
        const r = await api(`/plans/${props.id}/calendar`, { method: "POST" });
        notice.value = { kind: "ok", text: `캘린더(${r.backend})에 등록했어요.` };
        await load();
      } catch (e) {
        notice.value = { kind: "bad", text: e.message };
      } finally {
        busy.value = false;
      }
    }
    async function remove() {
      busy.value = true;
      try {
        await api(`/plans/${props.id}`, { method: "DELETE" });
        toast("이동 계획을 삭제했어요.");
        router.push("/plans");
      } catch (e) {
        notice.value = { kind: "bad", text: e.message };
        busy.value = false;
      }
    }

    return { plan, error, editing, form, busy, notice, confirmDelete, totalMin, startEdit, saveEdit, addCalendar, remove,
      dateLabel, legLabel, mins, won, POINT_LABEL };
  },
  template: `
    <section class="page">
      <router-link to="/plans" class="back">‹ 이동 계획 목록</router-link>
      <div v-if="error" class="empty-state">
        <p>{{ error }}</p>
        <router-link to="/plans" class="button">목록으로</router-link>
      </div>
      <p v-else-if="!plan" class="hint">불러오는 중…</p>
      <template v-else>
        <div class="page-head">
          <div>
            <p class="eyebrow">{{ dateLabel(plan.date) }}</p>
            <h2>{{ plan.title }}</h2>
            <p class="big-times">{{ plan.leave_at }} 출발 → {{ plan.arrive_at }} 도착</p>
          </div>
          <div class="actions">
            <span v-if="plan.calendar_event_id" class="tag ok">캘린더 등록됨</span>
            <button v-else type="button" class="ghost" :disabled="busy" @click="addCalendar">캘린더에 등록</button>
            <button type="button" class="ghost" :disabled="busy" @click="startEdit">수정</button>
            <button type="button" class="danger" :disabled="busy" @click="confirmDelete = true">삭제</button>
          </div>
        </div>
        <div v-if="notice" class="notice" :class="notice.kind" role="status">{{ notice.text }}</div>
        <div v-if="confirmDelete" class="notice bad confirm" role="alertdialog" aria-label="삭제 확인">
          '{{ plan.title }}' ({{ plan.date }} {{ plan.leave_at }}) 계획을 삭제할까요? 되돌릴 수 없어요.
          <button type="button" class="danger" :disabled="busy" @click="remove">삭제</button>
          <button type="button" class="ghost" @click="confirmDelete = false">취소</button>
        </div>
        <form v-if="editing" class="edit-form" @submit.prevent="saveEdit">
          <label>제목 <input v-model="form.title" required maxlength="100"></label>
          <label>날짜 <input v-model="form.date" type="date" required></label>
          <label>출발 <input v-model="form.leave_at" type="time" required></label>
          <label>도착 <input v-model="form.arrive_at" type="time" required></label>
          <button type="submit" :disabled="busy">저장</button>
          <button type="button" class="ghost" @click="editing = false">취소</button>
        </form>
        <div class="detail-grid">
          <div class="panel">
            <h3>지도</h3>
            <RouteMap v-if="plan.points && plan.points.length" :points="plan.points" height="380px" />
            <p v-else class="hint">이 계획은 지도 정보 없이 저장됐어요(지도 기능 추가 전에 저장한 계획).</p>
          </div>
          <div class="panel">
            <h3>구간</h3>
            <ol class="leg-timeline">
              <li v-for="(l, i) in plan.legs" :key="i" :class="l.mode">
                <span class="dot" aria-hidden="true"></span>
                <span class="leg-name">{{ legLabel(l) }}</span>
                <span class="leg-min">{{ l.minutes ?? '?' }}분</span>
                <span v-if="l.fare != null" class="leg-fare">{{ won(l.fare) }}</span>
              </li>
            </ol>
            <dl class="facts">
              <div><dt>총요금</dt><dd>{{ won(plan.total_fare) }}</dd></div>
              <div><dt>구간 이동 합계</dt><dd>{{ mins(totalMin) }} <span class="hint">(환승 대기 제외)</span></dd></div>
              <div v-for="p in plan.points || []" :key="p.kind"><dt>{{ POINT_LABEL[p.kind] || p.kind }}</dt><dd>{{ p.name }}</dd></div>
              <div><dt>저장</dt><dd>{{ plan.created_at.replace('T', ' ').slice(0, 16) }}</dd></div>
            </dl>
          </div>
        </div>
      </template>
    </section>`,
};
