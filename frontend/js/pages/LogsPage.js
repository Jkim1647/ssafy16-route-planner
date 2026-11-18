// 실행 로그: 세션 목록(/logs)과 세션 상세(/logs/:sid). 수정 기능은 없다(F3014).
import { computed, onMounted, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { api } from "../api.js";
import { VERDICT } from "../format.js";
import { toast } from "../store.js";
import { TraceList } from "../components/common.js";

export const LogsPage = {
  name: "LogsPage",
  setup() {
    const sessions = ref([]);
    const loading = ref(true);
    const error = ref("");
    const onlyWarn = ref(false);
    async function load() {
      loading.value = true;
      try {
        sessions.value = await api("/logs");
        error.value = "";
      } catch (e) {
        error.value = e.message;
      } finally {
        loading.value = false;
      }
    }
    const shown = computed(() => sessions.value.filter((s) => !onlyWarn.value || s.warn_count));
    onMounted(load);
    return { sessions, loading, error, onlyWarn, shown, load };
  },
  template: `
    <section class="page">
      <div class="page-head">
        <div>
          <h2>실행 로그</h2>
          <p class="hint">대화 세션마다 단계·Tool 호출·재계획과 이상 징후 판정이 저장돼요. 로그는 조회·삭제만 할 수 있어요.</p>
        </div>
        <button type="button" class="ghost" @click="load" :disabled="loading">새로고침</button>
      </div>
      <div class="toolbar">
        <label class="check"><input type="checkbox" v-model="onlyWarn"> 이상 징후가 있는 세션만</label>
        <span class="hint">{{ shown.length }} / {{ sessions.length }}개 세션</span>
      </div>
      <div v-if="error" class="notice">{{ error }}</div>
      <p v-else-if="loading" class="hint">불러오는 중…</p>
      <p v-else-if="!shown.length" class="empty-state">표시할 실행 로그가 없어요.</p>
      <ul v-else class="plan-list">
        <li v-for="s in shown" :key="s.session_id">
          <router-link :to="'/logs/' + s.session_id" class="plan-row log-row">
            <span class="what"><strong>{{ s.first_message || s.session_id }}</strong>
              <span class="basis">{{ s.last_ts.replace('T', ' ').slice(5, 16) }} · 요청 {{ s.run_count }}건</span></span>
            <span class="tags"><span v-if="s.warn_count" class="tag bad">이상 {{ s.warn_count }}</span></span>
            <span class="chev" aria-hidden="true">›</span>
          </router-link>
        </li>
      </ul>
    </section>`,
};

export const LogDetailPage = {
  name: "LogDetailPage",
  components: { TraceList },
  props: { sid: String },
  setup(props) {
    const router = useRouter();
    const data = ref(null);
    const error = ref("");
    const confirmDelete = ref(false);
    async function load() {
      data.value = null;
      try {
        data.value = await api(`/logs/${props.sid}`);
        error.value = "";
      } catch (e) {
        error.value = e.message;
      }
    }
    async function remove() {
      try {
        await api(`/logs/${props.sid}`, { method: "DELETE" });
        toast("실행 로그를 삭제했어요.");
        router.push("/logs");
      } catch (e) {
        error.value = e.message;
      }
    }
    watch(() => props.sid, load, { immediate: true });
    return { data, error, confirmDelete, remove, VERDICT };
  },
  template: `
    <section class="page">
      <router-link to="/logs" class="back">‹ 실행 로그 목록</router-link>
      <div v-if="error" class="empty-state"><p>{{ error }}</p><router-link to="/logs" class="button">목록으로</router-link></div>
      <p v-else-if="!data" class="hint">불러오는 중…</p>
      <template v-else>
        <div class="page-head">
          <div><p class="eyebrow">세션 {{ sid }}</p><h2>{{ data.runs[0]?.user_message || '실행 로그' }}</h2></div>
          <button type="button" class="danger" @click="confirmDelete = true">로그 삭제</button>
        </div>
        <div v-if="confirmDelete" class="notice bad confirm" role="alertdialog" aria-label="삭제 확인">
          이 세션의 실행 로그를 삭제할까요? 되돌릴 수 없어요.
          <button type="button" class="danger" @click="remove">삭제</button>
          <button type="button" class="ghost" @click="confirmDelete = false">취소</button>
        </div>
        <div class="run-list">
          <div v-for="r in data.runs" :key="r.run_id" class="run-summary">
            <strong>"{{ r.user_message }}"</strong> · {{ r.status }} · 재계획 {{ r.replan_count ?? 0 }} · LLM {{ r.llm_calls ?? 0 }}
            <span v-if="r.anomaly" class="verdict" :class="r.anomaly.verdict">{{ VERDICT[r.anomaly.verdict] }}</span>
            <div v-for="f in r.anomaly?.findings || []" :key="f.rule + f.detail" class="basis">{{ f.rule }}: {{ f.detail }}</div>
            <div v-if="r.anomaly?.diagnosis" class="basis">LLM 진단: {{ r.anomaly.diagnosis }}</div>
          </div>
        </div>
        <div class="panel"><h3>실행 순서</h3><TraceList :events="data.events" /></div>
      </template>
    </section>`,
};
