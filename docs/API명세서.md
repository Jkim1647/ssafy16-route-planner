# API 명세서

- 서버: FastAPI (`uvicorn backend.main:app --port 8000`), 문서 화면 `http://127.0.0.1:8000/docs`, 원본 스키마 `docs/openapi.json`
- 요청·응답은 JSON, 모델은 Pydantic(`backend/schemas.py`, `backend/agent/service.py`)
- CORS: `http://127.0.0.1:5500`, `http://localhost:5500`만 허용
- 오류: 없는 리소스 404 `{"detail": "..."}`, 입력 검증 실패 422, 처리 중 예외 500 `{"detail": "서버 오류가 발생했어요."}`(원문은 서버 로그에만, NF3002)

공통 보안 규칙
- Host 헤더가 `127.0.0.1`·`localhost`가 아니면 400(악성 도메인을 127.0.0.1로 바꿔치기하는 DNS rebinding 차단).
- CORS는 프론트 `http://127.0.0.1:5500`·`http://localhost:5500`만 허용. 서버는 127.0.0.1에만 바인딩.
- 계획 입력 상한: 제목·출발지·도착지 100자, `legs` 30개(구간 이름 100자, `path` 좌표 400개), `points` 10개, `total_fare` 0~10,000,000. 넘으면 422.

## 1. 대화

### `POST /api/chat`
요청
```json
{ "message": "토요일 오후 2시까지 광주 첨단동에서 서울 강남역, 6만원 이하", "session_id": null }
```
- `message` 1~500자, `session_id`는 생략하면 새로 발급(같은 값을 보내면 대화 맥락 유지, F3010)

응답 `TurnResult`
| 필드 | 타입 | 설명 |
|---|---|---|
| `run_id`, `session_id` | string | 이번 실행·세션 식별자 |
| `reply` | string | 최종 응답 문장(숫자는 카드 값만, 고정 안내 포함) |
| `cards` | object[] | 추천 경로 카드(최대 3) 또는 규정 근거(`type: "source"`) |
| `cards[].legs` | object[] | `{mode, name, minutes, fare, source}` — 도보·지하철·버스·열차·택시 구간 |
| `cards[].basis` | object | 판단 근거: 열차 출발·도착, 승차 여유 10분, 역까지/목적지까지 분·요금, 라벨 |
| `cards[].risk` | object\|null | 지각 위험 `{level: 넉넉·보통·빠듯, absorb_min, text}` — 예: "36분 늦어져도 마감 안". 마감 없는 요청은 `null` |
| `cards[].legs[].path` | number[][]\|null | 지도 동선 좌표 `[[x, y], …]` — 버스·지하철은 정류장, 택시는 도로. 열차·도보는 `null` |
| `cards[].checks` | object[] | 판단 결과 `{kind: deadline·depart·budget·calendar, text}` — 예: "마감 14:00까지 여유 36분", "예산 60,000원 중 16,800원 남음", "그날 일정 1건과 안 겹침" |
| `decision` | object\|null | 판단 요약 `{checked, passed, dominated(모든 면에서 밀려 추천에서 뺀 수), excluded_by: {마감·예산·일정·출발 시각·날씨: 개수}, undetermined, estimated}` |
| `cards[].points` | object[] | 지도용 지점 `{kind: origin·dep_station·arr_station·destination, name, x, y}` — Tool 결과(장소·역·터미널) 좌표 |
| `excluded` | object[] | `{summary, reason}` 제외 후보와 사유(예: "도착 15:40 > 마감 13:50") |
| `undetermined` | object[] | 판단하지 않은 후보(운임·소요시간 확인 불가) |
| `estimated` | object[] | 추정 시간표 후보(통과 아님) |
| `warnings` | string[] | 우천·돌발·택시 대체 안내 |
| `clarification` | string\|null | 되묻기 문장 |
| `status` | string | `done` · `clarify` · `no_option` · `error` · `llm_unavailable` |
| `intent` | string | 분석된 의도 |
| `replan_count`, `llm_calls` | int | 재계획·LLM 호출 횟수 |
| `events` | object[] | 이번 실행의 이벤트(실행 과정 표시용) |

## 2. 이동 계획 (F3015·F3016)

