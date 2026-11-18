"""Tool 단독 실행 데모 2(명세 4.1 증빙): tools_demo.py가 다루지 않는 나머지 6종.

고속버스 터미널·시간표, 도로 돌발, 규정 검색(RAG), 캘린더 조회·등록을 정상/빈 입력/키 없음/결과 없음으로 부른다.
캘린더는 실제 Google 일정이 생기지 않도록 임시 로컬 DB(CALENDAR_BACKEND=local)로 실행한다.
사용: python scripts/tools_demo_extra.py
"""
import datetime as dt
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.settings import get_settings  # noqa: E402

get_settings()  # .env 로드
import backend.tools.catalog_all  # noqa: E402,F401
from backend.db.database import init_db  # noqa: E402
from backend.db.repositories import PlanRepo  # noqa: E402
from backend.schemas import PlanIn  # noqa: E402
from backend.tools.budget import default_budget  # noqa: E402
from backend.tools.registry import get_tool  # noqa: E402

tomorrow = (dt.date.today() + dt.timedelta(days=1)).isoformat()
SONGJEONG = (126.7908, 35.1377)
GANGNAM = (127.0276, 37.4979)


def show(label, r):
    body = r["data"] if r["ok"] else f"{r['error']['code']} — {r['error']['message']}"
    text = str(body)
    print(f"  {str(r['ok']):<5} {label:<6} → {text[:120]}{'…' if len(text) > 120 else ''}")


def run(name, normal, empty, nodata, key_env=None, nodata_env=None):
    tool = get_tool(name)
    print(f"\n== {name} ==")
    show("정상", tool.run(**normal))
    show("빈입력", tool.run(**empty))
    if key_env:
        saved = os.environ.get(key_env, "")
        os.environ[key_env] = ""  # 빈 값으로 둔다(지우면 설정 로더가 .env에서 다시 읽는다)
        show("키없음", tool.run(**normal))
        os.environ[key_env] = saved
    else:
        print("  -     키없음 → 해당 없음(로컬 서버 API 툴, 외부 키 불필요)")
    old = {k: os.environ.get(k) for k in (nodata_env or {})}
    os.environ.update(nodata_env or {})
    show("결과없음", tool.run(**nodata))
    for k, v in old.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


if __name__ == "__main__":
    # 고속버스: 터미널 ID를 find_terminals 결과에서 받아 시간표 Tool로 넘긴다(후보 → 상세)
    t = get_tool("find_terminals").run(x=SONGJEONG[0], y=SONGJEONG[1])
    dep = t["data"]["terminals"][0]["terminal_id"] if t["ok"] else "NAEK610"
    s = get_tool("find_terminals").run(x=GANGNAM[0], y=GANGNAM[1])
    arr = s["data"]["terminals"][0]["terminal_id"] if s["ok"] else "NAEK010"
    run("find_terminals", {"x": SONGJEONG[0], "y": SONGJEONG[1]}, {"x": "abc"}, {"x": 125.0, "y": 33.0},
        key_env="KAKAO_REST_KEY")
    run("search_express_bus", {"dep_terminal_id": dep, "arr_terminal_id": arr, "date": tomorrow},
        {"dep_terminal_id": "", "arr_terminal_id": ""},
        {"dep_terminal_id": dep, "arr_terminal_id": dep, "date": tomorrow}, key_env="DATA_GO_KR_KEY")
    run("get_road_events", {"bbox": [126.79, 35.17, 126.89, 35.27], "date": dt.date.today().isoformat()},
        {"bbox": [], "date": ""}, {"bbox": [124.0, 33.0, 124.05, 33.05], "date": dt.date.today().isoformat()},
        key_env="ITS_API_KEY")
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        run("search_terms", {"question": "KTX 출발 30분 전 반환 위약금"}, {"question": ""},
            {"question": "KTX 반환 위약금"}, key_env="GMS_API_KEY", nodata_env={"CHROMA_DIR": str(Path(tmp) / "none")})
        db = str(Path(tmp) / "demo.db")
        init_db(db)
        os.environ.update({"DB_PATH": db, "CALENDAR_BACKEND": "local"})
        plan = PlanRepo(db).create(PlanIn(title="첨단동 → 강남역(데모)", date=dt.date.fromisoformat(tomorrow),
                                          leave_at="07:45", arrive_at="10:52", origin_name="첨단동",
                                          destination_name="강남역")).plan
        run("register_calendar", {"plan_id": plan.id}, {"plan_id": 0}, {"plan_id": 9999})
        run("get_free_busy", {"date": tomorrow}, {"date": ""}, {"date": "2026-01-01"})
        print("\n  (캘린더는 임시 로컬 DB로 실행 — Google 구현체도 같은 입출력, tests/calendar/test_calendar.py)")
    print("\n오늘 외부 API 사용량:", default_budget().usage())
