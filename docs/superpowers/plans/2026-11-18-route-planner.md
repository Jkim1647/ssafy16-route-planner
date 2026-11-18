# 이동 플래너 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 출발지·도착지·마감·예산을 말하면 외부 API로 확인한 값만으로 도보·지하철·버스·열차·택시 이동 옵션을 계산해 제안·저장하는 Agent 플래너(F3001~F3023, NF3001~NF3007 전부).

**Architecture:** FastAPI 백엔드(`backend/`)가 LangGraph Agent(분석→계획→실행→판단→응답, 재계획 루프)를 돌리고, Tool은 레지스트리에 등록된 순수 함수(ok/fail 규약), 판단은 LLM 없는 순수 코드(`agent/judge.py`). 실행 이벤트는 프로세스 내 버스로 발행되고 로깅 Agent가 SQLite에 append. 프론트(`frontend/`)는 바닐라 JS로 대화·실행 과정·계획·로그 화면.

**Tech Stack:** Python 3.10+, FastAPI, SQLite(sqlite3), LangGraph, langchain-openai(GMS), Chroma, Google Calendar API, requests, pytest(개발용), HTML/CSS/JS.

**Spec:** `docs/superpowers/specs/2026-11-18-route-planner-design.md` (이하 "설계" — 장 번호로 참조)

## Global Constraints

- 라이브러리 버전 고정: langgraph==1.2.10, langchain==1.3.14, langchain-openai==1.4.3, langchain-core==1.6.0, langchain-text-splitters==1.1.2, openai==2.54.0, python-dotenv==1.2.3, requests==2.34.2, langsmith==0.10.17, typing-extensions==4.16.0, fastapi==0.141.1, uvicorn[standard]==0.52.4, pydantic==2.13.5, google-api-python-client==2.201.0, google-auth-oauthlib==1.5.0, google-auth-httplib2==0.4.3, chromadb==1.5.9. 개발용 추가는 `pytest` 하나만.
- 프로젝트 루트: `C:\SSAFY\workspace\AI 코어 PJT-Agent\route-planner\`. 모든 경로는 이 루트 기준.
- API 키는 `.env`에서만 읽는다. `.env`, `token.json`, `credentials.json`, `data/app.db`, `data/chroma/`, `data/cache/`, `.venv/` 커밋 금지(NF3001).
- Tool은 예외를 밖으로 던지지 않는다. 반환은 `{"ok": True, "data": ...}` / `{"ok": False, "error": {"code", "message"}}`. 빈 값은 `None`(""·0 금지).
- 실패 코드 집합: `BAD_ARGUMENT, INVALID_KEY, NOT_FOUND, NO_DATA, UPSTREAM_ERROR, AMBIGUOUS_PLACE, OUT_OF_RANGE, NO_INDEX, RATE_LIMITED`.
- 오류 메시지·이벤트·화면에 키나 키가 든 URL을 넣지 않는다(NF3002).
- 시각·요금·소요시간 숫자는 Tool 결과와 `judge.py` 계산에서만 나온다. LLM이 만든 숫자는 응답에 남기지 않는다(설계 5.6).
- 상수: `BOARD_BUFFER_MIN=10`, 기본 `buffer_min=10`, `MAX_REPLAN=3`, `WORKER_MAX_RETRY=2`, `RAIN_POP=60`, `WALK_WARN_MIN=10`, `INTRACITY_KM=40`, 외부 호출 timeout 10초.
- 시간대는 Asia/Seoul. 날짜 `YYYY-MM-DD`, 시각 `HH:MM` 문자열을 API 경계에서 사용, 내부는 `datetime`.
- 좌표는 카카오 규약 `x=경도, y=위도`.
- 커밋은 매 Task 끝. 단, git 저장소 생성·첫 커밋·push는 사용자 확인 후 실행(사용자 git 규칙). 일자별 최소 1커밋(제출 규정).
- 2일차 17:00 이후 새 Task 착수 금지. Task 0~23은 그 전에 모두 **착수**되어 있어야 한다.

## Review Focus

1. 동명 장소("중앙역", "시청")·오탈자 → 임의로 하나를 고르지 않고 `AMBIGUOUS_PLACE`로 후보를 보여 주며 되묻는다. → Task 3 `test_search_places_ambiguous`, Task 14 `test_ambiguous_place_asks_user`.
2. 자정을 넘는 열차·이동(23:40 출발 → 다음날 02:10 도착) → 도착 시각이 다음 날짜로 계산되어야 한다. → Task 4 `test_search_trains_overnight_arrival`, Task 13 `test_overnight_option_arrival_next_day`.
3. 이미 지난 마감("오늘 오전 9시까지", 지금 11시) → Tool 호출 없이 "마감이 이미 지났다"고 되묻는다(재계획 아님). → Task 12 `test_past_deadline_is_missing_condition`.
4. 출발지와 도착지가 같은 곳이거나 1km 이내 → 열차 조회 없이 도보/대중교통 옵션만, 오류 없음. → Task 13 `test_intracity_when_close`, Task 14 `test_same_place_no_train_call`.
5. 외부 API 하나가 timeout/429 → 해당 Tool만 실패로 기록, 나머지로 응답, 재계획하지 않음. → Task 2 `test_fetch_json_429_is_rate_limited`, Task 14 `test_upstream_failure_no_replan`.

---

## Phase A — 1일차 (게이트 14:00, 커밋 day1 18:00 전)

### Task 0: 프로젝트 골격

**Files:**
- Create: `requirements.txt`, `.gitignore`, `.env.example`, `backend/__init__.py`, `backend/settings.py`, `tests/__init__.py`, `tests/conftest.py`, `pytest.ini`
- Test: `tests/test_settings.py`

**Interfaces:**
- Produces: `backend.settings.Settings` (frozen dataclass) 필드 = 설계 14장 키 전부. 문자열 키는 없으면 `None`. `AGENT_MODE: Literal["single","planner_worker"]="single"`, `WORKER_LLM: bool=True`, `MAX_REPLAN:int=3`, `WORKER_MAX_RETRY:int=2`, `LOGGING_ENABLED:bool=True`, `CALENDAR_BACKEND: Literal["local","google"]="local"`, `DEBUG_FORCE: str|None=None`, `DB_PATH: str="data/app.db"`, `CHROMA_DIR: str="data/chroma"`.
- Produces: `backend.settings.get_settings() -> Settings` (env를 매번 다시 읽음, 테스트가 monkeypatch 가능), `Settings.key_status() -> dict[str, bool]` (키 이름 → 설정 여부).

- [ ] **Step 1:** `python -m venv .venv` 후 활성화, `requirements.txt`(Global Constraints 버전 + `pytest`) 작성, `pip install -r requirements.txt`. Expected: 오류 없이 설치.
- [ ] **Step 2: 실패 테스트** `tests/test_settings.py`
  - `test_missing_key_is_none`: `monkeypatch.delenv("ODSAY_API_KEY", raising=False)` → `get_settings().ODSAY_API_KEY is None`
  - `test_key_status_has_no_values`: 키를 `"secret123"`으로 set → `key_status()["ODSAY_API_KEY"] is True` 이고 `"secret123" not in str(key_status())`
  - `test_bool_and_int_parsing`: `WORKER_LLM="off"` → `False`, `MAX_REPLAN="5"` → `5`
- [ ] **Step 3:** `pytest tests/test_settings.py -v` → FAIL(모듈 없음).
- [ ] **Step 4:** `backend/settings.py` 구현(`load_dotenv()` 후 `os.getenv`). bool은 `{"1","true","on","yes"}`만 True.
- [ ] **Step 5:** PASS 확인. `.gitignore`(Global Constraints 목록 + `__pycache__/`), `.env.example`(키 이름만, 값 비움) 작성.
- [ ] **Step 6:** (사용자 확인 후) `git init`, 커밋 `chore: 프로젝트 골격`.

### Task 1: 외부 API 실호출 확인 스크립트 (전환 게이트)

**Files:**
- Create: `scripts/check_apis.py`, `docs/기획검증.md`, `tests/fixtures/` (응답 샘플 JSON)

**Interfaces:**
- Produces: `tests/fixtures/{kakao_local,kakao_category,tago_city,tago_stations,tago_train,tago_train_empty,odsay,odsay_empty,kakao_mobility,kma,its,tago_bus}.json` — 실제 응답을 키 제거 후 저장. 이후 모든 Tool 테스트가 이 파일을 쓴다.
- Produces: 각 API의 **확정된** 엔드포인트·파라미터·응답 필드 이름을 `docs/기획검증.md` 표로 기록(이후 Task가 이 표를 따른다).

확인 대상(설계 4·6장, 필드명은 기억 기반 → 여기서 확정):

| API | 호출 | 확인할 값 |
|---|---|---|
| 카카오 로컬 | `GET https://dapi.kakao.com/v2/local/search/keyword.json` (헤더 `Authorization: KakaoAK {KAKAO_REST_KEY}`) `query="벡스코"`, `query="광주송정역"` | `documents[].place_name, address_name, x, y, place_url` |
| TAGO 도시·역 목록 | `TrainInfoService/getCtyCodeList`, `getCtyAcctoTrainSttnList(cityCode)` | `nodeid, nodename` |
| **TAGO 열차** | `getStrtpntAlocFndTrainInfo(depPlaceId, arrPlaceId, depPlandTime=YYYYMMDD)` — **오늘+1, +3, +7일** 각각 | 미래 날짜 응답 여부, `depplandtime, arrplandtime, traingradename, trainno, adultcharge` |
| ODsay | `searchPubTransPathT(SX,SY,EX,EY,apiKey)` 시내 구간 | `path[].info.totalTime, payment, busTransitCount, subwayTransitCount, totalWalk`, 결과 없음 응답 |
| 카카오 모빌리티 | `GET https://apis-navi.kakaomobility.com/v1/directions?origin=x,y&destination=x,y` | `routes[0].summary.duration, distance, fare.taxi, fare.toll, bound` |
| 기상청 | `VilageFcstInfoService_2.0/getVilageFcst(base_date, base_time, nx, ny, dataType=JSON)` | `POP, PTY, TMP`의 `fcstDate/fcstTime`, 범위 |
| ITS 돌발 | `openapi.its.go.kr` eventInfo (bbox) | 유형·설명·기간·좌표 필드 |
| TAGO 고속버스 | `ExpBusInfoService` 터미널 목록·구간 조회 | 미래 날짜·운임 |
| GMS | `ChatOpenAI(base_url=GMS_BASE_URL, api_key=GMS_API_KEY, model=LLM_MODEL).invoke("ping")` + `bind_tools([dummy])` 1회 + 임베딩 1회 | 응답, tool_calls 선택 여부, 임베딩 지원 여부 |

