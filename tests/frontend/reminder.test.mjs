// 화면 출발 알림 계산. 실행: node --test tests/frontend/reminder.test.mjs
import assert from "node:assert/strict";
import { test } from "node:test";
import { notifyDue, upcomingDepartures } from "../../frontend/js/reminder.js";

const NOW = new Date(2026, 10, 21, 7, 0);  // 11월 21일 07:00(로컬)
const p = (id, date, leave) => ({ id, title: `계획 ${id}`, date, leave_at: leave, arrive_at: "10:00" });

test("60분 안에 출발하는 계획만, 가까운 순", () => {
  const plans = [p(1, "2026-11-21", "07:45"), p(2, "2026-11-21", "07:20"), p(3, "2026-11-21", "09:00"),
                 p(4, "2026-11-22", "07:10"), p(5, "2026-11-21", "06:50")];
  assert.deepEqual(upcomingDepartures(plans, NOW).map((u) => [u.plan.id, u.minutes]), [[2, 20], [1, 45]]);
});

test("브라우저 알림은 10분 전부터 한 번만", () => {
  assert.equal(notifyDue({ plan: p(1, "2026-11-21", "07:08"), minutes: 8 }, new Set()), true);
  assert.equal(notifyDue({ plan: p(1, "2026-11-21", "07:08"), minutes: 8 }, new Set(["1@2026-11-21 07:08"])), false);
  assert.equal(notifyDue({ plan: p(1, "2026-11-21", "07:30"), minutes: 30 }, new Set()), false);
});
