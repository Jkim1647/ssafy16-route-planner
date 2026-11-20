# 셀프 체크리스트 실제 실행 기록

실행 2026-11-20 12:04 · 모델 `claude-haiku-5-5` · 실제 외부 API(영구 캐시 적중 포함) · 로컬 캘린더 · `python scripts/checklist_live.py`

## 1. Tool 목록 · 정상 1회 · 실패 2가지(잘못된 입력, 키 비움)

| Tool | 구분 | 필수 입력 | 정상 호출 | 잘못된 입력 | 키 비움 |
|---|---|---|---|---|---|
| `search_places` | external | query | ok — places 5건 | fail `BAD_ARGUMENT` — query는 필수입니다. | fail `INVALID_KEY` — KAKAO_REST_KEY가 설정되지 않았습니다. |
| `find_stations` | external | x, y | ok — stations 3건 | fail `BAD_ARGUMENT` — 입력값이 규약과 다릅니다. | fail `INVALID_KEY` — KAKAO_REST_KEY가 설정되지 않았습니다. |
| `get_free_busy` | local | date | ok — backend=local, busy 0건 | fail `BAD_ARGUMENT` — date는 YYYY-MM-DD 형식이어야 합니다. | — (로컬 Tool, 키 없음) |
| `register_calendar` | local | plan_id | — (계획을 실제 일정에 등록하므로 생략, 테스트 `test_register_reads_plan_from_repo`) | fail `BAD_ARGUMENT` — plan_id는 1 이상의 정수입니다. | — (로컬 Tool, 키 없음) |
| `get_road_events` | external | bbox, date | ok — realtime=False, events 1건 | fail `BAD_ARGUMENT` — bbox는 [minX, minY, maxX, maxY]여야 합니다. | fail `INVALID_KEY` — ITS_API_KEY가 설정되지 않았습니다. |
| `get_car_route` | external | sx, sy, ex, ey | ok — duration_min=14, taxi_fare=10600, bbox 4건, path 120건 | fail `BAD_ARGUMENT` — 입력값이 규약과 다릅니다. | fail `INVALID_KEY` — KAKAO_REST_KEY가 설정되지 않았습니다. |
| `get_weather` | external | lat, lon, at | ok — pop=0, temp=6.0 | fail `BAD_ARGUMENT` — at은 YYYY-MM-DDTHH:MM 형식이어야 합니다. | fail `INVALID_KEY` — DATA_GO_KR_KEY가 설정되지 않았습니다. |
| `get_transit_route` | external | sx, sy, ex, ey | ok — paths 3건 | fail `BAD_ARGUMENT` — 입력값이 규약과 다릅니다. | fail `INVALID_KEY` — ODSAY_API_KEY가 설정되지 않았습니다. |
| `search_terms` | local | question | ok — chunks 4건 | fail `BAD_ARGUMENT` — question은 필수입니다. | fail `INVALID_KEY` — GMS_API_KEY가 설정되지 않아 규정을 검색할 수 없습니다. |
| `find_terminals` | external | x, y | ok — terminals 1건 | fail `BAD_ARGUMENT` — 입력값 형식이 규약과 다릅니다: x | fail `INVALID_KEY` — KAKAO_REST_KEY가 설정되지 않았습니다. |
| `search_express_bus` | external | dep_terminal_id, arr_terminal_id | ok — date_requested=2026-11-21, estimated=False, buses 120건 | fail `BAD_ARGUMENT` — 출발·도착 터미널 ID는 필수입니다. | fail `INVALID_KEY` — DATA_GO_KR_KEY가 설정되지 않았습니다. |
| `search_trains` | external | dep_station_id, arr_station_id | ok — date_requested=2026-11-21, date_queried=2026-11-21, estimated=False, trains 35건 | fail `BAD_ARGUMENT` — date는 YYYY-MM-DD 형식이어야 합니다. | fail `INVALID_KEY` — DATA_GO_KR_KEY가 설정되지 않았습니다. |
| `get_festivals` | external | x, y, date | ok — festivals 0건 | fail `BAD_ARGUMENT` — date는 YYYY-MM-DD 형식이어야 합니다. | fail `INVALID_KEY` — DATA_GO_KR_KEY가 설정되지 않았습니다. |

