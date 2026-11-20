# 화면 → 백엔드 API 호출 기록 (체크리스트 21번)

2026-11-20 10:50, Chrome 개발자 네트워크 기록(`127.0.0.1:8000/api/`만). 화면(`127.0.0.1:5500`)은 정적 파일이고 데이터는 모두 백엔드 API에서 받는다.

| # | 화면 | 메서드 | 경로 | 상태 |
|---|---|---|---|---|
| 1–2 | 공통(로그인 확인) | OPTIONS · GET | `/api/auth/me` | 200 |
| 3–4 | 이동 계획 `#/plans` | GET | `/api/plans` | 200 |
| 5 | 공통(키·한도 상태 배너) | GET | `/api/config/status` | 200 |
| 6–7 | 공통(내 장소) | GET · OPTIONS | `/api/places` | 200 |
| 8 | 실행 로그 `#/logs` | GET | `/api/logs` | 200 |
| 9–10 | 대화 `#/`(일정 제안) | OPTIONS · GET | `/api/suggestions/calendar` | 200 |
| 11 | 대화 `#/`(질문 보내기) | POST | `/api/chat` | 200 |
| 12 | 대화(응답 뒤 한도 갱신) | GET | `/api/config/status` | 200 |

처리 중 표시: `docs/screenshots/processing.jpg`("경로를 계산하는 중이에요 · 0초", 조건 추출 → 시간표 조회 → … 단계 안내).
