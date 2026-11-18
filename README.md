# 이동 플래너 (Route Planner)

> AI 코어 프로젝트 3회차 — Agent 기반 도메인 플래너 서비스 (광주 3반)

출발지·도착지·도착 마감·예산을 말하면, 외부 API로 확인한 시간표·소요시간·요금만으로 도보·지하철·버스·열차·택시를 이어 붙인 이동 옵션을 계산해 근거와 함께 제안하고, 고른 옵션을 이동 계획으로 저장·관리하는 Agent 서비스입니다.

## 진행 상황
- [x] 1일차: 도메인 확정, 외부 API 6종 실호출 확인, Tool 6종 단독 실행 (`docs/day1_tools_demo.txt`)
- [ ] 2일차: LangGraph Agent, 로깅, FastAPI, 화면, 심화 착수
- [ ] 3일차: 심화 마무리, 검증, 산출물

## 실행 방법 (1일차 기준)
```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env   # 키 입력
python scripts/tools_demo.py   # Tool 단독 실행
pytest                         # 테스트 (외부 API 호출 없음)
```

## 문서
- 요구사항 정의서: `docs/요구사항정의서.md`
- 기획 검증: `docs/기획검증.md`
- 설계: `docs/superpowers/specs/2026-11-18-route-planner-design.md`
- 구현 계획: `docs/superpowers/plans/2026-11-18-route-planner.md`

## 사용한 외부 API와 이용 조건
| API | 제공 | 한도 |
|---|---|---|
| 카카오 로컬·모빌리티 | Kakao Developers | 무료 쿼터 |
| TAGO 열차정보 | 국토교통부(공공데이터포털) | 개발계정 하루 10,000회 |
| 기상청 단기예보 | 기상청(공공데이터포털) | 개발계정 하루 10,000회 |
| ODsay 대중교통 길찾기 | ODsay LAB (Basic) | 하루 30회 |
| ITS 돌발정보 | 국가교통정보센터 | 월 100회 |
