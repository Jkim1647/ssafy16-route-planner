// 이동 수단 아이콘(직접 그린 단순 SVG). 색은 currentColor를 따른다.
import { MODE_LABEL } from "../format.js";

const PATHS = {
  walk: `<circle cx="13" cy="4" r="2"/><path d="M10.5 8.5 13 7.6c.9-.3 1.8.1 2.2.9l1.3 2.6 2.5.9-.6 1.8-3.2-1.1-.9-1.7-1 3.9 2.5 2.6V22h-2v-4.5l-2.3-2.3-1 4.5L9 22l-2-.4 2.3-10.1-1.8.8V15h-2v-4.1z"/>`,
  bus: `<path d="M5 4.5C5 3.1 6.1 2 7.5 2h9C17.9 2 19 3.1 19 4.5V17c0 .8-.4 1.4-1 1.7V21h-2.5v-2h-7v2H6v-2.3c-.6-.3-1-.9-1-1.7z"/><rect x="7" y="5" width="10" height="6" rx="1" fill="#fff"/><circle cx="8.5" cy="15" r="1.2" fill="#fff"/><circle cx="15.5" cy="15" r="1.2" fill="#fff"/>`,
  subway: `<path d="M6 4.5C6 3.1 7.1 2 8.5 2h7C16.9 2 18 3.1 18 4.5V16c0 1.1-.9 2-2 2l2 3h-2.3l-2-3h-3.4l-2 3H6l2-3c-1.1 0-2-.9-2-2z"/><rect x="8" y="5" width="3.3" height="5" rx=".6" fill="#fff"/><rect x="12.7" y="5" width="3.3" height="5" rx=".6" fill="#fff"/><circle cx="9.5" cy="14" r="1.1" fill="#fff"/><circle cx="14.5" cy="14" r="1.1" fill="#fff"/>`,
  train: `<path d="M4 17.5V9c0-3.9 3.6-7 8-7s8 3.1 8 7v8.5c0 1-.8 1.5-1.6 1.5l1.6 2h-2.4l-1.6-2H8l-1.6 2H4l1.6-2C4.8 19 4 18.5 4 17.5z"/><path d="M7 9.5C7 7 9.2 5 12 5s5 2 5 4.5V11H7z" fill="#fff"/><circle cx="8.5" cy="15" r="1.1" fill="#fff"/><circle cx="15.5" cy="15" r="1.1" fill="#fff"/>`,
  taxi: `<rect x="9" y="2" width="6" height="3" rx=".8"/><path d="M5.2 9.2 6.8 6c.3-.6.9-1 1.6-1h7.2c.7 0 1.3.4 1.6 1l1.6 3.2c1.2.3 2.2 1.4 2.2 2.8v5h-1.8v2h-2.6v-2H8.2v2H5.6v-2H3.8v-5c0-1.4.9-2.5 1.4-2.8z"/><path d="M7.6 9h8.8l-1-2.2H8.6z" fill="#fff"/><circle cx="7.5" cy="13.2" r="1.2" fill="#fff"/><circle cx="16.5" cy="13.2" r="1.2" fill="#fff"/>`,
};
PATHS.car = PATHS.taxi;

export default {
  name: "ModeIcon",
  props: { mode: String, size: { type: Number, default: 16 } },
  computed: {
    svg() { return PATHS[this.mode] || PATHS.walk; },
    label() { return MODE_LABEL[this.mode] || this.mode; },
  },
  // 아이콘 경로는 위의 고정 문자열뿐이라 v-html에 사용자·서버 값이 들어가지 않는다.
  template: `<svg class="mode-icon" :width="size" :height="size" viewBox="0 0 24 24" fill="currentColor"
                  role="img" :aria-label="label" v-html="svg"></svg>`,
};