- [ ] **Step 1:** `scripts/check_apis.py` — 각 API를 1회 호출하고 `[API] OK/FAIL 상태코드 핵심필드요약`을 출력, 응답을 `serviceKey/apiKey/Authorization` 문자열 제거 후 fixtures로 저장. 인자 `--only tago_train` 등 개별 실행 지원.
- [ ] **Step 2:** `python scripts/check_apis.py` 실행. Expected: 핵심 3종(카카오 로컬, TAGO 열차, ODsay) OK.
- [ ] **Step 3: 게이트 판정** — 다음을 `docs/기획검증.md`에 기록: (a) TAGO 열차가 오늘+1/+3/+7일 시간표와 `adultcharge`를 주는가, (b) 카카오 "광주송정역" 이름 → TAGO `nodename` "광주송정" 매칭이 되는가(5개 역: 광주송정, 용산, 서울, 부산, 동대구), (c) 결과 없음·빈 값 실제 응답 형태, (d) 각 API 호출 한도·약관 링크(NF3007), (e) 대표 요청마다 "Tool 없이 LLM만으로 답하면 틀리는 점" 한 줄.
- [ ] **Step 4:** **(a) 또는 (b)가 실패하면 여기서 중단하고 사용자에게 공연 플래너 전환을 보고한다.** 통과 시 커밋 `docs: 외부 API 기획 검증`.

### Task 2: Tool 공통 규약·레지스트리·HTTP 헬퍼

**Files:**
- Create: `backend/tools/__init__.py`, `backend/tools/base.py`, `backend/tools/registry.py`, `backend/tools/http.py`
- Test: `tests/tools/test_base.py`

**Interfaces:**
- Produces (`base.py`): `ok(data) -> dict`, `fail(code: str, message: str) -> dict`, 상수 `BAD_ARGUMENT ... RATE_LIMITED`, `@dataclass Tool(name: str, description: str, parameters: dict, func: Callable[..., dict], kind: Literal["external","local"])` + `Tool.run(**kwargs) -> dict` (TypeError→`BAD_ARGUMENT`, 기타 예외→`UPSTREAM_ERROR`, 메시지는 고정 문구).
- Produces (`registry.py`): `register(tool: Tool) -> Tool`, `get_tool(name: str) -> Tool | None`, `catalog(kind: str | None = None) -> list[dict]`(name, description, parameters만), `all_tools() -> dict[str, Tool]`.
- Produces (`http.py`): `fetch_json(url: str, *, params: dict | None = None, headers: dict | None = None) -> dict` → ok(body) 또는 fail: 401/403→`INVALID_KEY`, 429→`RATE_LIMITED`, timeout·연결오류·5xx·JSON 아님→`UPSTREAM_ERROR`. 메시지에 URL·params 포함 금지. timeout=10.
- Produces (`backend/tools/budget.py`, 설계 19장): `ApiBudget(db_path, settings, today: Callable[[], date])` — `cached_call(api: str, args: dict, ttl_sec: int, fn: Callable[[], dict]) -> dict` : 캐시 적중이면 `{"ok":..., "data":..., "cached": True}`, 아니면 쿼터 확인 → 초과 시 fn 호출 없이 `fail(RATE_LIMITED, "오늘 {api} 조회 한도에 도달했어요.")` → 호출 → **ok 결과만** 캐시 저장 → 사용량 +1(실패 응답도 사용량은 증가). `usage() -> dict[str, {"used","limit"}]`. `normalize_args(args) -> str`(좌표 키 `sx,sy,ex,ey,x,y,lat,lon`은 소수 3자리 반올림, sort_keys JSON). 테이블 `api_cache(key, value_json, expires_at)`, `api_quota(day, api, used)`를 `init_db`와 별개로 자체 생성. 한도: odsay 30(예약 6, `QUOTA_USE_RESERVE`일 때만 사용), its 하루 4·월 100, 그 외 무제한.
- Produces (`tests/conftest.py`): autouse fixture `no_network` — `requests.get`을 호출하면 테스트 실패(모든 Tool 테스트는 fixture monkeypatch 필수).

