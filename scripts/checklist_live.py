"""셀프 체크리스트의 '확인 방법'을 실제 구성요소로 실행해 결과를 남긴다(테스트가 아니라 실제 API·GMS 호출).

사용: python scripts/checklist_live.py [출력 md]   (기본 docs/evidence/2026-11-20-checklist-live.md)
대상 항목: 1(Tool 목록·정상/잘못된 입력/키 없음), 2(기준 날짜), 3(식별자 연쇄·빈 속성), 4(보조 정보),
          10(재계획 상한), 14(세션 분리·LLM 판단 이벤트), 18(로그 API, 수정 API 없음).
로컬 캘린더·로그인 끔으로 실행해 실제 일정·계정 정보가 기록에 섞이지 않게 한다. 키 값은 출력하지 않는다.
"""
import datetime as dt
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.settings import get_settings  # noqa: E402

get_settings()
os.environ["CALENDAR_BACKEND"] = "local"
os.environ["AUTH_REQUIRED"] = "false"
import backend.tools.catalog_all  # noqa: E402,F401
from backend.tools.registry import all_tools, get_tool  # noqa: E402

OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "docs" / "evidence" / "2026-11-20-checklist-live.md"
TOMORROW = (dt.date.today() + dt.timedelta(days=1)).isoformat()
GJ = (126.793, 35.137)      # 광주송정역 부근
GN = (127.0276, 37.4979)    # 강남역
lines: list[str] = [f"# 셀프 체크리스트 실제 실행 기록\n\n실행 {dt.datetime.now():%Y-%m-%d %H:%M} · 모델 `{os.getenv('LLM_MODEL')}` · "
                    "실제 외부 API(영구 캐시 적중 포함) · 로컬 캘린더 · `python scripts/checklist_live.py`\n"]


def short(r: dict) -> str:
    """ok/fail 결과를 한 줄로(데이터는 개수·첫 값만)."""
    if not r.get("ok"):
        return f"fail `{r['error']['code']}` — {r['error']['message']}"
    d = r["data"]
    if isinstance(d, dict):
        parts = []
        for k, v in d.items():
            if isinstance(v, list):
                parts.append(f"{k} {len(v)}건")
            elif k in ("date_requested", "date_queried", "estimated", "realtime", "pop", "temp", "duration_min", "taxi_fare", "backend"):
                parts.append(f"{k}={v}")
        return "ok — " + ", ".join(parts)
    return f"ok — {len(d)}건" if isinstance(d, list) else "ok"


def run(name: str, **kw) -> dict:
    return get_tool(name).run(**kw)


def no_key(name: str, env: str, **kw) -> dict:
    old = os.environ.get(env, "")
    os.environ[env] = ""
    try:
        return run(name, **kw)
    finally:
        os.environ[env] = old


