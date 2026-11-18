# 이동 플래너 (Route Planner) 설계 문서

- 작성일: 2026-11-18 (AI 코어 프로젝트 3회차 1일차)
- 근거: `AI코어프로젝트_3회차_요구사항정의서.pdf`, 1일차 라이브(FastAPI·프로젝트 소개), 광주 3반 제출 안내
- 제출 프로젝트명(안): `AI코어프로젝트3_이동플래너_광주_03_김진영` (lab.ssafy.com `AICorePJT03` 하위)

---

## 1. 의도와 이유

사용자가 "어디서 → 어디로, 언제까지(또는 언제부터), 어떤 조건으로" 가는지 말하면, Agent가 **외부 API로 확인한 시간표·소요시간·요금만으로** 문 앞에서 문 앞까지(도보·지하철·버스·열차·택시) 이동 옵션을 계산해 근거와 함께 제안하고, 사용자가 고른 옵션을 이동 계획으로 저장·관리하게 한다.

- 이 과제의 첫 번째 평가 기준은 "얼마나 많이 해 주는가보다 **확인하지 않은 값을 지어내지 않는가**"이다. 이 서비스는 좌석 잔여·실시간 지연·혼잡도처럼 공개 API로 확인할 수 없는 값을 **절대 계산에 넣지 않고 '확인 불가'로 명시**하는 것을 정체성으로 삼는다.
- 길찾기 앱과의 차이: 길찾기는 "출발 시각을 주면 경로"를 준다. 이 서비스는 **도착 마감·예산·캘린더 일정**이라는 제약을 계산해 **수단·편·출발 시각을 골라 주고**, 맞는 게 없으면 재계획하며, 결과를 저장하고 캘린더에 등록한다.
- 목표 범위: 요구사항 **F3001~F3023 전부(심화 4종 포함) + NF3001~NF3007**. 사용자가 명시적으로 "심화도 필수"로 정했다.

## 2. 목표 · 비목표 · 반목표

**목표**
- 요구사항 표의 모든 항목을 실행 결과(화면 캡처·실행 로그)로 증명할 수 있다.
- 대표 시나리오 5개 이상(충족 / 재계획 / 상한 도달 / Tool 실패 / Tool 불필요)이 재현 가능하다.
- 매일 commit, 3일차 17:30 전 제출.

**비목표**
- 실제 예매·결제. (공개 예매 API가 없고, 비공식 크롤링은 약관 위반)
- 시내 경로의 정밀 안내(몇 번 출구, 실시간 지하철 위치) — 길찾기 앱 영역.
- 실시간 교통 예측, 지연 예측.
- 집회·시위 정보(신뢰할 공개 API 없음, 크롤링은 NF3007 위반 소지).
- 항공(1차 범위에서 보류. 시간이 남아도 추가하지 않음 — 2일차 17시 이후 신규 기능 금지).

**반목표 (기술적으로 돌아가도 실패로 보는 것)**
- LLM이 시각·요금·소요시간 숫자를 만들어 내거나 바꾸는 것. 숫자는 Tool 결과와 코드 계산에서만 나온다.
- 날씨·행사·도로통제로 "약 N분 지연"처럼 추정해 시간 계산에 더하는 것. 이들은 **경고**로만 쓴다.
- 비어 있는 값을 `""`/`0`으로 채우는 것. `None`으로 두고 "판단하지 않음"으로 표시한다.
- 로깅 Agent가 꺼지거나 저장에 실패했을 때 대화가 실패하는 것.
- API 키나 오류 원문이 화면·로그·커밋에 노출되는 것.

## 3. 제약

- 일정: 라이브 매일 09:00~11:00 / 기획 1일차 ~16:00(도메인 확정) / 구현 1일차 16:00~3일차 12:00 / **2일차 17:00 이후 신규 기능 시작 금지** / 검증 3일차 13:30~17:30.
- 1일차 16:00까지 외부 API 3종 이상 실제 호출 확인 못 하면 제공 도메인(영화)으로 전환해야 한다.
- 필수 라이브러리 버전 고정(명세서 1.2-5): langgraph 1.2.10, langchain 1.3.14, langchain-openai 1.4.3, langchain-core 1.6.0, langchain-text-splitters 1.1.2, openai 2.54.0, python-dotenv 1.2.3, requests 2.34.2, langsmith 0.10.17, typing-extensions 4.16.0, fastapi 0.141.1, uvicorn[standard] 0.52.4, pydantic 2.13.5, google-api-python-client 2.201.0, google-auth-oauthlib 1.5.0, google-auth-httplib2 0.4.3, chromadb 1.5.9.
- Python 3.10+, FastAPI + SQLite, 프론트는 HTML/CSS/JS(Vue 선택).
- LLM은 SSAFY GMS 키(OpenAI 호환 엔드포인트로 `langchain-openai` 사용). 사용할 모델명·엔드포인트·임베딩 지원 여부는 1일차에 실제 호출로 확인.
- 외부 API 키 4곳: 공공데이터포털(TAGO·기상청·TourAPI), ODsay LAB, Kakao Developers(로컬·모빌리티), 국가교통정보센터(ITS). Google Calendar는 Google Cloud OAuth 클라이언트(데스크톱 앱).
- 개인 프로젝트(AI 페어 프로그래밍). 라이브 영화 예시 코드를 매일 이 도메인으로 옮겨 적용한다.

## 4. 접근 방식 (검토한 대안과 선택)