- [ ] **Step 1: 실패 테스트**
  - `test_run_type_error_becomes_bad_argument`: func이 인자 1개인데 `run(x=1, y=2)` → `error.code == "BAD_ARGUMENT"`
  - `test_run_exception_becomes_upstream`: func이 `raise ValueError("secretkey")` → code `UPSTREAM_ERROR`, `"secretkey" not in message`
  - `test_catalog_only_public_fields`: `set(catalog()[0]) == {"name","description","parameters"}`
  - `test_fetch_json_429_is_rate_limited`(Review Focus 5): `requests.get` monkeypatch → status 429 → `RATE_LIMITED`
  - `test_fetch_json_timeout`: `requests.Timeout` → `UPSTREAM_ERROR`, message에 `"serviceKey"` 없음
  - `test_budget_cache_hit_no_second_call`: 같은 args 두 번 → fn 1회, 두 번째 `cached=True`, used 1
  - `test_budget_coords_rounded_share_cache`: `x=126.79312` 와 `x=126.79349` → 같은 키
  - `test_budget_odsay_stops_at_24_without_reserve`: used 24 → 25번째는 fn 호출 없이 `RATE_LIMITED`; `QUOTA_USE_RESERVE=true`면 30까지
  - `test_budget_failure_not_cached`: fn이 fail 반환 → 다음 호출 때 fn 다시 호출
  - `test_budget_resets_next_day`: today를 하루 뒤로 → used 0
- [ ] **Step 2:** FAIL 확인 → **Step 3:** 구현 → **Step 4:** `pytest tests/tools/test_base.py -v` PASS → **Step 5:** 커밋 `feat: Tool 공통 규약과 레지스트리`.

### Task 3: 장소·역 Tool (`search_places`, `find_stations`) — F3004, F3002 보조

**Files:**
- Create: `backend/tools/kakao_local.py`, `backend/tools/stations.py`
- Test: `tests/tools/test_kakao_local.py`, `tests/tools/test_stations.py`

**Interfaces:**
- Consumes: Task 2 `fetch_json`, `register`, fixtures.
- Produces: `search_places(query: str, near_x: float | None = None, near_y: float | None = None) -> dict` → `data = {"places": [{"name","address","x","y","place_url"}]}`. 결과 0 → `NO_DATA`. 상위 결과들의 `place_name`이 정규화 후 동일한데 주소의 시·군·구가 서로 다르면 → `AMBIGUOUS_PLACE`, `message`에 후보 이름+주소 최대 3개.
- Produces: `find_stations(x: float, y: float, radius_km: float = 20) -> dict` → `data={"stations":[{"station_id","name","x","y","distance_km"}]}`(가까운 순, 최대 3). 카카오 키워드 `"기차역"` 반경 검색 결과를 TAGO 역 목록과 `normalize_station_name(name: str) -> str`(공백, 끝의 "역", 괄호 제거)으로 매칭. TAGO 역 목록은 `data/cache/stations.json`에 캐시(없으면 도시 목록→도시별 역 목록 호출 후 저장). 매칭 0 → `NO_DATA`.
- Produces: `haversine_km(x1, y1, x2, y2) -> float` (`stations.py`, judge가 재사용).

- [ ] **Step 1: 실패 테스트**
  - `test_search_places_ok`: fixture `kakao_local` → 첫 결과 `name/x/y` 존재, `x`는 float
  - `test_search_places_empty_query`: `""` → `BAD_ARGUMENT`
  - `test_search_places_no_key`: `KAKAO_REST_KEY` 삭제 → `INVALID_KEY`, HTTP 호출 없음
  - `test_search_places_ambiguous`(Review Focus 1): "중앙역" 두 도시 결과 fixture → `AMBIGUOUS_PLACE`
  - `test_normalize_station_name`: `"광주송정역"→"광주송정"`, `"서울역 (KTX)"→"서울"`
  - `test_find_stations_matches_tago`: 카카오 결과 "광주송정역" + 캐시 `{"광주송정": "NAT..."}` → `station_id == "NAT..."`
  - `test_haversine_seoul_busan`: 서울역↔부산역 ≈ 325±10km
- [ ] **Step 2~4:** FAIL → 구현·`register` → PASS.
- [ ] **Step 5:** 커밋 `feat: 장소·역 검색 Tool`.

### Task 4: 열차 Tool (`search_trains`) — F3002 필수

**Files:** Create `backend/tools/tago_train.py` / Test `tests/tools/test_tago_train.py`

**Interfaces:**
- Produces: `search_trains(dep_station_id: str, arr_station_id: str, date: str | None = None) -> dict` → `data={"date_requested","date_queried","estimated": bool,"estimated_reason": str|None,"trains":[{"train_no","grade","dep_at","arr_at","fare"}]}`. `dep_at/arr_at`는 ISO datetime 문자열. `date` 없으면 오늘(Asia/Seoul) — 기본값 F3002. 요청 날짜 결과가 비고 Task 1에서 "미래 날짜 미제공"이 확인된 경우에만 같은 요일 최근 날짜로 재조회하고 `estimated=True`(설계 18-2). `fare` 없으면 `None`.

- [ ] **Step 1: 실패 테스트**
  - `test_search_trains_ok`: fixture → `trains[0]["dep_at"]` 파싱 가능, `fare` int
  - `test_search_trains_default_date_is_today`: date 생략 → `date_requested == today`
  - `test_search_trains_missing_fare_is_none`: fixture에서 `adultcharge` 제거 → `fare is None`
  - `test_search_trains_overnight_arrival`(Review Focus 2): 23:40 출발·02:10 도착 → `arr_at` 날짜가 하루 뒤
  - `test_search_trains_empty`: `tago_train_empty` → `NO_DATA`
  - `test_search_trains_bad_date`: `"2026-13-40"` → `BAD_ARGUMENT`
- [ ] **Step 2~4:** FAIL → 구현 → PASS. **Step 5:** 커밋 `feat: 열차 조회 Tool`.

### Task 5: 대중교통 구간 Tool (`get_transit_route`) — F3003 필수

**Files:** Create `backend/tools/odsay.py` / Test `tests/tools/test_odsay.py`

**Interfaces:**
- 모든 외부 Tool(Task 3~7, 17)은 HTTP 호출을 `ApiBudget.cached_call(api, args, ttl, fn)`로 감싼다(TTL은 설계 19-1).
- Produces: `get_transit_route(sx: float, sy: float, ex: float, ey: float) -> dict` → `data={"paths":[{"total_min","fare","transfers","walk_min","legs":[{"mode": "walk|subway|bus","name": str|None,"min": int|None}]}]}` (최대 3, 소요시간 순). `walk_min` = 도보 합계 분(ODsay가 m로 주면 80m/분으로 환산하지 말고 legs의 도보 시간 합 사용; 시간 필드가 없으면 `None`). 결과 없음 → `NO_DATA`.

