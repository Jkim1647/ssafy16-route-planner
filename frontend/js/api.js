// 백엔드 API 호출. 오류는 서버가 준 detail만 보여 준다(원문·키 노출 금지).
// 기본은 8000번. 다른 포트로 띄웠다면 index.html?api=http://127.0.0.1:8001/api 처럼 지정.
const API_BASE = new URLSearchParams(location.search).get("api") || "http://127.0.0.1:8000/api";

async function api(path, options = {}) {
  let res;
  try {
    res = await fetch(API_BASE + path, {
      headers: { "Content-Type": "application/json" },
      ...options,
      body: options.body ? JSON.stringify(options.body) : undefined,
    });
  } catch (e) {
    throw new Error("서버에 연결할 수 없어요. 백엔드(uvicorn)가 실행 중인지 확인해 주세요.");
  }
  if (res.status === 204) return null;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const d = data.detail;
    const msg = typeof d === "string" ? d : Array.isArray(d) ? "입력값을 확인해 주세요." : "요청을 처리하지 못했어요.";
    throw new Error(msg);
  }
  return data;
}