| 대안 | 장점 | 단점 | 결과 |
|---|---|---|---|
| 공연 관람 플래너(KOPIS) | 영화 예시와 1:1, 가장 안전 | 차별성 낮음, 공연시간 텍스트 파싱 | 기각 |
| 야외 운동 플래너 | 제약이 전부 수치, 캘린더 적합 | 예보 기간 짧음, 건강 면책 | 기각 |
| 법률 기한 플래너 | 2회차 연속성 | API 승인·XML·규칙 정의 리스크 | 기각 |
| **문 앞~문 앞 이동 플래너** | 제약·재계획이 자연스럽고 RAG(약관)·캘린더(앞 일정)가 억지 없이 맞음, 시연 공감도 높음 | Tool 연결(좌표→역 ID)이 복잡, 호출 수 많음 | **선택** |

API 구성은 단계적으로 늘린다(사용자 결정):

| 단계 | API | 시점 |
|---|---|---|
| 핵심 | 카카오 로컬, TAGO 열차정보, ODsay 대중교통 길찾기 | 1일차 반드시 호출 확인 |
| 확장 1 | 기상청 단기예보, 카카오 모빌리티 길찾기 | 1일차 가능하면 |
| 확장 2 | ITS 돌발정보, TAGO 고속버스정보 | 2일차 17:00 전 착수 |
| 선택 | TourAPI 행사정보 | 시간 남으면, 2일차 17:00 전 착수한 경우만 |
| 보류 | 항공, 집회·시위 | 하지 않음 |

**전환 기준(사용자 결정):** 1일차 14:00까지 "TAGO 열차가 미래 날짜 시간표·운임을 주는지"와 "카카오 좌표 → TAGO 역 ID 연결"이 확인되지 않으면 공연 플래너로 전환한다.

## 5. 서비스 동작

### 5.1 요청 유형(의도)
| 의도 | 예 | Tool |
|---|---|---|
| `plan_trip` 이동 계획 수립 | "토요일 10시까지 첨단동에서 강남역, 6만원 이하" | 있음 |
| `modify` 조건 변경 후속 | "같은 조건에서 저녁 6시 이후 출발로" | 있음(바뀐 조건만 갱신) |
| `fact_query` 사실 조회 | "광주송정→용산 내일 첫 KTX 몇 시?" | 열차 Tool만 |
| `terms_query` 규정 질문 | "KTX 출발 30분 전 취소 위약금?" | RAG Tool |
| `save_plan` 계획 확정 | "②번으로 저장해줘" / 카드 버튼 | 없음(서버 직접) |
| `register_calendar` | "그거 캘린더에 넣어줘" | 캘린더 등록 Tool |
| `chat` 인사·사용법 | "안녕", "어떻게 써?" | 없음(계획 단계 건너뜀) |

### 5.2 조건 추출 (F3005)
- 기준: `origin`, `destination`, `date`, `arrive_by` 또는 `depart_after`
- 선호: `priority`(cheapest | fastest | fewest_transfers, 기본 cheapest), `modes`(허용 수단), `avoid`(예: 운전 안 함, 비 맞기 싫음)
- 제약: `budget`(원), `buffer_min`(도착 여유, 기본 10분), 캘린더 일정
- **추출하지 못한 값은 None으로 둔다.** `date`와 (`arrive_by` 또는 `depart_after`), `origin`, `destination` 중 하나라도 없으면 Tool 호출 전에 되묻는다. (예: "2시까지 서울 가야 해" → 날짜·출발지 질문)
- 상대 날짜("모레", "토요일")는 서버 기준 오늘(Asia/Seoul)로 코드에서 변환한다. LLM에는 오늘 날짜를 프롬프트로 준다.

### 5.3 판단 계산식 (F3008) — 전부 코드, LLM 사용 안 함
한 옵션 = [출발 구간] + [간선 열차(또는 고속버스)] + [도착 구간]

```
access_min, access_fare   = 출발지 → 출발역  (ODsay 대중교통, 또는 카카오 모빌리티 택시)
egress_min, egress_fare   = 도착역 → 목적지  (동일)
BOARD_BUFFER = 10분        # 역 도착 후 승차 여유 (설계 상수, 문서·화면에 명시)

leave_at   = train.dep_time − BOARD_BUFFER − access_min
arrive_at  = train.arr_time + egress_min
total_fare = access_fare + train.fare + egress_fare   # 하나라도 None이면 total_fare=None

통과 조건
  arrive_by  있으면: arrive_at ≤ arrive_by − buffer_min
  depart_after 있으면: leave_at ≥ depart_after
  budget 있으면: total_fare ≤ budget   (total_fare=None → "예산 판단 불가", 통과도 제외도 아님)
  캘린더: [leave_at, arrive_at]이 그날 busy 구간과 겹치면 제외(사유에 일정 제목·시각)
```
- `arrive_by`만 있고 `depart_after`가 없으면, 출발 시각 하한은 "현재 시각(같은 날일 때)"과 "캘린더상 직전 일정 종료" 중 늦은 값.
- 실시간 지연·좌석·혼잡은 확인 불가 → 응답에 고정 문구로 명시.
- 정렬: `priority` 기준 1순위 + 나머지 기준별 대표 1개씩(최저가 / 최단 소요 / 환승 최소)을 최대 3개 카드로 제시. 중복 제거.
- 경고(계산에 미반영):
  - 날씨: 해당 시각 강수확률 ≥ 60% 이고 도보 합계 ≥ 10분 → "우천 시 도보 구간 주의" + 같은 옵션의 택시 변형을 함께 제시. 예보 범위 밖이면 "예보 없음".
  - 도로 돌발: 택시·자동차·버스 구간 경로 bbox 안에 통제·공사 이벤트 → 경고. 실시간 정보이므로 출발일이 오늘이 아니면 "기간이 명시된 이벤트"만 사용.
  - 행사(선택): 목적지 반경 내 같은 날 행사 → "혼잡 가능" 안내만.
  - 사용자가 `avoid`에 "비"를 명시한 경우에만 날씨가 **제약**이 된다(강수확률 ≥ 60% 시간대에 도보 ≥ 10분인 옵션 제외).

