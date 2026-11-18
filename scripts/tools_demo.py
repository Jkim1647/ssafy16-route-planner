"""Tool 단독 실행 데모(명세 4.1 증빙): 카탈로그 + Tool별 정상/빈 입력/키 없음/결과 없음.

실제 API를 부르지만 ApiBudget 캐시를 거치므로 두 번째 실행부터는 외부 호출이 거의 없다.
사용: python scripts/tools_demo.py
"""
import datetime as dt
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.settings import get_settings  # noqa: E402

get_settings()  # .env 로드
import backend.tools.catalog_all  # noqa: E402,F401
from backend.tools.budget import default_budget  # noqa: E402
from backend.tools.registry import catalog, get_tool  # noqa: E402

tomorrow = (dt.date.today() + dt.timedelta(days=1)).isoformat()
SONGJEONG = (126.7908, 35.1377)
CHEOMDAN = (126.8432, 35.2280)

CASES = {
    "search_places": ("KAKAO_REST_KEY", {"query": "광주송정역"}, {"query": ""}, {"query": "zzqqxxyy없는장소"}),
    "find_stations": ("KAKAO_REST_KEY",{"x": SONGJEONG[0], "y": SONGJEONG[1]}, {"x": "abc"},
                      {"x": 125.0, "y": 33.0}),
    "search_trains": ("DATA_GO_KR_KEY", {"dep_station_id": "NAT031857", "arr_station_id": "NAT010032", "date": tomorrow},
                      {"dep_station_id": "", "arr_station_id": ""},
                      {"dep_station_id": "NAT031857", "arr_station_id": "NAT031857", "date": tomorrow}),
    "get_transit_route": ("ODSAY_API_KEY", {"sx": SONGJEONG[0], "sy": SONGJEONG[1], "ex": CHEOMDAN[0], "ey": CHEOMDAN[1]},
                          {"sx": SONGJEONG[0]}, {"sx": 125.0, "sy": 33.0, "ex": 125.1, "ey": 33.1}),
    "get_car_route": ("KAKAO_REST_KEY", {"sx": SONGJEONG[0], "sy": SONGJEONG[1], "ex": CHEOMDAN[0], "ey": CHEOMDAN[1]},
                      {"sx": 1}, {"sx": 125.0, "sy": 33.0, "ex": 125.1, "ey": 33.1}),
    "get_weather": ("DATA_GO_KR_KEY", {"lat": SONGJEONG[1], "lon": SONGJEONG[0], "at": f"{tomorrow}T15:00"},
                    {"lat": 35.1, "lon": 126.7, "at": ""}, {"lat": 35.1, "lon": 126.7, "at": "2099-01-01T10:00"}),
}


def show(label, r):
    body = r["data"] if r["ok"] else r["error"]["code"]
    text = str(body)
    print(f"  {str(r['ok']):<5} {label:<6} → {text[:110]}{'…' if len(text) > 110 else ''}")


if __name__ == "__main__":
    print("== 등록된 Tool (Agent에 넘기는 것: 이름·설명·입력 규격) ==")
    for c in catalog():
        print(f"[Tool] {c['name']} — {c['description']}")
        print(f"       입력: {list(c['parameters']['properties'])} 필수: {c['parameters'].get('required')}")
    for name, (key_env, normal, empty, nodata) in CASES.items():
        tool = get_tool(name)
        print(f"\n== {name} ==")
        show("정상", tool.run(**normal))
        show("빈입력", tool.run(**empty))
        saved = os.environ.pop(key_env, "")  # 키 없음: 잠깐 비우고 부른다(키 검사는 캐시보다 먼저)
        show("키없음", tool.run(**normal))
        os.environ[key_env] = saved
        show("결과없음", tool.run(**nodata))
    print("\n오늘 외부 API 사용량:", default_budget().usage())
