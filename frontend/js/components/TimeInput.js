// 숫자로 치는 시각 입력: "730"·"0730"·"7:30"·"19" → 칸을 떠날 때 07:30처럼 정리. 없는 시각이면 빨간 테두리 + 안내.
import { ref, watch } from "vue";
import { parseTimeInput } from "../question.js";

export default {
  name: "TimeInput",
  props: { modelValue: { type: String, default: "" }, label: { type: String, required: true } },
  emits: ["update:modelValue"],
  setup(props, { emit }) {
    const text = ref(props.modelValue);
    const bad = ref(false);
    watch(() => props.modelValue, (v) => { if (parseTimeInput(text.value) !== v) text.value = v; });
    function commit() {
      const v = parseTimeInput(text.value);
      bad.value = v === null;
      if (v === null) { emit("update:modelValue", ""); return; }
      text.value = v;
      emit("update:modelValue", v);
    }
    // 네 자리(0730)나 콜론 뒤 두 자리까지 치면 바로 반영해 질문 미리보기가 따라오게 한다
    function onInput() {
      bad.value = false;
      const v = parseTimeInput(text.value);
      if (v && /^\d{4}$|:\d{2}$/.test(text.value.trim())) emit("update:modelValue", v);
    }
    return { text, bad, commit, onInput };
  },
  template: `
    <label class="time-input" :class="{ bad }">{{ label }}
      <input type="text" inputmode="numeric" maxlength="5" placeholder="예) 0730" autocomplete="off"
             v-model="text" @input="onInput" @blur="commit" @keydown.enter.prevent="commit" :aria-invalid="bad">
      <span v-if="bad" class="field-error" role="alert">0730·7:30처럼</span>
    </label>`,
};