### 5.4 재계획 (F3009, NF3004)
- **조건:** 통과 옵션이 0개일 때만. `MAX_REPLAN = 3`(설정값).
- **전략(순서대로 하나씩):**
  1. 거점 확장: 출발·도착 측 다음으로 가까운 역 추가(예: 광주송정 → 광주역/나주역).
  2. 수단 확장: 출발·도착 구간에 택시 변형 추가, 고속버스 간선 추가(확장 2 구현 시).
  3. 시간 완화 제안: 도착 마감 전날 출발 후보 조회(`arrive_by`가 아침이고 사용자가 금지하지 않은 경우).
- **재사용:** Tool 결과를 `(tool_name, 정규화된 args)` 키로 실행 단위 캐시에 저장, 재계획 시 같은 호출은 캐시에서 가져온다(이벤트에 `cached=true`).
- **재계획하지 않는 경우:** `INVALID_KEY`, `BAD_ARGUMENT`, 필수 조건 누락, `AMBIGUOUS_PLACE` → 즉시 안내·되묻기.
- **상한 도달:** 멈추고 사유(무엇을 시도했는지)와 함께 조정 가능한 조건(예산 +N원, 마감 완화, 전날 출발)을 되묻는다.

### 5.5 대화 맥락 (F3010)
- 보관: 세션별 현재 조건 dict, 직전 제안 옵션 요약(카드 번호 ↔ 옵션 핵심 값), 저장한 plan_id 목록, 최근 대화 N턴.
- 보관 안 함: Tool 원본 응답(요약만), API 키, 오류 원문.
- 후속 요청은 LLM이 "바뀐 필드만" 구조화 출력 → 기존 조건에 병합. 병합 결과를 이벤트로 남긴다.
- 구현: LangGraph checkpointer(`thread_id = session_id`). 서버 재시작 시 대화 맥락은 사라져도 됨(계획·로그는 SQLite에 영구 저장).

### 5.6 최종 응답 (F3011)
- 카드(구조화 데이터, 화면이 렌더): 옵션별 구간 목록, 출발해야 할 시각, 도착 시각, 총요금, 통과 근거(계산식 값), 경고, 근거 Tool 이름.
- 제외 목록: 옵션·사유("도착 10:12 > 마감 09:50", "운임 정보 없음 — 예산 판단 불가", "캘린더 '팀 회의' 13:00–14:00과 겹침").
- 추정 표시: 예보 범위 밖, 실시간 정보 사용 불가 등.
- 자연어 요약은 LLM이 작성하되 **숫자는 카드 데이터에서 그대로 인용**하도록 프롬프트로 제한하고, 응답에 등장한 시각·금액이 카드 값 집합에 없으면 요약 대신 템플릿 문장으로 대체(코드 검사).
- 위험 도메인 아님 → 면책 문구 없음. 대신 고정 안내: "좌석·실시간 지연은 확인하지 못했어요. 예매처에서 확인하세요."

## 6. Tool 설계 (F3001~F3004, F3022, F3023)

### 6.1 공통 규약
- 반환: `{"ok": true, "data": ...}` / `{"ok": false, "error": {"code", "message"}}`. 예외는 밖으로 던지지 않는다(`tools_start.py` 규약 계승).
- 원본 응답을 통째로 넘기지 않고 판단에 쓸 값만 뽑는다. 빈 값은 `None`.
- 실패 코드: `BAD_ARGUMENT`, `INVALID_KEY`, `NOT_FOUND`, `NO_DATA`, `UPSTREAM_ERROR`, `AMBIGUOUS_PLACE`(장소 후보 여러 개), `OUT_OF_RANGE`(예보·시간표 범위 밖), `NO_INDEX`(RAG 색인 없음), `RATE_LIMITED`.
- 레지스트리: 이름 → Tool(이름, 설명="언제 쓰는지", JSON Schema, 함수, 종류=external|local). Agent에는 이름·설명·스키마만 전달.
- 오류 메시지에 키가 든 URL이 섞이지 않게 `requests` 예외는 일반 문구로 바꾼다.
- 모든 외부 호출 timeout 10초.

### 6.2 Tool 목록

| Tool | 종류 | API | 요구사항 | 입력 | 출력(핵심) |
|---|---|---|---|---|---|
| `search_places` | 외부 | 카카오 로컬 키워드/카테고리 검색 | F3004 | `query`, `near?` | `[{name, address, x, y, place_url}]`, 동명 다수면 `AMBIGUOUS_PLACE` + 후보 |
| `find_stations` | 외부 | 카카오 로컬(좌표 주변 기차역) + TAGO 역 목록 매칭 | F3002 보조 | `x, y, radius_km` | `[{tago_station_id, name, x, y, distance_km}]` |
| `search_trains` | 외부 | TAGO 열차정보 | **F3002 필수** | `dep_station_id, arr_station_id, date(기본=오늘)` | `[{train_no, grade, dep_time, arr_time, fare}]`, 요청 날짜≠조회 날짜면 `estimated=true`+사유 |
| `get_transit_route` | 외부 | ODsay 대중교통 길찾기 | **F3003 필수** | `sx, sy, ex, ey` | `{total_min, fare, transfers, walk_min, legs:[{mode, name, min}]}` |
| `get_car_route` | 외부 | 카카오 모빌리티 길찾기 | F3003 보충 | `sx, sy, ex, ey` | `{duration_min, distance_km, taxi_fare, toll, bbox}` |
| `get_weather` | 외부 | 기상청 단기예보 | F3004 | `lat, lon, datetime` | `{pop, pty, temp}`, 범위 밖 `OUT_OF_RANGE` |
| `get_road_events` | 외부 | ITS 돌발정보 | F3004 | `bbox` | `[{type, description, start, end, x, y}]` |
| `search_express_bus` | 외부 | TAGO 고속버스 | F3002 보충 | `dep_terminal_id, arr_terminal_id, date` | `[{dep_time, arr_time, grade, fare}]` |
| `search_events` (선택) | 외부 | TourAPI 행사정보 | F3004 | `x, y, date` | `[{title, start, end, address}]` |
| `search_terms` | 로컬 | Chroma | F3022 | `question` | `[{text, source, title, page?}]`, 색인 없음 `NO_INDEX` |
| `get_free_busy` | 로컬 | 캘린더 백엔드 | F3023 | `date` | `[{title, start, end}]` |
| `register_calendar` | 로컬 | 캘린더 백엔드 | F3023 | `plan_id` **만** | `{event_id}` (제목·시각은 저장소에서 읽음) |

