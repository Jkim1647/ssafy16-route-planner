// 시간·요금 트레이드오프 그래프 계산. 실행: node --test tests/frontend/tradeoff.test.mjs
import assert from "node:assert/strict";
import { test } from "node:test";
import { chartPoints, insight } from "../../frontend/js/tradeoff.js";

const card = (label, date, leave, fare, min) => ({ label, date, leave_at: leave, total_fare: fare, total_min: min });
const CARDS = [
  card("최저가", "2026-11-21", "05:18", 39850, 279),
  card("최단 소요", "2026-11-21", "06:10", 43700, 192),
  card("늦게 출발", "2026-11-21", "07:04", 43700, 198),
];

test("출발 시각을 x, 요금을 y로 그림 영역 안에 놓는다(이른 출발 왼쪽, 비싼 쪽 위)", () => {
  const pts = chartPoints(CARDS, { w: 300, h: 120, pad: 20 });
  assert.equal(pts.length, 3);
  assert.ok(pts[0].x < pts[1].x && pts[1].x < pts[2].x);
  assert.ok(pts[0].y > pts[1].y);  // 싼 쪽이 아래
  for (const p of pts) assert.ok(p.x >= 20 && p.x <= 280 && p.y >= 20 && p.y <= 100);
});

test("전날 출발도 시간 순서대로(날짜 반영)", () => {
  const pts = chartPoints([card("a", "2026-11-20", "22:00", 30000, 300), card("b", "2026-11-21", "06:00", 40000, 200)],
    { w: 300, h: 120, pad: 20 });
  assert.ok(pts[0].x < pts[1].x);
});

test("요약: 가장 늦게 나가는 경로 대비 일찍 나가서 아끼는 금액", () => {
  assert.equal(insight(CARDS), "1시간 46분 일찍 나가면 3,850원 아껴요(05:18 출발).");
});

test("가장 늦은 출발이 가장 싸면 기다릴수록 이득", () => {
  assert.equal(insight([card("a", "2026-11-21", "06:00", 50000, 200), card("b", "2026-11-21", "08:00", 40000, 200)]),
    "가장 늦게 나가는 경로(08:00)가 가장 싸요.");
});

test("요금이 없거나 한 개면 요약하지 않는다", () => {
  assert.equal(insight([CARDS[0]]), "");
  assert.equal(insight([card("a", "2026-11-21", "06:00", null, 200), CARDS[1]]), "");
  assert.deepEqual(chartPoints([CARDS[0]], { w: 300, h: 120, pad: 20 }), []);
});
