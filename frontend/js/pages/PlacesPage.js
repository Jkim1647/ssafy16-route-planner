// 내 장소: 집·교육장처럼 이름을 붙여 저장한다. 대화에서 그 이름을 말하면 검색 없이 저장한 좌표를 쓴다.
import { onMounted, ref } from "vue";
import { api } from "../api.js";
import { loadPlaces, store, toast } from "../store.js";

export const KINDS = [["home", "집"], ["school", "교육장·학교"], ["work", "회사"], ["pin", "기타"]];
export const KIND_ICON = { home: "🏠", school: "🎓", work: "🏢", pin: "📍" };

export default {
  name: "PlacesPage",
  setup() {
    const q = ref("");
    const results = ref([]);
    const searching = ref(false);
    const searchError = ref("");
    const picked = ref(null);
    const form = ref({ label: "", kind: "home" });
    const editing = ref(null);
    const saving = ref(false);

    async function search() {
      if (!q.value.trim()) return;
      searching.value = true;
      searchError.value = "";
      try {
        results.value = await api(`/places/search?q=${encodeURIComponent(q.value.trim())}`);
      } catch (e) {
        results.value = [];
        searchError.value = e.message;
      } finally {
        searching.value = false;
      }
    }
    function pick(r) {
      picked.value = r;
      if (!form.value.label) form.value.label = KINDS.find((k) => k[0] === form.value.kind)?.[1].split("·")[0] || "";
    }
    async function save() {
      if (!picked.value) return;
      saving.value = true;
      try {
        await api("/places", { method: "POST", body: { ...picked.value, label: form.value.label.trim(), kind: form.value.kind } });
        toast(`'${form.value.label}'(으)로 저장했어요. 대화에서 이 이름으로 말하면 돼요.`);
        picked.value = null; results.value = []; q.value = ""; form.value = { label: "", kind: "pin" };
        await loadPlaces();
      } catch (e) {
        toast(e.message, "bad");
      } finally {
        saving.value = false;
      }
    }
    function startEdit(p) { editing.value = { ...p }; }
    async function saveEdit() {
      const p = editing.value;
      try {
        await api(`/places/${p.id}`, { method: "PUT", body: { label: p.label.trim(), kind: p.kind, name: p.name, address: p.address, x: p.x, y: p.y } });
        editing.value = null;
        await loadPlaces();
      } catch (e) {
        toast(e.message, "bad");
      }
    }
    async function remove(p) {
      try {
        await api(`/places/${p.id}`, { method: "DELETE" });
        toast(`'${p.label}'을(를) 지웠어요.`);
        await loadPlaces();
      } catch (e) {
        toast(e.message, "bad");
      }
    }
    onMounted(loadPlaces);
    return { store, q, results, searching, searchError, picked, form, editing, saving, KINDS, KIND_ICON,
      search, pick, save, startEdit, saveEdit, remove };
  },
  template: `
    <section class="page">
      <div class="page-head">
        <div>
          <h2>내 장소</h2>
          <p class="hint">집·교육장처럼 자주 가는 곳을 이름으로 저장해요. 대화에서 "집에서 교육장까지"처럼 말하거나 여러 동선에서 바로 고를 수 있어요.</p>
        </div>
      </div>
      <div class="detail-grid">
        <div class="panel">
          <h3>저장한 장소</h3>
          <p v-if="!store.places.length" class="hint">아직 없어요. 오른쪽에서 검색해 추가해 보세요.</p>
          <ul class="place-list">
            <li v-for="p in store.places" :key="p.id">
              <template v-if="editing && editing.id === p.id">
                <span class="place-icon" aria-hidden="true">{{ KIND_ICON[editing.kind] }}</span>
                <input v-model="editing.label" maxlength="20" aria-label="이름">
                <select v-model="editing.kind" aria-label="종류"><option v-for="k in KINDS" :key="k[0]" :value="k[0]">{{ k[1] }}</option></select>
                <button type="button" class="small" @click="saveEdit">저장</button>
                <button type="button" class="ghost small" @click="editing = null">취소</button>
              </template>
              <template v-else>
                <span class="place-icon" aria-hidden="true">{{ KIND_ICON[p.kind] }}</span>
                <span class="place-main"><strong>{{ p.label }}</strong><span class="basis">{{ p.name }} · {{ p.address }}</span></span>
                <button type="button" class="ghost small" @click="startEdit(p)">수정</button>
                <button type="button" class="danger small" @click="remove(p)">삭제</button>
              </template>
            </li>
          </ul>
        </div>
        <div class="panel">
          <h3>장소 추가</h3>
          <form class="search-row" @submit.prevent="search">
            <label class="sr-only" for="place-q">장소 검색</label>
            <input id="place-q" v-model="q" maxlength="50" placeholder="예) SSAFY 광주캠퍼스, 첨단 쌍암공원">
            <button type="submit" :disabled="searching || !q.trim()">{{ searching ? '찾는 중…' : '검색' }}</button>
          </form>
          <p v-if="searchError" class="notice bad">{{ searchError }}</p>
          <ul v-if="results.length" class="result-list">
            <li v-for="(r, i) in results" :key="i">
              <button type="button" class="result" :class="{ on: picked === r }" @click="pick(r)">
                <strong>{{ r.name }}</strong><span class="basis">{{ r.address }}</span>
              </button>
            </li>
          </ul>
          <form v-if="picked" class="edit-form" @submit.prevent="save">
            <label>이름 <input v-model="form.label" required maxlength="20" placeholder="예) 집"></label>
            <label>종류 <select v-model="form.kind"><option v-for="k in KINDS" :key="k[0]" :value="k[0]">{{ k[1] }}</option></select></label>
            <button type="submit" :disabled="saving || !form.label.trim()">저장</button>
          </form>
        </div>
      </div>
    </section>`,
};