- **"세 개의 필수 Tool"(명세 1.3-9)** = `search_trains`(후보) / `get_transit_route`(상세: 후보 열차를 타고 내리기 위한 구간의 시간·요금) / `search_places`(보조: 위치·주소·링크).
- **출력→입력 연결:** `search_places`(좌표) → `find_stations`(역 ID) → `search_trains`(역 ID·날짜) → `get_transit_route`/`get_car_route`(장소 좌표 ↔ 역 좌표) → `get_weather`/`get_road_events`(좌표·시각·bbox).
- **역 ID 매칭(1일차 최대 리스크):** TAGO 역 목록(도시코드별)을 첫 호출 시 받아 `data/cache/stations.json`에 캐시하고, 카카오 로컬에서 찾은 "OO역"의 이름 정규화(공백·"역" 제거)로 매칭한다. 매칭 실패 역은 후보에서 빼고 이벤트에 남긴다.
- **Tool로 두지 않는 것:** 계획 저장·수정·삭제, 조건 병합, 판단 계산, 정렬, 겹침 판정 — 모델 판단이 필요 없으므로 실행 흐름·서버가 직접 수행.

## 7. Agent 실행 흐름 (LangGraph)

### 7.1 단일 Agent 모드 (`AGENT_MODE=single`, 필수 구현)
```
START → analyze ─┬─(chat)────────────────────────────► respond → END
                 ├─(조건 누락/AMBIGUOUS)─► clarify ──► END
                 ├─(save_plan/register)─► action ────► respond → END
                 └─(plan_trip/modify/fact/terms)
                        ▼
                      plan → execute → judge ─┬─(통과≥1 or 비재계획 실패)─► respond → END
                        ▲                     │
                        └──── replan ◄────────┴─(통과 0 & replan<MAX)
                                              └─(통과 0 & replan=MAX)─► respond(상한 안내)
```
- `analyze`(LLM, 구조화 출력): intent, intent_reason, 조건(5.2), 변경 필드.
- `plan`(LLM): Tool 카탈로그를 보고 작업 목록 `[{id, tool, args, depends_on}]` 생성 → 코드로 레지스트리·스키마 검증, 불필요 Tool 제외. 재계획 시에는 직전 시도와 실패 사유를 입력으로 받고 5.4 전략 중 하나를 택한다.
- `execute`(코드): 의존 순서대로 호출, 결과는 Tool 이름 키로 보관, 실패는 사유 기록 후 계속(F3007). 캐시 재사용.
- `judge`(코드): 5.3 계산·정렬·경고.
- `respond`(LLM + 코드 검사): 5.6.

### 7.2 상태(State) 필드
`session_id, run_id, user_message, intent, intent_reason, conditions, missing, tasks, tool_results, cache, options, excluded, warnings, replan_count, replan_history, final_reply, cards, status`

### 7.3 Planner·Worker 모드 (`AGENT_MODE=planner_worker`, F3021)
- **Planner**(LLM): 작업 목록 생성. 사용자 조건으로 채운 인자(날짜, 출발·도착 장소, 마감, 예산)는 `fixed_args`로 표시.
- **Worker**: 평소 LLM 없이 작업 목록대로 Tool 호출. `NO_DATA`·`NOT_FOUND`·`BAD_ARGUMENT`처럼 **인자를 고치면 달라질 수 있는 실패**일 때만 LLM에게 `retry(new_args) | skip | request_replan` 판단을 받는다(`WORKER_LLM=on`일 때). 재시도는 같은 Tool로만, `WORKER_MAX_RETRY=2`, `fixed_args`는 변경 불가(코드로 검사, 위반 시 판단 무효화).
- LLM에 넘기지 않는 실패: `INVALID_KEY`, `RATE_LIMITED`, 필수 인자 누락, `AMBIGUOUS_PLACE` → 즉시 사용자 안내/되묻기.
- Worker가 해결 못 한 실패 → 사유와 함께 Planner로 전달 → 재계획 입력.
- **검증:** Worker 완료 후 로깅 Agent의 규칙 판정(F3020)을 동기 호출 → `warn`이면 Planner가 작업 목록을 다시 구성(재계획 횟수에 포함).
- LLM 호출 조건 요약:

| Agent | 호출함 | 호출 안 함 |
|---|---|---|
| Planner | 의도·조건 추출, 작업 목록 생성/재구성, 최종 응답 문장 | 계산·정렬·저장 |
| Worker | 고칠 여지가 있는 실패의 재시도/건너뜀/계획 변경 판단 | 정상 경로(0회), 치명적 실패, 필수 인자 누락 |
| 로깅 | 이상(warn) 판정된 실행의 원인 진단(3문장 이내) | 이벤트 수집·저장, 규칙 판정, 정상 실행 |