| 메서드·경로 | 요청 | 응답 |
|---|---|---|
| `GET /api/plans` | - | `PlanOut[]` (날짜·출발시각 순) |
| `POST /api/plans` | `PlanIn` | 201 `PlanSaveResult{plan, overlaps}` — 같은 날 시간 겹치는 계획을 `overlaps`로 알림(저장은 함) |
| `GET /api/plans/{plan_id}` | - | `PlanOut` / 404 |
| `PUT /api/plans/{plan_id}` | `PlanUpdate`(부분 수정) | `PlanSaveResult`(겹침 재검사) / 404 / 422 |
| `DELETE /api/plans/{plan_id}` | - | 204 / 404 |
| `POST /api/plans/{plan_id}/calendar` | `{}` (JSON 필수) | `{event_id, backend}` 캘린더 등록(F3023, 계획 ID만 받음) / 404 없음 / 409 이미 등록됨 / 415 JSON이 아닌 요청(다른 사이트의 폼 전송 차단) |

`PlanIn`
```json
{ "title": "첨단동 → 강남역", "date": "2026-11-21", "leave_at": "07:45", "arrive_at": "10:52",
  "origin_name": "광주 첨단동", "destination_name": "서울 강남역",
  "legs": [{"mode": "train", "name": "KTX-산천 00610", "minutes": 112, "fare": 40900, "source": "tago_train"}],
  "total_fare": 43700, "source_run_id": null,
  "points": [{"kind": "origin", "name": "쌍암공원 분수광장", "x": 126.84, "y": 35.22},
             {"kind": "dep_station", "name": "광주송정", "x": 126.79, "y": 35.14},
             {"kind": "arr_station", "name": "수서", "x": 127.10, "y": 37.49},
             {"kind": "destination", "name": "강남역 2호선", "x": 127.03, "y": 37.50}] }
```
- `points`(선택, 기본 `[]`): 지도 표시용 지점. 경로 카드의 `points`를 그대로 넘긴다. 같은 도시 안 이동은 출발지·도착지 2개.
- `leave_at`/`arrive_at`은 `HH:MM`, 도착이 출발보다 이르면 다음 날 도착(자정 넘김)으로 본다.
| `POST /api/plans/{plan_id}/recheck` | `{}` | 다시 확인(당일 재확인, LLM 없음) `{plan_id, status: ok·warn·partial·past, checked_at, items[{kind: time·train·calendar·weather·festival, level: ok·warn·info·unknown, text}]}` — ok는 모든 항목을 확인했을 때만, 확인 못 한 항목(unknown — 출발지·도착지 중 한쪽 예보만 받았거나 좌표가 없어 조회하지 못한 경우 포함)이 있으면 partial. 열차 시간표는 캐시 없이 조회 — 열차 번호가 그날 시간표에 남았는지, 이동 시간과 겹치는 일정('이동:' 일정 제외), 강수확률+도보, 도착지 행사, 출발 시각 경과 / 404 |
| `POST /api/plans/{plan_id}/share` | `{}` (JSON 필수) | `{token}` 읽기 전용 공유 토큰(144비트 무작위, 이미 있으면 그대로) / 404 내 계획 아님 / 415 |
| `DELETE /api/plans/{plan_id}/share` | - | 204 공유 끊기(이전 링크 즉시 무효) / 404 |
| `GET /api/shared/{token}` | **로그인 없이** | `{title, date, leave_at, arrive_at, origin_name, destination_name, legs, total_fare, points}` — 사용자·계획·캘린더·실행 ID는 보내지 않음. 주인이 '집'으로 저장한 곳 300m 안 지점은 약 500m 격자로 반올림·이름 '집 근처', 그 근처 동선 좌표는 제거(`home_hidden: true`) / 404 끊김·없음·형식 오류 |
| `GET /api/suggestions/calendar` | - | 앞으로 이틀 안의 장소 있는 캘린더 일정 최대 5개 `[{title, date, arrive_by, location, place: {name, address, x, y} \| null}]` — '이동:' 일정·종일·30분 안 시작 제외, 장소는 카카오 장소 검색으로 좌표화. 경로 계산·LLM 없음 |
- `PlanOut` = `PlanIn` + `id`, `calendar_event_id`, `share_token`(주인에게만), `created_at`, `updated_at`
- 캘린더 등록(Google)은 출발 15분·5분 전 팝업 알림을 함께 넣는다.

## 3. 실행 로그 (F3014 — 수정 API 없음)

| 메서드·경로 | 응답 |
|---|---|
| `GET /api/logs` | `[{session_id, run_count, last_ts, warn_count, first_message}]` 최근순 |
| `GET /api/logs/{session_id}` | `{session_id, events[], runs[{run_id, user_message, status, replan_count, llm_calls, anomaly}]}` — 이벤트는 실행 순서 |
| `DELETE /api/logs/{session_id}` | 204 (이벤트·실행·이상 판정 함께 삭제) / 404 |
| `GET /api/runs/{run_id}/anomaly` | `{verdict: ok\|warn\|undetermined, findings[{rule, detail, event_seqs}], diagnosis}` (F3020) |
| `PUT·PATCH /api/logs/...` | **없음** → 405 |

