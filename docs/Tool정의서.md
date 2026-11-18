# Tool 정의서

## 1. 공통 규약 (F3001)
- 반환: 성공 `{"ok": true, "data": {...}}`, 실패 `{"ok": false, "error": {"code", "message"}}` — 예외를 밖으로 던지지 않는다(`Tool.run`이 TypeError→`BAD_ARGUMENT`, 그 밖→`UPSTREAM_ERROR`로 변환).
- 응답 원본을 통째로 넘기지 않고 판단에 쓸 값만 뽑는다. 비어 있는 값은 `""`·`0`이 아니라 `null`.
- 오류 메시지·로그에 키가 든 URL을 넣지 않는다(`backend/tools/http.py`).
- 외부 호출은 `ApiBudget.cached_call`을 거친다: 영구 캐시(좌표 소수 3자리 반올림 키) + 일일 쿼터(ODsay 30회 중 24회 평소 사용·6회 예약, ITS 하루 4·월 100회). 한도 도달 시 호출 없이 `RATE_LIMITED`.
- 실행 단위 재사용: 한 실행 안에서 같은 Tool·같은 입력은 다시 부르지 않고 이전 결과를 쓴다(F3009, 이벤트 `cached: true`).

| 실패 코드 | 의미 | 예 |
|---|---|---|
| `BAD_ARGUMENT` | 입력 규격 위반 | 빈 검색어, 날짜 형식 오류 |
| `INVALID_KEY` | 키 없음·틀림 | `.env` 누락, 401/403, 공공데이터포털 인증 오류 코드 |
| `NOT_FOUND` | 대상 없음 | 없는 계획 ID |
| `NO_DATA` | 조회는 됐지만 결과 없음 | 열차 0편, ODsay `error.code=5` |
| `UPSTREAM_ERROR` | 외부 서버 오류·시간 초과 | 5xx, timeout |
| `AMBIGUOUS_PLACE` | 같은 이름이 여러 시·도에 | "중앙역"(안산·부산) |
| `OUT_OF_RANGE` | 예보 범위 밖 | 5일 뒤 날씨 |
| `NO_INDEX` | RAG 색인 없음 | 문서 미색인 |
| `RATE_LIMITED` | 호출 한도 | ODsay 일일 한도 |

## 2. Tool 목록

### 외부 API 툴

| 이름 | 언제 쓰는지(설명) | 입력 | 출력(data) | API |
|---|---|---|---|---|
| `search_places` | 출발지·도착지 이름을 좌표·주소로 바꿀 때(가장 먼저) | `query`, `near_x?`, `near_y?` | `places[{name, address, x, y, place_url}]` | 카카오 로컬 키워드 검색 |
| `find_stations` | 좌표 근처 기차역과 TAGO 역 ID가 필요할 때 | `x`, `y`, `radius_km?=20` | `stations[{station_id, name, x, y, distance_km, ktx}]` (KTX 정차역 우선, 최대 3) | 카카오 로컬 + TAGO 역 목록(파일 캐시) |
| `search_trains` **(F3002 필수)** | 두 역 사이 특정 날짜 열차 시각·운임 | `dep_station_id`, `arr_station_id`, `date?=오늘` | `{date_requested, date_queried, estimated, trains[{train_no, grade, dep_at, arr_at, fare}]}` | TAGO 열차정보 `GetStrtpntAlocFndTrainInfo` |
| `get_transit_route` **(F3003 필수)** | 두 지점 사이 도보·지하철·버스 소요·요금 | `sx, sy, ex, ey` | `paths[{total_min, fare, transfers, walk_min, legs[{mode, name, min, path}]}]` (최대 3) — `path`: 버스·지하철이 지나는 정류장·역 좌표 `[[x, y], …]`(지도 동선), 도보는 `null` | ODsay `searchPubTransPathT` |
| `get_car_route` | 택시·자동차 시간·요금, 대중교통 실패·한도 시 대체 | `sx, sy, ex, ey` | `{duration_min, distance_km, taxi_fare, toll, bbox, path}` — `path`: 도로 좌표 `[[x, y], …]`(최대 120점으로 줄임) | 카카오 모빌리티 길찾기 |
| `get_weather` **(F3004)** | 이동 시각 강수확률(도보 구간 주의) | `lat, lon, at` | `{at, forecast_at, pop, pty, temp}` (3시간 간격 예보는 ±3시간 내 가장 가까운 시각) | 기상청 단기예보 |
| `get_road_events` | 최종 후보 도로 구간 주변 공사·사고 | `bbox[4]`, `date` | `{realtime, events[{type, detail, description, start, end, x, y}]}` (미래 날짜는 기간이 그날을 포함하는 것만) | ITS 돌발정보 |
| `find_terminals` | 고속버스 대안이 필요할 때 근처 터미널 ID | `x, y` | `terminals[{terminal_id, name, x, y, distance_km}]` | 카카오 로컬 + TAGO 터미널 목록 |
| `search_express_bus` | 두 터미널 사이 고속버스 시각·요금(재계획 수단 확장) | `dep_terminal_id, arr_terminal_id, date?` | `{buses[{train_no, grade, dep_at, arr_at, fare, kind:"bus"}]}` | TAGO 고속버스 `/ExpBusInfo` |