- **비교 실험:** `scripts/compare_modes.py`가 대표 요청 5개를 (single) / (planner_worker, WORKER_LLM=off) / (planner_worker, WORKER_LLM=on) 세 조건으로 실행해 재계획 횟수, 요청당 LLM 호출 수, 응답 시간을 `docs/비교결과.md` 표로 출력.

## 8. 이벤트와 로깅 (F3012~F3014, F3020)

### 8.1 이벤트 버스
- 프로세스 내 pub/sub. `publish(event)`는 구독자 목록을 순회하며 각 구독자를 try/except로 감싼다 → 구독자 실패·부재가 메인 흐름에 영향 없음.
- 발행 측은 구독자를 모른다. `LOGGING_ENABLED=false`면 로깅 Agent를 구독시키지 않는다(4.3 "로깅 Agent 없이 정상 동작" 검증용).

### 8.2 이벤트 스키마
`{session_id, run_id, seq, ts, agent(main|planner|worker|logger), type, node?, payload, duration_ms?}`

| type | payload |
|---|---|
| `run_start` / `run_end` | 사용자 메시지 / 상태, replan_count, llm_calls, 총 소요 |
| `node_start` / `node_end` | 노드 이름 / (analyze 종료 시) intent + intent_reason + 조건 |
| `llm_decision` | 판단 종류(intent, plan, worker_retry 등), 결정, 이유 |
| `plan_tasks` | 작업 목록(도구·인자·fixed_args) |
| `tool_call` / `tool_result` | 도구, 인자(키 제외) / ok, 오류 코드, 요약, cached, duration_ms |
| `replan` | 회차, 사유, 선택한 전략 |
| `worker_decision` | 실패 코드, 결정, 변경 인자 |
| `verify` | 로깅 판정 결과 요약 |

### 8.3 로깅 Agent
- 이벤트를 받는 즉시 SQLite `run_events`에 발생 순서대로 append. LLM 사용 안 함. 저장 실패 시 경고 로그만, 대화는 계속.
- 실행 로그 API: 세션 목록 / 세션 상세(seq 순) / 세션 삭제. **수정 API 없음.**

### 8.4 이상 징후 판정 (F3020)
- 규칙(LLM 없음):
  - `DUPLICATE_CALL`: 같은 run에서 같은 Tool·같은 정규화 인자 호출이 2회 이상(캐시 적중은 제외).
  - `EXCESSIVE_REPLAN`: replan_count ≥ 2(경고) / = MAX(상한).
  - `UNPLANNED_CALL`: `plan_tasks`에 없는 Tool 호출(Worker 재시도로 표시된 호출은 제외).
- 근거 이벤트(`plan_tasks` 또는 `tool_call`)가 없으면 `undetermined`(판정 불가), 이상 없으면 `ok`, 하나라도 있으면 `warn`.
- `warn`일 때만 LLM이 해당 run 이벤트를 읽고 원인(어느 Agent 쪽, 무엇을 고칠지) 3문장 이내 진단 → `anomaly_reports.diagnosis`에 판정과 분리 저장. 진단 실패해도 판정·로그 유지.
- 메인 Agent(Planner)는 `get_verdict(run_id)` 함수로 참조.
- 검증용으로 이상 실행을 일부러 만드는 디버그 옵션(`DEBUG_FORCE=duplicate|unplanned|replan`)을 둔다(설정값, 기본 off).

## 9. 데이터 저장 (SQLite `data/app.db`)

| 테이블 | 주요 컬럼 |
|---|---|
| `plans` | id, title, date, leave_at, arrive_at, origin_name, destination_name, legs_json, total_fare(NULL 허용), source_run_id, calendar_event_id, created_at, updated_at |
| `runs` | run_id, session_id, user_message, mode, status, replan_count, llm_calls, started_at, ended_at |
| `run_events` | id, session_id, run_id, seq, ts, agent, type, node, payload_json, duration_ms |
| `anomaly_reports` | run_id, verdict(ok/warn/undetermined), findings_json, diagnosis(NULL), created_at |
| `local_calendar` | id, title, start, end, plan_id(NULL) |

- 겹침 판정(F3015): 같은 `date`에서 `[leave_at, arrive_at)` 구간이 겹치는 계획 목록을 저장 응답의 `overlaps`로 반환. 저장은 막지 않는다.
- 계획 수정 가능 필드: title, date, leave_at, arrive_at, origin_name, destination_name. 수정 시 겹침 재검사.

## 10. 백엔드 API (FastAPI, Pydantic 요청·응답 모델)

| 메서드·경로 | 용도 |
|---|---|
| `POST /api/chat` | `{session_id?, message}` → `{session_id, run_id, reply, cards, excluded, warnings, clarification?, replan_count, events}` |
| `POST /api/sessions` | 새 대화(세션 발급) |
| `GET /api/plans` · `POST /api/plans` | 목록 / 저장(`{option_ref}` 또는 직접 값) → `{plan, overlaps}` |
| `GET·PUT·DELETE /api/plans/{id}` | 상세 / 수정(→ overlaps) / 삭제(204) |
| `POST /api/plans/{id}/calendar` | 캘린더 등록(F3023) |
| `GET /api/logs` | 세션별 로그 목록(요청 수, 마지막 시각, 이상 판정 요약) |
| `GET /api/logs/{session_id}` | 이벤트 seq 순 상세 |
| `DELETE /api/logs/{session_id}` | 로그 삭제 (PUT/PATCH 없음) |
| `GET /api/runs/{run_id}/anomaly` | 이상 판정 + 진단 |
| `GET /api/tools` | 등록 Tool 카탈로그(4.1 검증) |
| `GET /api/config/status` | 키별 설정 여부 **boolean만** (화면 키 누락 안내용) |