- [ ] **Step 1: 실패 테스트** `test_transit_ok`(total_min·fare int), `test_transit_no_result`(→`NO_DATA`), `test_transit_no_key`(→`INVALID_KEY`), `test_transit_legs_modes_subset`(mode ∈ {walk,subway,bus}).
- [ ] **Step 2~4** → **Step 5:** 커밋 `feat: 대중교통 구간 Tool`.

### Task 6: 자동차·택시 Tool (`get_car_route`) — F3003 보충

**Files:** Create `backend/tools/kakao_mobility.py` / Test `tests/tools/test_kakao_mobility.py`

**Interfaces:**
- Produces: `get_car_route(sx, sy, ex, ey) -> dict` → `data={"duration_min","distance_km","taxi_fare","toll","bbox":[min_x,min_y,max_x,max_y]}`. 분은 올림. 경로 없음 → `NO_DATA`.

- [ ] **Step 1:** `test_car_route_ok`(sec→min 올림: 1830초→31), `test_car_route_no_route`, `test_car_route_no_key`.
- [ ] **Step 2~4** → **Step 5:** 커밋 `feat: 택시·자동차 구간 Tool`.

### Task 7: 날씨 Tool (`get_weather`) — F3004

**Files:** Create `backend/tools/kma_weather.py` / Test `tests/tools/test_kma_weather.py`

**Interfaces:**
- Produces: `latlon_to_grid(lat: float, lon: float) -> tuple[int, int]` (기상청 LCC 격자 변환 공식), `latest_base_time(now: datetime) -> tuple[str, str]`(발표시각 02,05,08,11,14,17,20,23시 + API 제공 10분 지연 반영), `get_weather(lat: float, lon: float, at: str) -> dict` → `data={"at","pop": int|None,"pty": str|None,"temp": float|None}`. `at`이 응답 예보 범위 밖이면 `OUT_OF_RANGE`.

- [ ] **Step 1:** `test_grid_seoul`(37.5665,126.9780 → (60,127)), `test_grid_gwangju_songjeong`(Task 1 실제 값으로 확정), `test_base_time_before_0210`(02:05 → 전날 2300), `test_weather_out_of_range`(+5일 → `OUT_OF_RANGE`), `test_weather_ok`.
- [ ] **Step 2~4** → **Step 5:** 커밋 `feat: 날씨 Tool`.

### Task 8: Tool 단독 실행 데모 + 1일차 문서 + day1 커밋

**Files:** Create `scripts/tools_demo.py`, `docs/요구사항정의서.md`(v1), `README.md`(골격)

**Interfaces:**
- Consumes: Task 2~7 레지스트리.
- Produces: `python scripts/tools_demo.py` 출력 = 카탈로그(`[Tool] 이름 — 설명`) + Tool마다 정상/빈 입력/키 없음/결과 없음 4줄(`tools_start.py`와 같은 형식). 명세 4.1 증빙.

- [ ] **Step 1:** 데모 스크립트 작성(키 없음은 `os.environ.pop` 후 복원).
- [ ] **Step 2:** 실행. Expected: 핵심 Tool 3종 정상 `True`, 나머지 3케이스 `False CODE`.
- [ ] **Step 3:** `docs/요구사항정의서.md` v1 — 도메인 근거(설계 1·4장), 요구사항 표 F3001~F3023·NF3001~NF3007(이 도메인 표현), 기획 검증 결과(Task 1 기록 링크).
- [ ] **Step 4:** 출력 캡처를 `docs/screenshots/day1_tools.png`로 저장.
- [ ] **Step 5:** `pytest -q` 전체 PASS → 커밋 `feat: day1 Tool 단독 실행` → (사용자 확인 후) lab.ssafy.com `AICorePJT03` 하위 `AI코어프로젝트3_이동플래너_광주_03_김진영`에 push.

---

## Phase B — 2일차 (17:00까지 Task 9~23 착수)

### Task 9: LLM 클라이언트와 호출 카운터

**Files:** Create `backend/agent/__init__.py`, `backend/agent/llm.py` / Test `tests/agent/test_llm.py`

**Interfaces:**
- Produces: `get_llm(temperature: float = 0) -> BaseChatModel` (GMS `ChatOpenAI`), `class LLMCounter` (`count: int`, `wrap(llm) -> llm`), `structured(llm, schema: type[BaseModel], messages: list) -> BaseModel` — `llm.with_structured_output(schema).invoke(messages)` 호출 + 카운트. 키 없음이면 `LLMUnavailable` 예외(노드에서 잡아 "LLM 키 설정 안내"로 응답).
- Produces (테스트 공용): `tests/fakes.py`의 `FakeLLM(responses: list[BaseModel | str])` — `with_structured_output(schema).invoke()`가 순서대로 반환.

- [ ] **Step 1:** `test_structured_counts_calls`(FakeLLM 2회 호출 → counter 2), `test_get_llm_without_key_raises`.
- [ ] **Step 2~4** → **Step 5:** 커밋.

### Task 10: DB 스키마와 저장소

**Files:** Create `backend/db/__init__.py`, `backend/db/database.py`, `backend/db/repositories.py`, `backend/schemas.py` / Test `tests/db/test_plans.py`, `tests/db/test_events.py`

**Interfaces:**
- Produces (`database.py`): `connect(path: str) -> sqlite3.Connection`(row_factory=Row, 호출마다 새 연결), `init_db(path: str) -> None` (설계 9장 5개 테이블, `CREATE TABLE IF NOT EXISTS`).
- Produces (`schemas.py`, Pydantic): `PlanIn(title: str, date: date, leave_at: str /*HH:MM*/, arrive_at: str, origin_name: str, destination_name: str, legs: list[dict] = [], total_fare: int | None = None, source_run_id: str | None = None)`, `PlanUpdate`(위 필드 중 수정 가능 6개 모두 Optional), `PlanOut(PlanIn + id: int, calendar_event_id: str | None, created_at: datetime, updated_at: datetime)`, `PlanSaveResult(plan: PlanOut, overlaps: list[PlanOut])`. `arrive_at`이 `leave_at`보다 이르면 다음날 도착으로 보고 허용(자정 넘김).
- Produces (`repositories.py`): `PlanRepo(db_path)`: `create(PlanIn) -> PlanSaveResult`, `list() -> list[PlanOut]`(date, leave_at 순), `get(id) -> PlanOut | None`, `update(id, PlanUpdate) -> PlanSaveResult | None`, `delete(id) -> bool`, `set_calendar_event(id, event_id) -> None`, `find_overlaps(date, leave_at, arrive_at, exclude_id=None) -> list[PlanOut]`(구간 `[leave_at, arrive_at)` 교집합).
- Produces: `EventRepo`: `append(event: dict) -> None`, `list_sessions() -> list[dict]`(`session_id, run_count, last_ts, warn_count`), `get_session(session_id) -> list[dict]`(seq 순), `get_run(run_id) -> list[dict]`, `delete_session(session_id) -> bool`(run_events, runs, anomaly_reports 함께 삭제). **update 메서드 없음.**
- Produces: `RunRepo`: `start(run_id, session_id, user_message, mode)`, `finish(run_id, status, replan_count, llm_calls)`; `AnomalyRepo`: `save(run_id, verdict, findings, diagnosis=None)`, `set_diagnosis(run_id, text)`, `get(run_id) -> dict | None`.