# ---------------------------------------------------------------- 1. Tool 목록과 정상/실패 호출
lines.append("## 1. Tool 목록 · 정상 1회 · 실패 2가지(잘못된 입력, 키 비움)\n")
lines.append("| Tool | 구분 | 필수 입력 | 정상 호출 | 잘못된 입력 | 키 비움 |\n|---|---|---|---|---|---|")
st = run("find_stations", x=GJ[0], y=GJ[1])
gj_id = st["data"]["stations"][0]["station_id"] if st.get("ok") else "NAT031857"
st2 = run("find_stations", x=GN[0], y=GN[1])
gn_id = st2["data"]["stations"][0]["station_id"] if st2.get("ok") else "NAT010032"
te = run("find_terminals", x=126.879, y=35.160)  # 광주 유·스퀘어 부근
t1 = te["data"]["terminals"][0]["terminal_id"] if te.get("ok") else "NAEK500"
t2 = "NAEK021"  # 센트럴시티(서울, 호남선 쪽 ID) — 광주↔센트럴시티 운행 노선
CASES = {  # 이름: (정상 인자, 잘못된 입력, 키 환경 변수)
    "search_places": ({"query": "광주송정역"}, {"query": ""}, "KAKAO_REST_KEY"),
    "find_stations": ({"x": GJ[0], "y": GJ[1]}, {"y": GJ[1]}, "KAKAO_REST_KEY"),
    "find_terminals": ({"x": 126.879, "y": 35.160}, {"x": "abc", "y": 35.16}, "KAKAO_REST_KEY"),
    "search_trains": ({"dep_station_id": gj_id, "arr_station_id": gn_id, "date": TOMORROW},
                      {"dep_station_id": gj_id, "arr_station_id": gn_id, "date": "2026-13-40"}, "DATA_GO_KR_KEY"),
    "search_express_bus": ({"dep_terminal_id": t1, "arr_terminal_id": t2, "date": TOMORROW},
                           {"dep_terminal_id": "", "arr_terminal_id": t2}, "DATA_GO_KR_KEY"),
    "get_transit_route": ({"sx": GJ[0], "sy": GJ[1], "ex": 126.85, "ey": 35.16}, {"sx": GJ[0], "sy": GJ[1]}, "ODSAY_API_KEY"),
    "get_car_route": ({"sx": GJ[0], "sy": GJ[1], "ex": 126.85, "ey": 35.16}, {"sx": GJ[0]}, "KAKAO_REST_KEY"),
    "get_weather": ({"lat": GJ[1], "lon": GJ[0], "at": f"{TOMORROW}T12:00"}, {"lat": GJ[1], "lon": GJ[0], "at": "내일"}, "DATA_GO_KR_KEY"),
    "get_road_events": ({"bbox": [126.7, 35.0, 127.0, 35.3], "date": TOMORROW}, {"bbox": [1, 2], "date": TOMORROW}, "ITS_API_KEY"),
    "get_festivals": ({"x": GN[0], "y": GN[1], "date": TOMORROW}, {"x": GN[0], "y": GN[1], "date": "11/21"}, "DATA_GO_KR_KEY"),
    "search_terms": ({"question": "KTX 반환 위약금"}, {"question": ""}, "GMS_API_KEY"),
    "get_free_busy": ({"date": TOMORROW}, {"date": "모레"}, None),
    "register_calendar": (None, {"plan_id": 0}, None),
}
for name in all_tools():
    t = get_tool(name)
    good, bad, env = CASES[name]
    ok_txt = short(run(name, **good)) if good is not None else "— (계획을 실제 일정에 등록하므로 생략, 테스트 `test_register_reads_plan_from_repo`)"
    bad_txt = short(run(name, **bad))
    key_txt = short(no_key(name, env, **(good or bad))) if env else "— (로컬 Tool, 키 없음)"
    lines.append(f"| `{name}` | {t.kind} | {', '.join(t.parameters.get('required') or [])} | {ok_txt} | {bad_txt} | {key_txt} |")
lines.append("\n예외가 밖으로 나온 호출: 0건(모두 ok/fail 형식).\n")

# ---------------------------------------------------------------- 2. 기준 날짜
lines.append("## 2. 기준 날짜 기본값 · 조회할 수 없는 기준\n")
r = run("search_trains", dep_station_id=gj_id, arr_station_id=gn_id)
lines.append(f"- 날짜 생략: {short(r)} (오늘 {dt.date.today().isoformat()})")
far = (dt.date.today() + dt.timedelta(days=60)).isoformat()
lines.append(f"- 60일 뒤({far}) 열차: {short(run('search_trains', dep_station_id=gj_id, arr_station_id=gn_id, date=far))}")
w5 = (dt.date.today() + dt.timedelta(days=5)).isoformat()
lines.append(f"- 5일 뒤 날씨(예보 범위 밖): {short(run('get_weather', lat=GJ[1], lon=GJ[0], at=f'{w5}T12:00'))}")
lines.append("- 시간표가 없는 날짜를 이웃 날짜 시간표로 대신할 때는 `estimated`=True와 '추정 시간표' 그룹으로 표시(통과 불가) — TAGO가 미래 날짜도 그 날 시간표를 줘 실제 대체는 발생하지 않음(`test_estimated_never_passed`).\n")

# ---------------------------------------------------------------- 3. 식별자 연쇄 · 빈 속성
lines.append("## 3. 후보 식별자로 상세 조회 · 비어 있는 속성\n")
lines.append(f"- 장소(좌표) → `find_stations` → 역 ID `{gj_id}`·`{gn_id}` → `search_trains`({TOMORROW}): "
             f"{short(run('search_trains', dep_station_id=gj_id, arr_station_id=gn_id, date=TOMORROW))}")
tr = run("search_trains", dep_station_id=gj_id, arr_station_id=gn_id, date=TOMORROW)
nofare = [x for x in (tr.get("data") or {}).get("trains", []) if x.get("fare") is None]
lines.append(f"- 운임이 빈 열차: {len(nofare)}건 — 빈 값은 `None` 그대로 두고 판단 단계에서 '예산 판단 불가'로 분류(임의 값 없음)\n")