- 없는 리소스 404, 검증 실패 422, 내부 오류는 일반 메시지(원문은 서버 로그만).
- CORS: `http://127.0.0.1:5500`, `http://localhost:5500`만 허용(Live Server). `*` 금지.
- `/api/chat`은 실행 완료 후 이벤트를 한 번에 반환한다(스트리밍 없음). 화면은 요청 중 "처리 중" 표시.

## 11. 프론트엔드 (HTML/CSS/JS)

```
[이동 플래너]                         [대화] [이동 계획] [실행 로그]
┌─ 대화 ─────────────────────────┐ ┌─ 실행 과정 ─ 재계획 1회 · 8.2s ┐
│ 나: 토요일 10시까지 벡스코…      │ │ ● 의도 분석  plan_trip (이유…) │
│ Agent: 요약 문장                │ │ ● 계획 수립  5개 작업           │
│ ┌① 최저가 41,300원 4h05m ─────┐ │ │   Tool search_trains  성공 0.6s│
│ │ 도보6 → 1호선 → KTX 07:02 … │ │ │   Tool get_transit_route 실패  │
│ │ 07:12 출발 · 09:41 도착 ✓     │ │ │ ── 재계획 1: 거점 확장 ───────│
│ │ ⚠ 강수확률 70% 도보 구간     │ │ │ ● 판단  통과 3 / 제외 4       │
│ │ [이 경로로 저장]             │ │ │ ● 응답                         │
│ └────────────────────────────┘ │ └───────────────────────────────┘
│ 제외: KTX 513 도착 10:12 > 09:50 │
│ [입력]                    [보내기]│
└────────────────────────────────┘
```
- 대화 탭: 입력·처리 중 표시·카드·제외 사유·경고·Tool 실패/키 누락 안내(`/api/config/status` 기반 "OO API 키가 설정되지 않았어요").
- 실행 과정 패널: 이벤트를 seq 순 타임라인으로, agent 배지(Planner/Worker), 재계획 지점 구분선, Tool 인자·결과·소요시간.
- 이동 계획 탭: 목록·상세·수정·삭제·캘린더 등록, 저장 시 겹침 알림. 변경 즉시 목록 갱신.
- 실행 로그 탭: 세션 목록 → 상세 타임라인, 이상 판정 배지(ok/warn/판정 불가)와 진단.
- 오류 원문·키를 화면에 표시하지 않는다.

## 12. RAG (F3022)
- 색인 대상(출처 기록 필수): 한국철도공사 여객운송약관, 고속버스 운송약관, 행정안전부 기상특보 국민행동요령. 원문 파일은 `data/docs/`에 두고 출처 URL·수집일을 `data/docs/SOURCES.md`에 기록.
- `scripts/build_index.py`: 로드 → `langchain-text-splitters`로 분할 → 임베딩 → Chroma(`data/chroma/`, 영구). 2회차 파이프라인이 있으면 이식, 없으면 같은 구조로 작성.
- 임베딩: GMS가 임베딩을 지원하면 GMS, 아니면 Chroma 기본 임베딩. 1일차에 확인.
- `search_terms`: 상위 k개 청크 + 출처. 색인 디렉터리 없거나 비어 있으면 `NO_INDEX` → "아직 규정 문서를 색인하지 않았어요".

## 13. 캘린더 (F3023)
- 인터페이스 `CalendarBackend`: `get_free_busy(date) -> list[Busy]`, `create_event(plan) -> event_id`.
- `LocalCalendar`(SQLite `local_calendar`) 먼저 → `GoogleCalendar`(OAuth 데스크톱 앱, `credentials.json`/`token.json`은 gitignore)로 교체. `CALENDAR_BACKEND=local|google`.
- `register_calendar(plan_id)`: 제목·시각은 `plans`에서 읽는다. 모델이 시각을 넘길 수 없게 입력 스키마에 plan_id만 둔다.
- 조회한 busy 구간은 5.3 판단에 반영.

## 14. 설정 (`.env`, 커밋 금지 / `.env.example` 커밋)
`GMS_API_KEY, GMS_BASE_URL, LLM_MODEL, EMBEDDING_MODEL, KAKAO_REST_KEY, ODSAY_API_KEY, DATA_GO_KR_KEY, ITS_API_KEY, AGENT_MODE, WORKER_LLM, MAX_REPLAN, WORKER_MAX_RETRY, LOGGING_ENABLED, CALENDAR_BACKEND, GOOGLE_CALENDAR_ID, DEBUG_FORCE`

## 15. 디렉터리 구조 (NF3006)
```
route-planner/
  backend/
    main.py                 # FastAPI 앱, CORS, 라우터 등록
    api/  chat.py plans.py logs.py config.py
    agent/ graph.py state.py nodes/{analyze,plan,execute,judge,respond}.py
           planner_worker.py judge_rules.py prompts.py memory.py
    tools/ base.py registry.py kakao_local.py tago_train.py tago_bus.py odsay.py
           kakao_mobility.py kma_weather.py its_events.py tour_events.py
           rag.py calendar.py
    events/ bus.py logger_agent.py anomaly.py
    db/    database.py repositories.py
    schemas.py settings.py
  frontend/ index.html  css/  js/{api,chat,plans,logs,timeline}.js
  scripts/ build_index.py compare_modes.py check_apis.py
  data/   (docs/, chroma/, cache/, app.db — docs/SOURCES.md만 커밋)
  docs/   요구사항정의서.md Agent설계.md Tool정의서.md API명세서.md 검증결과.md
          실행로그샘플.md 비교결과.md 셀프체크리스트.md screenshots/
  tests/
  README.md  requirements.txt  .env.example  .gitignore
```