- [ ] **Step 1: 실패 테스트**
  - `test_create_plan_has_created_at`
  - `test_overlap_same_date_reported_but_saved`: 10:00–12:00 저장 후 11:00–13:00 저장 → 두 번째 결과 `overlaps` 길이 1, `list()` 길이 2 (F3015)
  - `test_touching_ranges_not_overlap`: 10:00–12:00 과 12:00–13:00 → overlaps 0
  - `test_update_rechecks_overlap`, `test_delete_returns_false_when_missing`
  - `test_events_ordered_by_seq`, `test_sessions_isolated`(세션 A·B 이벤트 섞이지 않음), `test_delete_session_cascades`, `test_event_repo_has_no_update`(`not hasattr(EventRepo, "update")`)
- [ ] **Step 2~4** → **Step 5:** 커밋 `feat: 계획·로그 저장소`.

### Task 11: 이벤트 버스와 로깅 Agent — F3012, F3013

**Files:** Create `backend/events/__init__.py`, `backend/events/bus.py`, `backend/events/logger_agent.py` / Test `tests/events/test_bus.py`

**Interfaces:**
- Produces: `class EventBus`: `subscribe(fn: Callable[[dict], None]) -> None`, `publish(event: dict) -> None`(구독자별 try/except, 예외는 `logging.warning`만).
- Produces: `class Emitter(bus, session_id, run_id)`: `emit(type: str, *, agent: str = "main", node: str | None = None, payload: dict | None = None, duration_ms: int | None = None) -> dict` (seq 자동 증가, ts ISO). 이벤트 키 = 설계 8.2.
- Produces: `class LoggerAgent(event_repo)`: `__call__(event) -> None` (repo.append, 실패는 삼킴+warning). LLM 의존 없음.
- Produces: `build_bus(settings) -> EventBus` — `LOGGING_ENABLED`면 LoggerAgent 구독.

- [ ] **Step 1:** `test_publish_without_subscribers_ok`, `test_failing_subscriber_does_not_raise`, `test_emitter_seq_increments`, `test_logger_agent_appends_in_order`, `test_logging_disabled_no_subscriber`, `test_logger_agent_does_not_import_llm`(`"langchain" not in sys.modules` 검사 대신 `logger_agent.py` 소스에 `llm` import 없음을 `ast`로 확인).
- [ ] **Step 2~4** → **Step 5:** 커밋 `feat: 이벤트 버스와 로깅 Agent`.

### Task 12: 조건 모델·병합·누락 검사 — F3005, F3010

**Files:** Create `backend/agent/conditions.py` / Test `tests/agent/test_conditions.py`

**Interfaces:**
- Produces: `class Conditions(BaseModel)` = 설계 5.2 필드(`origin, destination, date, arrive_by, depart_after, budget, buffer_min=10, priority="cheapest", modes=None, avoid=[]`, 시각은 `"HH:MM"` 문자열).
- Produces: `merge(old: Conditions | None, changes: dict) -> Conditions` (changes에 있는 키만 갱신, `None` 값은 "지우기"로 해석하지 않고 무시 — 지우려면 키 `"_clear": [필드]`).
- Produces: `missing_fields(c: Conditions, now: datetime) -> list[str]` → `origin`/`destination`/`date`/`time`(arrive_by·depart_after 둘 다 없음)/`past_deadline`(같은 날 arrive_by ≤ now).

- [ ] **Step 1:** `test_merge_only_changed`(S7: depart_after만 바뀌고 나머지 유지), `test_missing_when_no_date`(S6), `test_past_deadline_is_missing_condition`(Review Focus 3), `test_defaults_not_invented`(빈 dict → budget None, origin None).
- [ ] **Step 2~4** → **Step 5:** 커밋.

### Task 13: 옵션 조립과 판단 — F3008 (LLM 없음, 핵심)

**Files:** Create `backend/agent/judge.py` / Test `tests/agent/test_judge.py`

**Interfaces:**
- Consumes: Task 3 `haversine_km`, Task 12 `Conditions`.
- Produces dataclasses: `Leg(mode: str, name: str | None, minutes: int | None, fare: int | None, source: str)`, `Option(id: str, kind: Literal["intercity","intracity"], legs: list[Leg], leave_at: datetime | None, arrive_at: datetime | None, total_fare: int | None, estimated: bool = False, warnings: list[str] = [], basis: dict = {})`, `Busy(title: str, start: datetime, end: datetime)`, `Judgment(passed: list[Option], excluded: list[tuple[Option, str]], undetermined: list[tuple[Option, str]], estimated: list[Option])`.
- Produces: `is_intracity(ox, oy, dx, dy, same_station: bool) -> bool` (`< INTRACITY_KM` 또는 같은 역).
- Produces: `build_intercity_options(trains: list[dict], access: Leg-set, egress: Leg-set) -> list[Option]` — 열차마다 출발 구간 후보(대중교통, 택시) × 도착 구간 후보 조합. 대중교통 구간 `minutes is None`이면 택시 Leg로 대체하고 `warnings`에 "대중교통 정보 없음 → 택시 기준"(설계 18-5). `leave_at = dep_at − BOARD_BUFFER_MIN − access.minutes`, `arrive_at = arr_at + egress.minutes`, `total_fare` = 합(하나라도 None → None).
- Produces: `build_intracity_options(paths: list[dict], car: dict | None, conds: Conditions, date: date) -> list[Option]` — 설계 18-3 식.
- Produces: `evaluate(options: list[Option], conds: Conditions, busy: list[Busy], now: datetime) -> Judgment` — 설계 5.3 통과 조건 그대로. 사유 문구 고정 형식: `"도착 {HH:MM} > 마감 {HH:MM}"`, `"출발 {HH:MM} < 가능 시각 {HH:MM}"`, `"총 {N}원 > 예산 {M}원"`, `"캘린더 '{title}' {HH:MM}–{HH:MM}과 겹침"`, undetermined: `"운임 정보 없음 — 예산 판단 불가"`, `"구간 소요시간 확인 불가"`. `estimated=True` 옵션은 `estimated` 그룹으로만.
- Produces: `rank(passed: list[Option], priority: str) -> list[Option]` — 1순위 + 최저가/최단/환승최소 대표, 중복 제거, 최대 3.
- Produces: `apply_warnings(options, weather: dict[str, dict], road_events: list[dict], avoid: list[str]) -> list[Option]` — 설계 5.3 경고 규칙(POP≥60 & 도보≥10분). `"비" in avoid`면 경고 대신 제외 사유 반환을 위해 `evaluate` 전에 호출되어 `basis["rain_block"]=True`를 표시.

- [ ] **Step 1: 실패 테스트** (값은 설계 그대로)
  - `test_leave_and_arrive_formula`: 열차 07:02→09:00, 출발구간 20분, 도착구간 25분 → leave 06:32, arrive 09:25
  - `test_arrive_by_with_buffer`: arrive_by 09:30, buffer 10 → 09:25 통과, 09:21 도착 통과, 09:22? (경계: `arrive_at ≤ 09:20`만 통과) → 09:25는 제외 사유 `"도착 09:25 > 마감 09:20"`
  - `test_budget_none_fare_is_undetermined`
  - `test_calendar_overlap_excluded`: busy 07:00–08:00, 이동 06:32–09:25 → 제외 사유 `"캘린더 '팀 회의' 07:00–08:00과 겹침"`
  - `test_destination_event_not_excluded`: busy 14:00–15:00, arrive 13:40 → 통과(설계 18-7)
  - `test_estimated_never_passed`
  - `test_transit_none_falls_back_to_taxi`
  - `test_overnight_option_arrival_next_day`(Review Focus 2)
  - `test_intracity_when_close`(Review Focus 4): 0.5km → `is_intracity` True
  - `test_rank_max_three_unique`
  - `test_rain_warning_rule`: POP 70, 도보 12분 → 경고 1개, POP 50 → 0개
