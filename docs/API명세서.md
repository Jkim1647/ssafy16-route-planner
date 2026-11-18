# API 명세서

- 서버: FastAPI (`uvicorn backend.main:app --port 8000`), 문서 화면 `http://127.0.0.1:8000/docs`, 원본 스키마 `docs/openapi.json`
- 요청·응답은 JSON, 모델은 Pydantic(`backend/schemas.py`, `backend/agent/service.py`)
- CORS: `http://127.0.0.1:5500`, `http://localhost:5500`만 허용
- 오류: 없는 리소스 404 `{"detail": "..."}`, 입력 검증 실패 422, 처리 중 예외 500 `{"detail": "서버 오류가 발생했어요."}`(원문은 서버 로그에만, NF3002)

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
| `POST /api/plans/{plan_id}/calendar` | - | `{event_id, backend}` 캘린더 등록(F3023, 계획 ID만 받음) / 404 |

`PlanIn`
```json
{ "title": "첨단동 → 강남역", "date": "2026-11-21", "leave_at": "07:45", "arrive_at": "10:52",
  "origin_name": "광주 첨단동", "destination_name": "서울 강남역",
  "legs": [{"mode": "train", "name": "KTX-산천 00610", "minutes": 112, "fare": 40900, "source": "tago_train"}],
  "total_fare": 43700, "source_run_id": null }
```
- `leave_at`/`arrive_at`은 `HH:MM`, 도착이 출발보다 이르면 다음 날 도착(자정 넘김)으로 본다.
- `PlanOut` = `PlanIn` + `id`, `calendar_event_id`, `created_at`, `updated_at`

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

## 4. 메타

| 메서드·경로 | 응답 |
|---|---|
| `GET /api/tools` | 등록 Tool `[{name, description, parameters}]` (Agent에 넘기는 정보 그대로) |
| `GET /api/config/status` | `{keys: {GMS_API_KEY: true, ...}, quota: {odsay: {used, limit}, its: {...}}, model, agent_mode, calendar}` — 키 값은 절대 포함하지 않음 |