예외가 밖으로 나온 호출: 0건(모두 ok/fail 형식).

## 2. 기준 날짜 기본값 · 조회할 수 없는 기준

- 날짜 생략: ok — date_requested=2026-11-20, date_queried=2026-11-20, estimated=False, trains 35건 (오늘 2026-11-20)
- 60일 뒤(2027-01-19) 열차: ok — date_requested=2027-01-19, date_queried=2027-01-19, estimated=False, trains 35건
- 5일 뒤 날씨(예보 범위 밖): fail `OUT_OF_RANGE` — 단기예보 범위(오늘~4일 뒤) 밖이라 날씨를 확인할 수 없습니다.
- 시간표가 없는 날짜를 이웃 날짜 시간표로 대신할 때는 `estimated`=True와 '추정 시간표' 그룹으로 표시(통과 불가) — TAGO가 미래 날짜도 그 날 시간표를 줘 실제 대체는 발생하지 않음(`test_estimated_never_passed`).

## 3. 후보 식별자로 상세 조회 · 비어 있는 속성

- 장소(좌표) → `find_stations` → 역 ID `NAT031857`·`NAT010032` → `search_trains`(2026-11-21): ok — date_requested=2026-11-21, date_queried=2026-11-21, estimated=False, trains 35건
- 운임이 빈 열차: 0건 — 빈 값은 `None` 그대로 두고 판단 단계에서 '예산 판단 불가'로 분류(임의 값 없음)

## 4. 보조 정보 검색 결과 있음 / 없음

- 있음: 광주송정역 · 전남광주통합특별시 광산구 상무대로 201 · 링크 있음 · 좌표 (126.7908, 35.1377)
- 없음: fail `NO_DATA` — 'ㅁㄴㅇㄹ없는장소qwerty' 장소를 찾지 못했습니다.

## 10. 충족할 수 없는 조건 → 재계획 상한에서 멈춤

- 상태 `no_option` · 재계획 3회 · LLM 1회
  - 재계획 1: 거점 확장(근처 역 3곳까지) — 조건을 만족하는 후보 0개 (검토 71개)
  - 재계획 2: 수단 확장(택시 구간 포함) — 조건을 만족하는 후보 0개 (검토 85개)
  - 재계획 3: 전날 출발 후보 추가 — 조건을 만족하는 후보 0개 (검토 432개)
- 응답: 조건을 만족하는 이동 방법을 찾지 못했어요(재계획 3/3회: 거점 확장(근처 역 3곳까지), 수단 확장(택시 구간 포함), 전날 출발 후보 추가). 예: KTX 00464 05:18 출발 → 09:57 도착 — 도착 09:57 > 마감 05:50; KTX 00464 05:18 출발 → 09:57 도착 — 도착 09:57 > 마감 05:50. 도착 시각을 늦

## 14. 세션 둘 — 이벤트가 세션별로 저장되고 섞이지 않음, LLM 판단 이벤트

- `live-check-a-120437`: 응답 이벤트 7개 = 저장 7개, 다른 세션 섞임 0개, 종류 llm_decision, node_end, node_start, run_end, run_start
  - LLM 판단 이벤트: decision=`intent` value=`chat` reason="인사 메시지이므로 이동 계획과 무관한 chat으로 분류"
- `live-check-b-120437`: 응답 이벤트 49개 = 저장 49개, 다른 세션 섞임 0개, 종류 llm_decision, node_end, node_start, plan_tasks, run_end, run_start, tool_call, tool_result
  - LLM 판단 이벤트: decision=`intent` value=`plan_trip` reason="출발지와 도착지, 도착 시한이 주어진 이동 계획 요청이다."

## 18. 실행 로그 목록 · 상세 · 삭제, 수정 API 없음

- `GET /api/logs` → 200, 세션 138개 (새 세션 포함: True)
- `GET /api/logs/live-check-b-120437` → 200, 이벤트 49개, 실행 순서(seq 1→49) 오름차순 True
- `PUT /api/logs/live-check-b-120437` → 405 (수정 API 없음)
- OpenAPI의 /api/logs 경로 메서드: DELETE, GET
- `DELETE /api/logs/live-check-a-120437` → 204, 다시 조회 → 404
- `DELETE /api/logs/live-check-b-120437` → 204, 다시 조회 → 404