- [ ] **Step 2~4** → **Step 5:** 커밋 `feat: 제약 판단 계산`.

### Task 14: Agent 그래프(단일 모드) — F3005~F3011

**Files:** Create `backend/agent/state.py`, `backend/agent/prompts.py`, `backend/agent/nodes.py`, `backend/agent/graph.py`, `backend/agent/service.py` / Test `tests/agent/test_graph.py`

**Interfaces:**
- Consumes: Task 2 레지스트리, Task 9 `structured`, Task 11 `Emitter`, Task 12, Task 13.
- Produces (`state.py`): `AgentState(TypedDict)` = 설계 7.2 필드.
- Produces (`nodes.py`) 구조화 출력 스키마: `AnalyzeOut(intent: Literal["plan_trip","modify","fact_query","terms_query","save_plan","register_calendar","chat"], intent_reason: str, changes: dict, option_ref: int | None)`, `PlanOut(tasks: list[TaskSpec])`, `TaskSpec(id: str, tool: str, args: dict, depends_on: list[str] = [], fixed_args: list[str] = [])`. 인자 값 `"$<task_id>.<path>"`는 이전 결과 참조.
- Produces 노드: `analyze(state) -> dict`, `clarify(state)`, `plan(state)`(LLM 출력 검증: 미등록 Tool·스키마 위반 task 제거, `plan_tasks` 이벤트), `execute(state)`(참조 해석·펼치기·캐시 `(tool, json.dumps(args, sort_keys=True))`, 실패 기록 후 계속, `tool_call/tool_result` 이벤트에 `task_id, cached, duration_ms`), `judge_node(state)`, `replan(state)`(설계 5.4 전략 순서, 비재계획 사유 판정), `respond(state)`(LLM 요약 + `numbers_ok(text, cards) -> bool` 검사: 텍스트의 `\d{1,2}:\d{2}`와 `\d[\d,]*원`이 카드 값 집합에 없으면 템플릿 문장으로 대체), `action(state)`(save_plan: `option_ref`로 직전 카드 → `PlanRepo.create`).
- Produces (`graph.py`): `build_graph(deps: Deps) -> CompiledGraph` (`MemorySaver`, 라우팅 = 설계 7.1 다이어그램), `@dataclass Deps(llm, bus, plan_repo, run_repo, settings, now: Callable[[], datetime])`.
- Produces (`service.py`): `run_turn(deps, session_id: str, message: str) -> TurnResult` — TurnResult(Pydantic) = `run_id, session_id, reply, cards: list[dict], excluded: list[dict], undetermined: list[dict], estimated: list[dict], warnings: list[str], clarification: str | None, replan_count: int, llm_calls: int, events: list[dict]`. 이벤트는 run 동안 Emitter가 모은 사본. `run_start/run_end` 발행, `RunRepo.start/finish`.

- [ ] **Step 1: 실패 테스트** (FakeLLM + 레지스트리를 fake Tool로 교체, 외부 호출 없음)
  - `test_chat_skips_plan`: intent chat → `tool_call` 이벤트 0 (S5)
  - `test_missing_condition_asks`: S6 → `clarification` 있음, tool_call 0
  - `test_ambiguous_place_asks_user`(Review Focus 1)
  - `test_full_flow_events_order`: node_start/end 순서 analyze→plan→execute→judge→respond, analyze 종료 payload에 `intent_reason`
  - `test_tool_failure_continues`: 열차 하나 상세 실패해도 응답 생성 (S4)
  - `test_replan_reuses_cache`: 1회차 통과 0 → replan → 같은 args 호출이 `cached=true`
  - `test_replan_limit_stops`: 항상 통과 0 → `replan_count == 3`, reply에 조정 질문 (S3)
  - `test_upstream_failure_no_replan`(Review Focus 5): INVALID_KEY → replan 0
  - `test_followup_keeps_conditions`: 같은 session_id로 S1 → S7, 두 번째 run의 조건에서 date·destination 유지
  - `test_respond_number_guard`: FakeLLM이 카드에 없는 "08:15" 출력 → 템플릿으로 대체
  - `test_same_place_no_train_call`(Review Focus 4)
  - `test_odsay_calls_capped_per_run`: 열차 5편·거점 확장 재계획이 있어도 run 내 `get_transit_route` 실호출(cached=false) ≤ 4 (설계 19-3)
  - `test_rate_limited_falls_back_to_taxi_no_replan`: ODsay `RATE_LIMITED` → 카드 경고 "대중교통 조회 한도 초과 → 택시 기준", replan 0
  - `test_its_called_once_after_judge`: `get_road_events` 호출은 judge 이후 최대 1회, 택시·버스 구간 없으면 0회
  - `test_main_works_without_logger`: `LOGGING_ENABLED=false`로 정상 응답(4.3)
- [ ] **Step 2~4** → **Step 5:** `python -c "from backend.agent.graph import ...; print(build_graph(deps).get_graph().draw_mermaid())"`로 그래프 구조 출력 → `docs/screenshots/graph.md` 저장(4.2 증빙) → 커밋 `feat: 단일 Agent 그래프`.

### Task 15: FastAPI 서버 — F3014, F3015, F3016, F3017

**Files:** Create `backend/main.py`, `backend/api/{__init__,chat,plans,logs,meta}.py`, `backend/deps.py` / Test `tests/api/test_api.py`

**Interfaces:**
- Consumes: Task 10 저장소, Task 14 `run_turn`.
- Produces: 설계 10장 경로 전부. 요청·응답은 Task 10·14 Pydantic 모델. `POST /api/plans`는 `{"run_id": str, "option_ref": int}` 또는 `PlanIn`(Union) → `PlanSaveResult` 201. `DELETE` 204. 없는 id 404 `{"detail":"Not Found"}`. 로그 라우터에 PUT/PATCH 없음. `GET /api/config/status` = `Settings.key_status()`. 예외 핸들러: 500 응답은 `{"detail":"서버 오류가 발생했어요."}`만.
- CORS: `allow_origins=["http://127.0.0.1:5500","http://localhost:5500"]`.
- 실행: `uvicorn backend.main:app --reload` (8000).

- [ ] **Step 1:** `TestClient` 테스트: `test_plan_crud_roundtrip`, `test_plan_overlap_in_response`, `test_logs_list_detail_delete`, `test_logs_no_put`(PUT → 405), `test_config_status_booleans_only`, `test_chat_returns_events`(deps를 FakeLLM으로 override), `test_500_hides_detail`.
- [ ] **Step 2~4** → **Step 5:** `/docs` 화면 캡처 `docs/screenshots/api_docs.png` → 커밋 `feat: FastAPI 서버`.

### Task 16: 프론트엔드 — F3018, F3019

