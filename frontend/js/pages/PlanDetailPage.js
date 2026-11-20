// 이동 계획 상세(/plans/:id): 지도, 구간, 캘린더 등록, 수정, 삭제.
import { computed, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { api } from "../api.js";
import { busTypeLabel, dateLabel, legColor, legLabel, mins, won, POINT_LABEL } from "../format.js";
import { buildQuestion } from "../question.js";
import { store, toast } from "../store.js";
import RouteMap from "../components/RouteMap.js";
import ModeIcon from "../components/ModeIcon.js";
import { RouteBar } from "../components/common.js";

export default {
  name: "PlanDetailPage",
  components: { RouteMap, ModeIcon, RouteBar },
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
    const check = ref(null);      // 다시 확인 결과
    const checking = ref(false);

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
    // 당일 재확인: 시간표·캘린더·날씨·행사·출발 시각을 다시 본다
    async function recheck() {
      checking.value = true;
      try {
        check.value = await api(`/plans/${props.id}/recheck`, { method: "POST", body: {} });
      } catch (e) {
        notice.value = { kind: "bad", text: e.message };
      } finally {
        checking.value = false;
      }
    }
    // 같은 출발지·도착지·도착 시각으로 대화에서 다시 찾는다
    function replan() {
      const p = plan.value;
      const q = buildQuestion({ date: p.date, stops: [{ name: p.origin_name }, { name: p.destination_name, arrive_by: p.arrive_at }] },
        new Date().toLocaleDateString("sv-SE"));
      if (!q.ok) return;
      store.pendingQuestion = q.text;
      router.push("/");
    }
    const CHECK_ICON = { ok: "✓", warn: "⚠", info: "·", unknown: "?" };
    // ok는 모든 항목을 확인했을 때만. 확인 못 한 항목이 있으면(partial) 괜찮다고 말하지 않는다
    const CHECK_TITLE = { ok: "그대로 가도 돼요", warn: "확인할 게 있어요", partial: "일부는 확인하지 못했어요", past: "출발 시각이 지났어요" };

    // 읽기 전용 공유 링크
    const shareUrl = computed(() => (plan.value?.share_token
      ? `${location.origin}${location.pathname}#/s/${plan.value.share_token}` : ""));
    async function share() {
      busy.value = true;
      try {
        const r = await api(`/plans/${props.id}/share`, { method: "POST", body: {} });
        plan.value = { ...plan.value, share_token: r.token };
      } catch (e) { notice.value = { kind: "bad", text: e.message }; } finally { busy.value = false; }
    }
    async function unshare() {
      busy.value = true;
      try {
        await api(`/plans/${props.id}/share`, { method: "DELETE" });
        plan.value = { ...plan.value, share_token: null };
        toast("공유를 끊었어요. 이전 링크는 더 이상 열리지 않아요.");
      } catch (e) { notice.value = { kind: "bad", text: e.message }; } finally { busy.value = false; }
    }
    async function copyLink() {
      try { await navigator.clipboard.writeText(shareUrl.value); toast("링크를 복사했어요."); }
      catch { toast("복사하지 못했어요. 링크를 직접 선택해 복사해 주세요.", "warn"); }
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
      check, checking, recheck, replan, CHECK_ICON, CHECK_TITLE, shareUrl, share, unshare, copyLink,
      dateLabel, legLabel, mins, won, POINT_LABEL, legColor, busTypeLabel };
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
            <button type="button" :disabled="checking" @click="recheck">{{ checking ? '확인하는 중…' : '다시 확인' }}</button>
            <span v-if="plan.calendar_event_id" class="tag ok">캘린더 등록됨</span>
            <button v-else type="button" class="ghost" :disabled="busy" @click="addCalendar">캘린더에 등록</button>
            <button v-if="!plan.share_token" type="button" class="ghost" :disabled="busy" @click="share">공유 링크</button>
            <button type="button" class="ghost" :disabled="busy" @click="startEdit">수정</button>
            <button type="button" class="danger" :disabled="busy" @click="confirmDelete = true">삭제</button>
          </div>
        </div>
        <div v-if="notice" class="notice" :class="notice.kind" role="status">{{ notice.text }}</div>
        <section v-if="plan.share_token" class="share-box" aria-label="공유 링크">
          <label class="sr-only" for="share-url">공유 링크</label>
          <input id="share-url" :value="shareUrl" readonly @focus="$event.target.select()">
          <button type="button" class="small" @click="copyLink">복사</button>
          <button type="button" class="danger small" :disabled="busy" @click="unshare">공유 끊기</button>
          <p class="hint">링크를 가진 사람은 로그인 없이 이 계획의 경로·시각·지도를 볼 수 있어요(수정 불가).
            '내 장소'에 집으로 저장한 곳 근처는 약 500m 단위로 흐리게, 이름은 '집 근처'로 보여요. 그 밖의 장소는 그대로 보여요.</p>
        </section>
        <section v-if="check" class="recheck" :class="check.status" aria-live="polite">
          <div class="recheck-head">
            <strong>{{ CHECK_TITLE[check.status] || '확인할 게 있어요' }}</strong>
            <span class="basis">{{ check.checked_at.replace('T', ' ') }} 기준</span>
            <button v-if="check.status !== 'ok'" type="button" class="small" @click="replan">다른 경로 찾기</button>
          </div>
          <ul>
            <li v-for="(it, i) in check.items" :key="i" :class="it.level"><span aria-hidden="true">{{ CHECK_ICON[it.level] }}</span> {{ it.text }}</li>
          </ul>
        </section>
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
            <RouteMap v-if="plan.points && plan.points.length" :points="plan.points" :legs="plan.legs" height="380px" />
            <p v-else class="hint">이 계획은 지도 정보 없이 저장됐어요(지도 기능 추가 전에 저장한 계획).</p>
          </div>
          <div class="panel">
            <h3>구간</h3>
            <RouteBar class="detail-bar" :legs="plan.legs" />
            <ol class="leg-timeline">
              <li v-for="(l, i) in plan.legs" :key="i" :class="l.mode">
                <span class="step-icon" :style="{ background: legColor(l) }"><ModeIcon :mode="l.mode" :size="14" /></span>
                <span class="leg-name"><span v-if="busTypeLabel(l)" class="bus-type">{{ busTypeLabel(l) }}</span>{{ legLabel(l) }}</span>
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
