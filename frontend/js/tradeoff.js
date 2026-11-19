// 시간·요금 트레이드오프: 경로 카드를 출발 시각(x)·총 요금(y) 평면에 놓고, "일찍 나가면 얼마 아끼는지" 한 줄로 요약한다.
// 의존성 없음(node 테스트 가능).

const leaveMin = (c) => Date.parse(`${c.date}T${c.leave_at}:00Z`) / 60000;
const priced = (cards) => (cards || []).filter((c) => c.total_fare != null && c.leave_at && c.date);
const hm = (m) => (m >= 60 ? `${Math.floor(m / 60)}시간${m % 60 ? ` ${m % 60}분` : ""}` : `${m}분`);

/** 그림 좌표 [{x, y, card}] — 두 개 이상일 때만. 이른 출발은 왼쪽, 비싼 요금은 위. */
export function chartPoints(cards, { w, h, pad }) {
  const cs = priced(cards);
  if (cs.length < 2) return [];
  const xs = cs.map(leaveMin), ys = cs.map((c) => c.total_fare);
  const [x0, x1, y0, y1] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
  const sx = (v) => (x1 === x0 ? w / 2 : pad + ((v - x0) / (x1 - x0)) * (w - 2 * pad));
  const sy = (v) => (y1 === y0 ? h / 2 : h - pad - ((v - y0) / (y1 - y0)) * (h - 2 * pad));
  return cs.map((c, i) => ({ x: sx(xs[i]), y: sy(ys[i]), card: c }));
}

/** 가장 늦게 나가는 경로와 가장 싼 경로를 비교한 한 줄. 비교할 게 없으면 "". */
export function insight(cards) {
  const cs = priced(cards);
  if (cs.length < 2) return "";
  const latest = cs.reduce((a, b) => (leaveMin(b) > leaveMin(a) ? b : a));
  const minFare = Math.min(...cs.map((c) => c.total_fare));
  if (latest.total_fare === minFare) return `가장 늦게 나가는 경로(${latest.leave_at})가 가장 싸요.`;
  const cheap = cs.filter((c) => c.total_fare === minFare).reduce((a, b) => (leaveMin(b) > leaveMin(a) ? b : a));
  const earlier = Math.round(leaveMin(latest) - leaveMin(cheap));
  if (earlier <= 0) return "";
  return `${hm(earlier)} 일찍 나가면 ${(latest.total_fare - minFare).toLocaleString("ko-KR")}원 아껴요(${cheap.leave_at} 출발).`;
}
