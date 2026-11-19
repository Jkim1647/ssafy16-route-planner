// 출발 알림 계산(의존성 없음, node 테스트 가능): 곧 나가야 하는 계획과 브라우저 알림 시점.
export const SOON_MIN = 60;    // 이 안에 출발하면 화면 위에 띄운다
export const NOTIFY_MIN = 10;  // 이 안이면 브라우저 알림(허용한 경우, 계획마다 한 번)

const leaveDate = (p) => {
  const [y, m, d] = p.date.split("-").map(Number);
  const [h, mi] = p.leave_at.split(":").map(Number);
  return new Date(y, m - 1, d, h, mi);
};

/** now 기준 SOON_MIN분 안에 출발하는 계획 [{plan, minutes}], 가까운 순. 이미 지난 것은 뺀다. */
export function upcomingDepartures(plans, now) {
  return (plans || [])
    .map((plan) => ({ plan, minutes: Math.round((leaveDate(plan) - now) / 60000) }))
    .filter((u) => u.minutes >= 0 && u.minutes <= SOON_MIN)
    .sort((a, b) => a.minutes - b.minutes);
}

export const notifyKey = (plan) => `${plan.id}@${plan.date} ${plan.leave_at}`;

/** 브라우저 알림을 보낼 때인가(10분 전부터, 같은 계획·시각은 한 번만). */
export function notifyDue(u, sent) {
  return u.minutes <= NOTIFY_MIN && !sent.has(notifyKey(u.plan));
}
