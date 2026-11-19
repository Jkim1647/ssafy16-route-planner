// 화면의 '조건으로 질문 만들기'가 만드는 문장. 실행: node --test tests/frontend/question.test.mjs
import assert from "node:assert/strict";
import { test } from "node:test";
import { buildQuestion, koDate, koTime, parseTimeInput, wonText } from "../../frontend/js/question.js";

const TODAY = "2026-11-19";
const home = { label: "집", name: "쌍암공원 분수광장" };
const school = { label: "교육장", name: "SSAFY 광주캠퍼스" };
const gangnam = { label: null, name: "강남역 2호선" };

test("날짜는 오늘·내일·모레, 그 밖은 M월 D일", () => {
  assert.equal(koDate("2026-11-19", TODAY), "오늘");
  assert.equal(koDate("2026-11-20", TODAY), "내일");
  assert.equal(koDate("2026-11-21", TODAY), "모레");
  assert.equal(koDate("2026-12-03", TODAY), "12월 3일");
});

test("시각은 오전·오후, 자정 무렵은 숫자로(파서가 '밤 12시'를 읽지 않음)", () => {
  assert.equal(koTime("09:00"), "오전 9시");
  assert.equal(koTime("15:30"), "오후 3시 30분");
  assert.equal(koTime("12:05"), "오후 12시 5분");
  assert.equal(koTime("00:30"), "00:30");
});

test("금액은 만·천 단위로, 딱 떨어지지 않으면 숫자 그대로", () => {
  assert.equal(wonText(60000), "6만원");
  assert.equal(wonText(45000), "4만5천원");
  assert.equal(wonText(45500), "45,500원");
});

test("두 곳·도착 마감 → 대화 Agent에 보낼 문장", () => {
  const r = buildQuestion({ date: "2026-11-20", stops: [{ ...home }, { ...gangnam, arrive_by: "14:00" }],
    budget: 60000, priority: "cheapest" }, TODAY);
  assert.deepEqual(r, { ok: true, text: "내일 오후 2시까지 집에서 강남역 2호선 가야 해. 6만원 이하로" });
});

test("출발 시각과 마감 둘 다, 우선순위 표현", () => {
  const r = buildQuestion({ date: "2026-11-21", stops: [{ ...home, depart: "07:00" }, { ...school, arrive_by: "10:30" }],
    budget: null, priority: "fewest_transfers" }, TODAY);
  assert.equal(r.text, "모레 오전 7시 이후에 출발해서 오전 10시 30분까지 집에서 교육장 가야 해. 환승 적게");
});

test("출발 시각만", () => {
  const r = buildQuestion({ date: "2026-11-20", stops: [{ ...home, depart: "18:00" }, { ...gangnam }],
    priority: "fastest" }, TODAY);
  assert.equal(r.text, "내일 오후 6시 이후에 출발해서 집에서 강남역 2호선 가야 해. 가장 빨리");
});

test("시각이 없거나 곳이 모자라면 이유와 함께 실패", () => {
  assert.equal(buildQuestion({ date: "2026-11-20", stops: [{ ...home }, { ...gangnam }] }, TODAY).ok, false);
  assert.match(buildQuestion({ date: "2026-11-20", stops: [{ ...home }] }, TODAY).reason, /두 곳/);
});

test("시각은 숫자로 입력: 7 · 730 · 0730 · 7:30 · 1930 · 19시 → HH:MM", () => {
  assert.equal(parseTimeInput("7"), "07:00");
  assert.equal(parseTimeInput("730"), "07:30");
  assert.equal(parseTimeInput("0730"), "07:30");
  assert.equal(parseTimeInput("7:30"), "07:30");
  assert.equal(parseTimeInput("1930"), "19:30");
  assert.equal(parseTimeInput("19시"), "19:00");
  assert.equal(parseTimeInput(" 22:5 "), "22:05");
  assert.equal(parseTimeInput(""), "");
});

test("없는 시각은 읽지 않는다", () => {
  for (const v of ["25", "2460", "7:75", "abc", "12345"]) assert.equal(parseTimeInput(v), null, v);
});