**Files:** Create `frontend/index.html`, `frontend/css/app.css`, `frontend/js/{api,chat,timeline,plans,logs,app}.js`

**Interfaces:**
- Consumes: Task 15 API(`API_BASE="http://127.0.0.1:8000/api"`).
- Produces 화면(설계 11장 스케치): 탭 3개, 대화(입력·처리 중 스피너·카드·제외/판단불가/추정 그룹·경고·저장 버튼), 실행 과정 타임라인(seq 순, agent 배지, `replan` 이벤트는 구분선 "재계획 N: 사유", Tool 인자·결과 요약·ms), 계획 탭(목록·상세·수정 폼·삭제·캘린더 등록·겹침 알림), 로그 탭(세션 목록→상세 타임라인 재사용, 이상 판정 배지·진단).
- 키 누락 안내: 시작 시 `/config/status` 조회 → false인 키 이름으로 상단 배너 "OO 키가 설정되지 않았어요(.env 확인)".
- 오류 응답은 `detail`만 표시. 모든 사용자 텍스트는 `textContent`로 삽입(innerHTML 금지).

- [ ] **Step 1:** Live Server(5500)로 열고 서버(8000) 실행.
- [ ] **Step 2:** 브라우저에서 S1, S5, S6 요청 → 카드·타임라인 표시, 콘솔 오류 0, CORS 오류 0.
- [ ] **Step 3:** 계획 저장 → 계획 탭 즉시 반영 → 수정 → 삭제 반영, 겹침 저장 시 알림(S10).
- [ ] **Step 4:** `ODSAY_API_KEY` 제거 후 재시작 → 배너와 "택시 기준" 경고 표시(S4).
- [ ] **Step 5:** 화면 캡처 `docs/screenshots/chat.png, plans.png, logs.png` → 커밋 `feat: 대화·계획·로그 화면`.

### Task 17: 확장 Tool — 카카오 모빌리티 연결 확인, ITS 돌발, 고속버스, (선택) TourAPI

**Files:** Create `backend/tools/its_events.py`, `backend/tools/tago_bus.py`, (선택) `backend/tools/tour_events.py` / Test `tests/tools/test_its_events.py`, `tests/tools/test_tago_bus.py`

**Interfaces:**
- Produces: `get_road_events(bbox: list[float], date: str) -> dict` → `data={"realtime": bool, "events":[{"type","description","start","end","x","y"}]}`. `date`가 오늘이 아니면 `end`가 있고 그 날짜를 포함하는 이벤트만(설계 5.3).
- Produces: `search_express_bus(dep_terminal_id, arr_terminal_id, date=None) -> dict` → `search_trains`와 같은 모양(`trains` 대신 `buses`, `grade`, `fare`). `find_terminals(x, y)`는 `find_stations`와 같은 매칭 방식(`data/cache/terminals.json`).
- Judge 연동: `build_intercity_options`가 `buses`도 간선으로 받도록 `trunks: list[dict]`(필드 `kind: "train"|"bus"`)로 일반화 — Task 13 테스트가 계속 통과해야 함.

- [ ] **Step 1:** `test_events_future_date_filters_realtime`, `test_events_empty_is_ok_with_empty_list`(결과 없음은 실패가 아니라 빈 목록 — 경고 없음), `test_bus_ok`, `test_bus_empty`.
- [ ] **Step 2~4** → **Step 5:** 커밋 `feat: 돌발정보·고속버스 Tool`.

### Task 18: 이상 징후 판정 — F3020

**Files:** Create `backend/events/anomaly.py` / Test `tests/events/test_anomaly.py`

**Interfaces:**
- Consumes: Task 10 `EventRepo.get_run`, `AnomalyRepo`, Task 9 `structured`.
- Produces: `judge_run(events: list[dict], max_replan: int) -> dict` (LLM 없음) → `{"verdict": "ok"|"warn"|"undetermined", "findings": [{"rule","detail","event_seqs"}]}`. 규칙 = 설계 8.4 + 18-4(`task_id` 없는 호출 또는 task의 tool과 다른 호출 = `UNPLANNED_CALL`; Worker 재시도 이벤트에 `retry_of`가 있으면 제외; `cached=true`는 DUPLICATE에서 제외).
- Produces: `diagnose(llm, events, findings) -> str | None` (warn일 때만, 3문장 이내 요청, 실패 시 None).
- Produces: `evaluate_and_store(run_id, deps) -> dict` — 판정 저장 → warn이면 진단 저장. `service.run_turn` 끝에서 호출(로깅 활성 시). `get_verdict(run_id) -> dict | None`(Planner 참조용).
- `DEBUG_FORCE` 처리: `execute`에서 `duplicate`면 첫 Tool을 캐시 우회로 한 번 더, `unplanned`면 task 밖 `get_weather` 1회, `replan`이면 첫 judge 결과를 통과 0으로 강제.

- [ ] **Step 1:** `test_duplicate_detected`, `test_cached_not_duplicate`, `test_unplanned_detected`, `test_retry_not_unplanned`, `test_excessive_replan`(replan 2 → warn), `test_no_evidence_undetermined`(plan_tasks·tool_call 없음 → `undetermined`), `test_normal_run_ok_and_no_llm`(FakeLLM 호출 0), `test_diagnosis_failure_keeps_verdict`.
- [ ] **Step 2~4** → **Step 5:** 커밋 `feat: 이상 징후 판정`.

### Task 19: Planner·Worker 모드 — F3021

**Files:** Create `backend/agent/planner_worker.py` / Modify `backend/agent/graph.py`(모드 분기) / Test `tests/agent/test_planner_worker.py`

**Interfaces:**
- Consumes: Task 14 노드(analyze·judge·respond 재사용), Task 18 `judge_run`.
- Produces: `build_pw_graph(deps) -> CompiledGraph` — 노드 `planner_analyze → planner_plan → worker → verify → judge → (respond | planner_replan)`. 이벤트 `agent="planner"|"worker"|"logger"`.
- Produces: `WorkerDecision(BaseModel)(action: Literal["retry","skip","request_replan"], new_args: dict = {}, reason: str)`. LLM 호출 조건 = 설계 7.3 표. `new_args`가 `fixed_args` 키를 바꾸면 결정 무효 → `skip`으로 기록. 재시도 이벤트 `retry_of=<원 호출 seq>`. `WORKER_LLM=off`면 판단 없이 `skip`.
- verify: `judge_run` 결과 warn & 규칙이 DUPLICATE/UNPLANNED → `planner_replan`(실행당 1회, replan 사유 `verify`). 설계 18-6.
- `build_graph(deps)`는 `settings.AGENT_MODE`로 단일/PW 선택. `run_turn` 인터페이스 불변.

- [ ] **Step 1:** `test_worker_no_llm_on_success`(정상 경로 Worker LLM 0), `test_worker_no_llm_on_invalid_key`, `test_worker_retry_on_no_data`(NO_DATA → retry → 성공), `test_worker_cannot_change_fixed_args`, `test_worker_request_replan_reaches_planner`, `test_verify_warn_triggers_one_rebuild`, `test_worker_llm_off_skips`.
- [ ] **Step 2~4** → **Step 5:** 커밋 `feat: Planner·Worker 모드`.

### Task 20: RAG Tool — F3022

