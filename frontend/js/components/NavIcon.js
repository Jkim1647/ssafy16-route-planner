// 상단 메뉴 아이콘(직접 그린 단순 선 SVG, 색은 currentColor). 글자와 함께 쓰므로 스크린리더에는 숨긴다.
const PATHS = {
  chat: `<path d="M4 5.5A2.5 2.5 0 0 1 6.5 3h11A2.5 2.5 0 0 1 20 5.5v8a2.5 2.5 0 0 1-2.5 2.5H10l-4.5 4v-4h0A1.5 1.5 0 0 1 4 14.5z"/><path d="M8 8.5h8M8 11.5h5"/>`,
  places: `<path d="M12 21s-6.5-5.7-6.5-11a6.5 6.5 0 0 1 13 0c0 5.3-6.5 11-6.5 11z"/><circle cx="12" cy="10" r="2.4"/>`,
  plans: `<rect x="4" y="5" width="16" height="15" rx="2"/><path d="M4 9.5h16M8.5 3v4M15.5 3v4M8 13.5l2 2 4-4"/>`,
  logs: `<path d="M6 4h9l3 3v13H6z"/><path d="M15 4v3h3M9 11h6M9 14.5h6M9 18h3"/>`,
};

export default {
  name: "NavIcon",
  props: { name: String },
  computed: { svg() { return PATHS[this.name] || ""; } },
  // 경로는 위의 고정 문자열뿐이라 v-html에 사용자·서버 값이 들어가지 않는다.
  template: `<svg class="nav-icon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                  stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" v-html="svg"></svg>`,
};