이벤트 공통 필드: `session_id, run_id, seq, ts, agent(main|planner|worker|logger), type, node, payload, duration_ms`
이벤트 종류: `run_start, run_end, node_start, node_end, llm_decision, plan_tasks, tool_call, tool_result, replan, worker_decision, verify, error`

## 4. 로그인 (`/api/auth`)
| 경로 | 요청 | 응답 |
|---|---|---|
| `GET /api/auth/me` | - | `{user: {id, email, name, picture}\|null, auth_required, google_configured}` |
| `GET /api/auth/google/login` | - | 302 → Google 동의 화면. `state`를 HttpOnly 쿠키에 저장(로그인 위조 방지). 설정 안 됨 503 |
| `GET /api/auth/google/callback?code&state` | - | state 일치·id_token 검증·이메일 인증 확인 후 세션 쿠키(`rp_session`, JWT, 7일, HttpOnly·SameSite=Lax) 설정 → 302 `FRONTEND_URL`. 실패 400 |
| `POST /api/auth/logout` | `{}` | 204, 세션 쿠키 삭제 |
- `AUTH_REQUIRED=true`이면 `/api/auth/*`·`/api/config/status` 외 모든 API는 로그인하지 않으면 401. 데이터(계획·장소·로그·로컬 캘린더)는 로그인한 사용자 것만 보이고, 다른 사용자 것은 404.

## 5. 내 장소 (`/api/places`)
| 경로 | 요청 | 응답 |
|---|---|---|
| `GET /api/places` | - | `PlaceOut[]` |
| `GET /api/places/search?q=` | 1~50자 | `[{name, address, x, y}]`(최대 5, 카카오 로컬) / 404 |
| `POST /api/places` | `PlaceIn{label(1~20자), kind(home·school·work·pin), name, address?, x, y}` | 201 `PlaceOut` / 409 같은 이름 있음 |
| `PUT /api/places/{id}` · `DELETE /api/places/{id}` | `PlaceIn` / - | `PlaceOut` / 204, 없으면 404 |

## 6. 여러 동선 (`/api/trips/plan`)
`POST` `TripIn{date, stops: StopIn[2~6]{name, address?, x, y, arrive_by?, stay_min(0~720)}, depart_after?, budget?, priority}`
→ `{legs: [{index, from, to, depart_after, arrive_by, status: done·walk·no_option·skipped, cards, decision, excluded, reason}], total_fare, start_at, end_at, warnings, run_id, session_id, status}`.
첫 구간의 출발 시각이나 첫 도착지 마감이 없으면 400. 앞 구간 도착 + 머무는 시간 = 다음 구간 출발 하한. LLM 없음, 실행 로그(세션 `trip-…`)에 기록.

## 7. 지도 (`/api/map`)
| 경로 | 요청 | 응답 |
|---|---|---|
| `POST /api/map/road-shape` | `{points: [[경도, 위도], …]}` 2~80개, 국내 좌표만 | `{path: [[경도, 위도], …]}`(최대 400점) — 버스 정류장을 차례로 경유하는 도로 좌표(카카오 길찾기, 경유지 5개씩 나눠 부르고 이어 붙임, 캐시). 못 찾으면 404 → 화면은 정류장 직선 유지 |
| `POST /api/map/walk-shape` | `{points: [[경도, 위도], [경도, 위도]]}` 정확히 2개, 국내·5km 이내 | `{path, distance_m}`(최대 200점) — 도보 구간을 실제 보행로를 따라 그리는 좌표(OpenStreetMap, FOSSGIS OSRM). 서버에서만 호출·7일 캐시·호출 간격 1초. 못 찾거나 꺼져 있으면(`WALK_ROUTE_ENABLED=false`) 404 → 화면은 직선 점선 |

## 8. 메타

| 메서드·경로 | 응답 |
|---|---|
| `GET /api/tools` | 등록 Tool `[{name, description, parameters}]` (Agent에 넘기는 정보 그대로) |
| `GET /api/config/status` | `{keys: {GMS_API_KEY: true, ...}, quota: {odsay: {used, limit}, its: {...}}, model, agent_mode, calendar}` — 키 값은 절대 포함하지 않음 |