**Files:** Create `scripts/build_index.py`, `backend/tools/rag.py`, `data/docs/SOURCES.md` / Test `tests/tools/test_rag.py`

**Interfaces:**
- Produces: `python scripts/build_index.py` — `data/docs/*.pdf|*.txt|*.md` 로드 → `RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=100)` → 임베딩(Task 1에서 GMS 임베딩 지원 확인 시 `OpenAIEmbeddings(base_url=GMS_BASE_URL, model=EMBEDDING_MODEL)`, 아니면 Chroma 기본) → `chromadb.PersistentClient(CHROMA_DIR)` 컬렉션 `"terms"`, 메타데이터 `source, title, page`.
- Produces: `search_terms(question: str, k: int = 4) -> dict` → `data={"chunks":[{"text","source","title","page"}]}`. 컬렉션 없음/비어 있음 → `NO_INDEX`. `kind="local"`. 설명: "열차·버스 환불·위약금·지연 보상 규정이나 기상특보 행동요령처럼 시간표 API로 확인할 수 없는 규정을 물을 때".
- 응답 연동: `terms_query` 의도는 계획 `[search_terms]` → respond가 근거 문단과 출처를 카드(`type: "source"`)로 표시.

- [ ] **Step 1:** 사용자에게 원문 확보 요청: 코레일 여객운송약관, 고속버스 운송약관, 기상특보 행동요령 → `data/docs/`, 출처·수집일을 `SOURCES.md`에.
- [ ] **Step 2:** `test_no_index_code`(빈 임시 디렉터리 → `NO_INDEX`), `test_search_returns_sources`(임시 디렉터리에 문서 2개 색인 후 질의 → `source` 존재).
- [ ] **Step 3~4** FAIL→구현→PASS, 실제 색인 후 S8 질문으로 수동 확인.
- [ ] **Step 5:** 커밋 `feat: 약관 RAG Tool`.

### Task 21: 캘린더 — F3023 (로컬 먼저)

**Files:** Create `backend/calendar/{__init__,base,local,google}.py`, `backend/tools/calendar_tools.py` / Modify `backend/api/plans.py`(`POST /api/plans/{id}/calendar`) / Test `tests/calendar/test_calendar.py`

**Interfaces:**
- Produces: `class CalendarBackend(Protocol)`: `get_free_busy(day: date) -> list[Busy]`, `create_event(plan: PlanOut) -> str`. `LocalCalendar(db_path)`(table `local_calendar`), `GoogleCalendar(calendar_id, token_path="token.json", credentials_path="credentials.json")`(scope `https://www.googleapis.com/auth/calendar.events` + freeBusy용 `calendar.readonly`; `InstalledAppFlow.run_local_server` 최초 1회). `get_calendar(settings) -> CalendarBackend`.
- Produces Tool: `get_free_busy(date: str) -> dict` → `data={"busy":[{"title","start","end"}]}`(Google freeBusy는 제목이 없으므로 `title="일정"`), `register_calendar(plan_id: int) -> dict` → `data={"event_id"}`, 스키마에 `plan_id`만. 없는 plan → `NOT_FOUND`. 성공 시 `PlanRepo.set_calendar_event`.
- Agent 연동: `plan_trip` 계획에 `get_free_busy(date)` 포함 → `judge.evaluate(busy=...)`.

- [ ] **Step 1:** `test_local_free_busy_roundtrip`, `test_register_reads_plan_from_repo`(Tool 인자에 시각 없음, 이벤트 시각 = plan 값), `test_register_unknown_plan_not_found`, `test_backend_swap_same_shape`(Local과 Google mock의 Tool 출력 키 동일).
- [ ] **Step 2~4** → **Step 5:** 커밋 `feat: 캘린더 Tool(로컬)`.
- [ ] **Step 6 (3일차 오전):** 사용자가 Google Cloud OAuth 클라이언트 생성·`credentials.json` 배치 → `CALENDAR_BACKEND=google`로 S9 실행 → 캡처 → 커밋 `feat: Google Calendar 연동`.

### Task 22: 모드 비교 실험 스크립트 — F3021 비교

**Files:** Create `scripts/compare_modes.py`

**Interfaces:**
- Consumes: Task 14 `run_turn`, 실제 LLM·API.
- Produces: `python scripts/compare_modes.py` → S1, S2, S3, S4, S7 각각을 (single) / (planner_worker, WORKER_LLM=off) / (planner_worker, WORKER_LLM=on)으로 실행, 표 `요청 | 모드 | 재계획(no_option/verify/worker_request) | LLM 호출 수 | Worker LLM 호출 수 | 응답 ms | 최종 통과 수`를 `docs/비교결과.md`에 기록.

- [ ] **Step 1:** 스크립트 작성 → **Step 2:** 실행, 표 생성 확인 → **Step 3:** 커밋 `docs: 구조 비교 결과`.

### Task 23: day2 마감 점검

- [ ] **Step 1:** `pytest -q` 전체 PASS.
- [ ] **Step 2:** 16:30 기준 Task 17~21 중 착수 안 된 것 즉시 착수(골격+첫 테스트 커밋)해 17:00 규정 충족.
- [ ] **Step 3:** 커밋 `chore: day2` → (사용자 확인 후) push.

---

## Phase C — 3일차

### Task 24: 대표 시나리오 검증과 산출물

**Files:** Create/Modify `docs/검증결과.md`, `docs/실행로그샘플.md`, `docs/Agent설계.md`, `docs/Tool정의서.md`, `docs/API명세서.md`, `docs/셀프체크리스트.md`, `README.md`, `docs/screenshots/*`

- [ ] **Step 1:** S1~S10 실행 → 각 시나리오 최종 응답·실행 로그(재계획 여부, Tool 이력)·기대 vs 실제 차이·수정 내용을 `docs/검증결과.md` 표로.
- [ ] **Step 2:** 명세 4.1~4.8 확인 항목별 캡처 매핑(항목 → 파일). 4.3 "로깅 Agent 없이 동작"은 `LOGGING_ENABLED=false` 실행 캡처. 4.6 F3020은 `DEBUG_FORCE=duplicate|unplanned|replan` 세 실행 + 판정 불가 사례.
- [ ] **Step 3:** `docs/실행로그샘플.md` — S1 전체 이벤트 JSON + S2 재계획 사례.
- [ ] **Step 4:** `docs/Agent설계.md`(설계 5·7·8장 정리 + 그래프 그림 + LLM 호출 조건 표), `docs/Tool정의서.md`(설계 6장 + 실제 확정 파라미터 + 등록·확장 방법), `docs/API명세서.md`(FastAPI `/openapi.json` 기반 표).
- [ ] **Step 5:** README — 개요, 실행 방법(venv, `.env` 작성, `uvicorn`, Live Server, 색인 빌드), 기능 설명(필수/심화 구분) + 캡처·GIF, API 키 발급 절차, 외부 API 출처·이용 조건 표, 심화 요약.
- [ ] **Step 6:** NF 점검: `git grep -nE "(KakaoAK [A-Za-z0-9]|serviceKey=|apiKey=)[A-Za-z0-9]"` 결과 0, 화면 오류 원문 노출 없음, 대표 요청 응답 시간 기록.
- [ ] **Step 7:** 셀프 체크리스트(배포본) 작성 → 커밋 `docs: day3 산출물` → (사용자 확인 후) push.