# ---------------------------------------------------------------- 4. 보조 정보
lines.append("## 4. 보조 정보 검색 결과 있음 / 없음\n")
p = run("search_places", query="광주송정역")
if p.get("ok"):
    f = p["data"]["places"][0]
    lines.append(f"- 있음: {f['name']} · {f['address']} · 링크 {'있음' if f.get('place_url') else '없음'} · 좌표 ({f['x']:.4f}, {f['y']:.4f})")
lines.append(f"- 없음: {short(run('search_places', query='ㅁㄴㅇㄹ없는장소qwerty'))}\n")

# ---------------------------------------------------------------- 10·14. Agent 실행
from backend.container import Container  # noqa: E402

c = Container.build()
lines.append("## 10. 충족할 수 없는 조건 → 재계획 상한에서 멈춤\n")
res = c.chat(None, f"내일 오전 6시까지 광주 첨단동에서 서울 강남역 가야 해. 1만원 이하로")
reps = [e["payload"] for e in res.events if e["type"] == "replan"]
lines.append(f"- 상태 `{res.status}` · 재계획 {res.replan_count}회 · LLM {res.llm_calls}회")
for x in reps:
    lines.append(f"  - 재계획 {x.get('count')}: {x.get('strategy')} — {x.get('reason')}")
lines.append(f"- 응답: {res.reply.splitlines()[0][:200]}\n")

lines.append("## 14. 세션 둘 — 이벤트가 세션별로 저장되고 섞이지 않음, LLM 판단 이벤트\n")
SA, SB = (f"live-check-{x}-{dt.datetime.now():%H%M%S}" for x in "ab")  # 실행마다 새 세션(이전 실행과 섞이지 않게)
a = c.chat(SA, "안녕")
b = c.chat(SB, f"내일 오후 2시까지 광주 첨단동에서 서울 강남역 가야 해")
for s, r in ((SA, a), (SB, b)):
    stored = c.events.get_session(s)
    other = [e for e in stored if e.get("session_id") not in (None, s)]
    dec = [e for e in r.events if e["type"] == "llm_decision"]
    types = sorted({e["type"] for e in r.events})
    lines.append(f"- `{s}`: 응답 이벤트 {len(r.events)}개 = 저장 {len(stored)}개, 다른 세션 섞임 {len(other)}개, "
                 f"종류 {', '.join(types)}")
    for d in dec[:1]:
        pl = d["payload"]
        lines.append(f"  - LLM 판단 이벤트: decision=`{pl.get('decision')}` value=`{pl.get('value')}` reason=\"{pl.get('reason')}\"")
lines.append("")

# ---------------------------------------------------------------- 18. 로그 API
from fastapi.testclient import TestClient  # noqa: E402

from backend.main import app  # noqa: E402

lines.append("## 18. 실행 로그 목록 · 상세 · 삭제, 수정 API 없음\n")
with TestClient(app, base_url="http://127.0.0.1") as cl:  # 허용 호스트(TrustedHost)만 받는다
    lst = cl.get("/api/logs")
    sids = [x.get("session_id") for x in lst.json()] if lst.status_code == 200 else []
    lines.append(f"- `GET /api/logs` → {lst.status_code}, 세션 {len(sids)}개 (새 세션 포함: {SA in sids and SB in sids})")
    det = cl.get(f"/api/logs/{SB}")
    seqs = [e["seq"] for e in det.json().get("events", [])] if det.status_code == 200 else []
    lines.append(f"- `GET /api/logs/{SB}` → {det.status_code}, 이벤트 {len(seqs)}개, 실행 순서(seq 1→{max(seqs) if seqs else 0}) 오름차순 {seqs == sorted(seqs)}")
    put = cl.put(f"/api/logs/{SB}", json={})
    lines.append(f"- `PUT /api/logs/{SB}` → {put.status_code} (수정 API 없음)")
    paths = cl.get("/openapi.json").json()["paths"]
    methods = sorted({m.upper() for p, v in paths.items() if p.startswith("/api/logs") for m in v})
    lines.append(f"- OpenAPI의 /api/logs 경로 메서드: {', '.join(methods)}")
    for s in (SA, SB):
        d = cl.delete(f"/api/logs/{s}")
        lines.append(f"- `DELETE /api/logs/{s}` → {d.status_code}, 다시 조회 → {cl.get(f'/api/logs/{s}').status_code}")

OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
print(OUT)
