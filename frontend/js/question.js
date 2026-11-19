// 조건(들를 곳·날짜·시각·예산·우선순위)을 대화 Agent가 읽는 한국어 질문으로 바꾼다. 의존성 없음(node 테스트 가능).
// 서버의 한국어 날짜·시각 보조 파서(backend/agent/ko_time.py)가 읽는 표현만 쓴다.

const DAY_MS = 86400000;
const PRIORITY_TEXT = { fastest: "가장 빨리", fewest_transfers: "환승 적게" };  // 최저가는 기본값이라 말하지 않음

export function koDate(iso, todayIso) {
  const diff = Math.round((Date.parse(iso) - Date.parse(todayIso)) / DAY_MS);
  if (diff === 0) return "오늘";
  if (diff === 1) return "내일";
  if (diff === 2) return "모레";
  const [, m, d] = iso.split("-").map(Number);
  return `${m}월 ${d}일`;
}

export function koTime(hhmm) {
  const [h, m] = hhmm.split(":").map(Number);
  if (h === 0) return hhmm;  // "밤 12시"는 파서가 일부러 읽지 않는다(자정·정오 모호)
  const half = h < 12 ? "오전" : "오후";
  const h12 = h > 12 ? h - 12 : h;
  return `${half} ${h12}시` + (m ? ` ${m}분` : "");
}

export function wonText(n) {
  if (n % 10000 === 0) return `${n / 10000}만원`;
  if (n > 10000 && n % 1000 === 0) return `${Math.floor(n / 10000)}만${(n % 10000) / 1000}천원`;
  return `${n.toLocaleString("ko-KR")}원`;
}

const placeName = (s) => s.label || s.name;

/** 두 곳이면 {ok:true, text}, 아니면 {ok:false, reason}. 세 곳 이상은 화면이 여러 동선 계산을 바로 부른다. */
export function buildQuestion({ date, stops, budget, priority }, todayIso) {
  if (!stops || stops.length < 2) return { ok: false, reason: "출발지와 도착지, 두 곳을 넣어 주세요." };
  if (stops.length > 2) return { ok: false, reason: "세 곳 이상은 문장 대신 여러 동선 계산으로 찾아요." };
  if (!date) return { ok: false, reason: "날짜를 골라 주세요." };
  const [from, to] = stops;
  const depart = from.depart || "";
  const arrive = to.arrive_by || "";
  if (!depart && !arrive) return { ok: false, reason: "도착 마감이나 출발 시각 중 하나는 정해 주세요." };
  const when = [koDate(date, todayIso)];
  if (depart) when.push(`${koTime(depart)} 이후에 출발해서`);
  if (arrive) when.push(`${koTime(arrive)}까지`);
  const tail = [budget ? `${wonText(Number(budget))} 이하로` : "", PRIORITY_TEXT[priority] || ""].filter(Boolean).join(", ");
  const text = `${when.join(" ")} ${placeName(from)}에서 ${placeName(to)} 가야 해` + (tail ? `. ${tail}` : "");
  return { ok: true, text };
}