### 로컬 서버 API 툴

| 이름 | 언제 쓰는지 | 입력 | 출력 | 구현 |
|---|---|---|---|---|
| `search_terms` (F3022) | 환불 위약금·지연 보상처럼 시간표 API로 알 수 없는 규정 | `question`, `k?=4` | `chunks[{text, source, title, page, distance}]`, 색인 없으면 `NO_INDEX` | Chroma `data/chroma` + GMS 임베딩 |
| `get_free_busy` (F3023) | 이동 날짜의 기존 일정 확인(자정 넘김·전날 출발이면 여러 날) | `date`, `days`(1~3, 기본 1) | `{backend, busy[{title, start, end}]}` | `LocalCalendar` / `GoogleCalendar`(freeBusy) |
| `register_calendar` (F3023) | 저장한 계획을 캘린더에 등록 | `plan_id` **만** | `{event_id, backend}` | 제목·시각은 서버가 저장소에서 읽음 |

## 3. Tool 사이 값 전달
`search_places`(좌표) → `find_stations`(역 ID) → `search_trains`(역 ID·날짜) → `get_transit_route`/`get_car_route`(장소↔역 좌표) → `get_weather`(좌표·시각) → 판단 → `get_road_events`(출발지 bbox, 도로 구간이 있을 때만 1회)

## 4. 실패 처리 방식
| 상황 | 처리 |
|---|---|
| 장소 동명(`AMBIGUOUS_PLACE`) | Tool 호출 중단, 후보를 보여 주며 되묻기 |
| 대중교통 실패·한도(`NO_DATA`·`RATE_LIMITED`) | 택시 기준으로 대체하고 카드에 "대중교통 정보 없음/조회 한도 초과 → 택시 기준" |
| 운임 없음 | 예산 판단 불가(통과도 제외도 아님) |
| 구간 소요시간 없음 | 시간 판단 불가 |
| 키 오류·서버 오류(핵심 Tool) | 재계획하지 않고 안내(같은 결과가 반복되므로) |
| 열차 없음(일부 역 조합) | 사유 기록 후 나머지 조합으로 진행 |
| Planner·Worker 모드 | 고칠 인자가 있는 Tool(`find_stations`·`find_terminals` 반경)만 Worker LLM이 재시도 판단, 나머지는 규칙으로 건너뜀 |
| HTTP 200인데 결과 코드가 오류(TAGO·기상청·ITS) | 캐시 전에 실패(`INVALID_KEY`·`UPSTREAM_ERROR`)로 바꿔 캐시하지 않음 — 키를 고치면 바로 다시 조회 |
| 캘린더 조회 실패 | 판단은 계속하고 모든 후보 카드에 "캘린더 조회 실패" 경고 |
| 출발·도착 직선 700m 미만 | 경로 Tool을 부르지 않고 도보 안내(ODsay가 경로를 주지 않는 거리) |

## 5. 등록·확장 방법
1. `backend/tools/<이름>.py`에 함수 작성 → `ok()`/`fail()` 반환, 외부 호출은 `default_budget().cached_call(api, args, ttl, fn)`으로 감싼다.
2. 같은 파일에서 `register(Tool(name, description="언제 쓰는지", parameters=JSON Schema, func, kind="external"|"local"))`.
3. `backend/tools/catalog_all.py`에 모듈을 import.
4. 계획에 쓰려면 `backend/agent/executor.py`의 작업 템플릿(`PLAN_TRIP` 등)에 추가, 고정 인자는 `backend/agent/planner_worker.py`의 `FIXED_ARGS`에 등록.
5. `tests/fixtures/`에 실제 응답 샘플을 저장하고 `tests/tools/`에 정상·빈 입력·키 없음·결과 없음 테스트 작성(테스트는 네트워크 차단).
6. 확인: `python scripts/tools_demo.py`(카탈로그·4가지 케이스 출력), `GET /api/tools`.