## 16. 대표 시나리오 (4.7, 최소 5개 + 추가)
| # | 유형 | 요청 |
|---|---|---|
| S1 | 한 번에 충족 | "토요일 오후 2시까지 광주 첨단동에서 서울 강남역, 6만원 이하" |
| S2 | 재계획 | 광주송정 출발로는 마감이 안 맞고 거점 확장/택시 변형으로 통과하는 요청 |
| S3 | 상한 도달 | "오늘 밤 11시 이후 출발해서 내일 새벽 6시까지 부산, 2만원 이하" |
| S4 | Tool 실패 | ODsay 키 제거 상태에서 S1 → 해당 구간 판단 불가, 나머지 진행, 키 누락 안내 |
| S5 | Tool 불필요 | "안녕, 어떻게 써?" |
| S6 | 되묻기 | "2시까지 서울 가야 해" |
| S7 | 후속 변경 | S1 직후 "같은 조건에서 출발은 오전 10시 이후로" |
| S8 | RAG | "KTX 출발 30분 전에 취소하면 위약금 얼마야?" |
| S9 | 캘린더 | 그날 오전 일정이 있는 날짜로 S1 → 겹치는 옵션 제외 |
| S10 | 겹침 저장 | 같은 날 시간이 겹치는 계획 저장 → overlaps 알림 |

각 시나리오마다 최종 응답·실행 로그·기대 vs 실제 차이를 `docs/검증결과.md`에 기록, 대표 1건 전체 로그와 재계획 사례는 `docs/실행로그샘플.md`.

## 17. 일정과 커밋
| 시점 | 할 일 | 산출 |
|---|---|---|
| **1일차** ~16:00 | 키 신청, 핵심 API 3종 실제 호출(`scripts/check_apis.py`), 역 ID 매칭 설계 시험, 도메인 근거 작성 | 요구사항 정의서 v1(도메인 근거·기획 검증) |
| 1일차 ~18:00 | 핵심 Tool 3개 + `find_stations` 단독 실행(정상/빈 입력/키 없음/결과 없음), GMS 호출·Tool 선택 확인, 확장 1 Tool, lab 프로젝트 생성 | **commit: day1** |
| **2일차** 11:00~17:00 | LangGraph 단일 모드, 판단·재계획·메모리, 이벤트·로깅, FastAPI, 화면, 계획 CRUD → 17:00 전 F3020 규칙·F3021 모드 전환 골격·F3022 색인·F3023 로컬·확장 2 Tool **착수** | **commit: day2** |
| **3일차** 11:00~12:00 | 심화 마무리, Google Calendar 교체, 비교 실험 | |
| 3일차 13:30~17:30 | 시나리오 검증, 캡처·GIF, 문서, 셀프 체크리스트, 제출 | **commit: day3** |
- 화면이 붙는 2일차부터 대표 요청 캡처를 바로바로 `docs/screenshots/`에 저장.

## 18. 빌더 검토 후 확정한 결정 (작성자 판단, 사용자 확인 대상)

1. **전제 조건:** 이 문서 전체는 4장 전환 기준(TAGO 미래 날짜 시간표·운임, 좌표→역 ID 매칭)을 1일차 14:00까지 통과한다는 전제다. 실패하면 이 문서는 폐기하고 공연 플래너로 다시 설계한다. 구현 계획의 첫 작업은 이 확인이다.
2. **추정 시간표:** 요청 날짜의 시간표를 받지 못해 다른 날짜로 대신 조회한 열차(`estimated=true`)는 **통과 옵션이 될 수 없다.** "추정(같은 요일 시간표 기준)" 그룹으로 별도 표시만 하고, 재계획 판단의 통과 수에도 넣지 않는다.
3. **같은 도시 안 이동:** 출발지·목적지 직선거리 < 40km 이거나 양쪽 최근접 역이 같으면 간선 없이 **ODsay 대중교통 경로 + 택시 변형**만 옵션으로 만든다. 이때 ODsay 경로 하나 = 옵션 하나이고, 판단식은 `leave_at = depart_after or (arrive_by − buffer − total_min)` 기준으로 동일하게 적용한다. 도시 간 이동에서는 ODsay를 **출발·도착 구간(역↔장소) 계산에만** 쓰고, ODsay의 도시 간 경로 결과는 옵션으로 쓰지 않는다(간선 판단은 TAGO가 담당 — 차별점 유지, 중복 제거 불필요).
4. **작업 목록의 단위:** `plan`(Planner)의 LLM은 **작업 단위**(어떤 Tool을 어떤 순서로, 인자의 출처 표기 예: `"dep_station_id": "$find_stations.origin[0..1]"`)까지만 만든다. 이전 결과에 따라 여러 번 호출로 펼치는 것은 코드(`execute`/Worker)가 한다. 펼친 각 호출은 `tool_call` 이벤트에 `task_id`를 단다. `UNPLANNED_CALL`은 "어떤 task에도 속하지 않는 호출"(또는 task의 Tool과 다른 Tool 호출)로 정의한다 → 정상 실행은 warn이 나지 않는다.
5. **구간 소요시간이 None일 때:** 출발·도착 구간은 ODsay 실패 시 카카오 모빌리티(택시) 시간으로 대체하고 옵션에 "대중교통 정보 없음 → 택시 기준" 표시. 둘 다 없으면 그 옵션은 **"시간 판단 불가"** 그룹으로 보낸다(통과도 제외도 아님). 판단 불가가 원인이 `INVALID_KEY`·`UPSTREAM_ERROR`·`RATE_LIMITED`이면 통과 0개여도 **재계획하지 않고** 안내한다(재사용해도 결과가 같으므로). 원인이 `NO_DATA` 등 인자 의존이면 재계획 대상.
6. **검증(warn) → 재구성 규칙:** Planner·Worker 모드에서 로깅 판정이 `warn`이고 원인이 `DUPLICATE_CALL` 또는 `UNPLANNED_CALL`일 때만 작업 목록을 다시 구성한다. `EXCESSIVE_REPLAN` warn은 재구성 트리거가 아니다(기록·진단만). 검증 기반 재구성은 **실행당 최대 1회**이고 replan_count에 포함된다. 통과 옵션이 이미 있어도 재구성은 하되, 캐시로 같은 호출은 재사용한다. 비교 실험의 "재계획 횟수"는 replan 이벤트 수(사유별로 `no_option`/`verify`/`worker_request` 구분)로 센다.
7. **캘린더 busy 처리:** busy 판정은 이동 창 `[leave_at, arrive_at)`과 겹치는 일정만 본다. 목적지 일정(예: 14:00 회의)은 `arrive_at ≤ arrive_by − buffer`이므로 자연히 겹치지 않아 별도 처리가 없다. 캘린더 일정에서 `arrive_by`를 자동 추출하지는 않는다(사용자가 말한 값만 사용). 이 앱이 등록한 이동 계획도 busy로 본다(이미 잡힌 이동과 겹치는 새 이동은 제외가 맞다). 같은 이동을 다시 짜려면 기존 계획을 삭제·수정한다.

## 19. 외부 API 호출 한도와 분배 (키 발급 후 확인된 제약)

확인된 한도(2026-11-18 발급 화면 기준):

| API | 한도 | 영향 |
|---|---|---|
| ODsay (Basic, 무료) | **하루 30회** | 가장 빡빡함. 설계의 핵심 제약 |
| ITS 돌발정보 (개발용) | **월 100회** | 하루 평균 3회 수준 |
| 공공데이터포털 (TAGO·기상청 개발계정) | 기능별 하루 10,000회 | 여유 |
| 카카오 로컬·모빌리티 | 쿼터 넉넉 | 여유 |

**원칙: 같은 질문은 두 번 묻지 않고, 테스트는 실제 키를 쓰지 않으며, 한도가 차면 미리 막고 대체한다.**

1. **영구 캐시(`api_cache` 테이블):** 키 = `(api, 정규화 인자)`. 좌표는 소수점 3자리(약 100m)로 반올림해서 "근처 같은 곳"을 같은 키로 본다. TTL: ODsay 구간 7일(노선·소요시간은 자주 안 바뀜), 카카오 로컬 30일, TAGO 시간표 1일, 기상청은 발표 시각(base_time) 단위, ITS 30분. 서버 재시작 후에도 유지되므로 같은 시연 요청을 반복해도 추가 호출 0.
2. **일일 쿼터 관리자(`api_quota` 테이블):** `(date, api, used)`를 호출 **직전**에 확인·증가. ODsay: `ODSAY_DAILY_LIMIT=30`, 그중 `ODSAY_RESERVE=6`은 검증·시연용으로 남겨 두고, 평소 실행은 24회에서 멈춘다(`QUOTA_USE_RESERVE=true`일 때만 예약분 사용). ITS: `ITS_MONTHLY_LIMIT=100`, 하루 상한 `ITS_DAILY_SOFT=4`. 한도 도달 시 외부 호출 없이 즉시 `RATE_LIMITED` 반환.
3. **요청당 상한:** 한 실행에서 ODsay는 최대 4회(출발 쪽 역 2곳 + 도착 쪽 역 2곳, "장소↔역" 구간만. 열차 편마다 부르지 않음 — 구간 소요시간은 열차와 무관). 같은 도시 안 이동은 1회. 재계획에서 거점을 넓혀도 실행 합계 4회를 넘기지 않고, 넘치는 구간은 택시 기준으로 계산.
4. **대체 규칙:** ODsay가 `RATE_LIMITED`/실패면 카카오 모빌리티 택시 시간·요금으로 대체하고 카드에 "대중교통 조회 한도 초과 → 택시 기준" 표시(18-5와 동일 경로). `RATE_LIMITED`는 재계획 사유가 아니다.
5. **ITS는 마지막에 한 번만:** 판단·정렬이 끝난 뒤 최종 카드(최대 3개)의 택시·자동차·버스 구간 bbox를 합쳐 실행당 1회만 호출. 그 구간이 없으면 호출하지 않는다.
6. **테스트·개발은 키 0회:** 단위 테스트와 그래프 테스트는 `tests/fixtures/` 응답만 사용(네트워크 차단 fixture). 실제 호출은 Task 1 확인(ODsay 정상 1 + 결과 없음 1 = 2회)과 검증·시연 때만.
7. **가시화:** `GET /api/config/status`에 API별 오늘 사용량/한도(`{"odsay": {"used": 7, "limit": 30}}`)를 포함하고, 화면 상단에 작게 표시. 실행 이벤트 `tool_result`에 `quota_used`를 남겨 로그로도 확인.

**하루 예산 예시(ODsay 30회):** 개발 확인 2 · 통합 점검 요청 4건(최대 16, 캐시로 실제는 더 적음) · 예약 6(시나리오 캡처 S1·S2·S4·S7·S9 — 대부분 캐시 적중). 남는 분은 다음 날로 넘어가지 않으므로, 3일차 시연용 경로(첨단동↔광주송정, 용산↔강남 등)는 2일차에 미리 한 번 호출해 캐시를 채워 둔다.

## 20. 빌더에게 맡기는 것
- 프롬프트 문구, 구조화 출력 스키마의 세부 필드 이름.
- CSS 디자인(기존 설계 규칙 준수: 카드 남발·과한 그라디언트 지양, 접근성·반응형·빈/로딩/오류 상태 포함).
- 각 외부 API의 실제 파라미터 이름·응답 파싱(1일차 실제 호출 결과 기준).
- 테스트 범위(최소: Tool 단독 시험, 판단 계산식 단위 테스트, 겹침 판정, 이상 징후 규칙).
