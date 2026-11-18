"""외부 API 실호출 확인(Task 1, 기획 검증). 응답을 키 제거 후 tests/fixtures/에 저장한다.

ODsay(하루 30회)·ITS(월 100회) 한도를 아끼기 위해 각각 최소 횟수만 부른다.
사용: python scripts/check_apis.py [--only 이름 ...]
"""
import argparse
import datetime as dt
import json
import os
import pathlib
import sys

import requests
from dotenv import load_dotenv

ROOT = pathlib.Path(__file__).resolve().parents[1]
FIX = ROOT / "tests" / "fixtures"
load_dotenv(ROOT / ".env")

SECRETS = [os.getenv(k, "") for k in
           ("KAKAO_REST_KEY", "ODSAY_API_KEY", "DATA_GO_KR_KEY", "ITS_API_KEY", "GMS_API_KEY")]


def scrub(text: str) -> str:
    for s in SECRETS:
        if s:
            text = text.replace(s, "***").replace(requests.utils.quote(s, safe=""), "***")
    return text


def save(name: str, body) -> None:
    FIX.mkdir(parents=True, exist_ok=True)
    raw = body if isinstance(body, str) else json.dumps(body, ensure_ascii=False, indent=1)
    (FIX / f"{name}.json").write_text(scrub(raw), encoding="utf-8")


def call(name, url, params=None, headers=None):
    try:
        r = requests.get(url, params=params, headers=headers, timeout=10)
    except requests.RequestException as e:
        print(f"[{name}] FAIL {type(e).__name__}")
        return None
    try:
        body = r.json()
    except ValueError:
        body = r.text
    save(name, body)
    print(f"[{name}] HTTP {r.status_code}")
    return body


KAKAO = {"Authorization": f"KakaoAK {os.getenv('KAKAO_REST_KEY', '')}"}
DG = os.getenv("DATA_GO_KR_KEY", "")
TRAIN = "https://apis.data.go.kr/1613000/TrainInfo"
BUS = "https://apis.data.go.kr/1613000/ExpBusInfoService"


def items(body):
    try:
        it = body["response"]["body"]["items"]
        if not it:
            return []
        it = it["item"]
        return it if isinstance(it, list) else [it]
    except (KeyError, TypeError):
        return []


def kakao():
    for name, q in [("kakao_local", "벡스코"), ("kakao_local_songjeong", "광주송정역"), ("kakao_local_ambiguous", "중앙역")]:
        b = call(name, "https://dapi.kakao.com/v2/local/search/keyword.json", {"query": q}, KAKAO)
        if isinstance(b, dict):
            for d in b.get("documents", [])[:3]:
                print("   ", d.get("place_name"), d.get("address_name"), d.get("x"), d.get("y"))
    # 광주송정역 주변 기차역(반경 20km)
    b = call("kakao_stations_near", "https://dapi.kakao.com/v2/local/search/keyword.json",
             {"query": "기차역", "x": "126.7930", "y": "35.1379", "radius": 20000, "sort": "distance"}, KAKAO)
    if isinstance(b, dict):
        print("   ", [d.get("place_name") for d in b.get("documents", [])[:8]])


def tago_train():
    cities = items(call("tago_city", f"{TRAIN}/GetCtyCodeList", {"serviceKey": DG, "_type": "json"}))
    print("   cities:", [(c["citycode"], c["cityname"]) for c in cities])
    wanted = {"광주": None, "서울": None, "부산": None}
    for c in cities:
        for k in wanted:
            if c["cityname"].startswith(k):
                wanted[k] = c["citycode"]
    stations = {}
    for k, code in wanted.items():
        if code is None:
            continue
        st = items(call(f"tago_stations_{code}", f"{TRAIN}/GetCtyAcctoTrainSttnList",
                        {"serviceKey": DG, "_type": "json", "cityCode": code, "numOfRows": 200}))
        for s in st:
            stations[s["nodename"]] = s["nodeid"]
        print(f"   {k}({code}) stations:", [s["nodename"] for s in st][:15])
    dep, arr = stations.get("광주송정"), stations.get("용산")
    print("   광주송정:", dep, "용산:", arr)
    if not (dep and arr):
        print("   !! 역 ID 매칭 실패")
        return
    for plus in (1, 3, 7):
        day = (dt.date.today() + dt.timedelta(days=plus)).strftime("%Y%m%d")
        tr = items(call(f"tago_train_plus{plus}", f"{TRAIN}/GetStrtpntAlocFndTrainInfo",
                        {"serviceKey": DG, "_type": "json", "depPlaceId": dep, "arrPlaceId": arr,
                         "depPlandTime": day, "numOfRows": 100}))
        print(f"   +{plus}일({day}) 열차 {len(tr)}편", tr[:2])
    # 결과 없음 사례: 같은 역 출발=도착
    call("tago_train_empty", f"{TRAIN}/GetStrtpntAlocFndTrainInfo",
         {"serviceKey": DG, "_type": "json", "depPlaceId": dep, "arrPlaceId": dep,
          "depPlandTime": dt.date.today().strftime("%Y%m%d")})


def odsay():
    key = os.getenv("ODSAY_API_KEY", "")
    url = "https://api.odsay.com/v1/api/searchPubTransPathT"
    # 정상 1회: 광주송정역 → 광주 첨단(광주과학기술원 근처)
    b = call("odsay", url, {"SX": 126.7930, "SY": 35.1379, "EX": 126.8432, "EY": 35.2280, "apiKey": key})
    if isinstance(b, dict):
        paths = (b.get("result") or {}).get("path", [])
        print("   paths:", len(paths), [p.get("info", {}).get("totalTime") for p in paths[:3]], b.get("error"))
    # 결과 없음 1회: 바다 한가운데
    b = call("odsay_empty", url, {"SX": 125.0, "SY": 33.0, "EX": 125.1, "EY": 33.1, "apiKey": key})
    print("   empty:", str(b)[:200])


def mobility():
    b = call("kakao_mobility", "https://apis-navi.kakaomobility.com/v1/directions",
             {"origin": "126.7930,35.1379", "destination": "126.8432,35.2280"}, KAKAO)
    if isinstance(b, dict) and b.get("routes"):
        print("   summary:", b["routes"][0].get("summary", {}).get("fare"), b["routes"][0].get("summary", {}).get("duration"))


def kma():
    now = dt.datetime.now()
    base = now.replace(minute=0, second=0, microsecond=0)
    hours = [2, 5, 8, 11, 14, 17, 20, 23]
    h = max([x for x in hours if x <= (now - dt.timedelta(minutes=10)).hour] or [23])
    if h == 23 and now.hour < 2:
        base -= dt.timedelta(days=1)
    b = call("kma", "https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getVilageFcst",
             {"serviceKey": DG, "dataType": "JSON", "numOfRows": 1000, "pageNo": 1,
              "base_date": base.strftime("%Y%m%d"), "base_time": f"{h:02d}00", "nx": 58, "ny": 74})
    it = items(b)
    if it:
        days = sorted({i["fcstDate"] for i in it})
        print("   예보 날짜 범위:", days, "categories:", sorted({i["category"] for i in it}))


def its():
    b = call("its", "https://openapi.its.go.kr:9443/eventInfo",
             {"apiKey": os.getenv("ITS_API_KEY", ""), "type": "all", "eventType": "all",
              "minX": 126.6, "maxX": 127.1, "minY": 35.0, "maxY": 35.3, "getType": "json"})
    print("   ", str(b)[:300])


def tago_bus():
    b = call("tago_bus_terminals", f"{BUS}/GetExpBusTrminlList",
             {"serviceKey": DG, "_type": "json", "numOfRows": 300})
    print("   ", str(b)[:200])


def gms():
    key, base = os.getenv("GMS_API_KEY"), os.getenv("GMS_BASE_URL")
    if not key:
        print("[gms] SKIP — GMS_API_KEY 비어 있음")
        return
    from langchain_core.tools import tool
    from langchain_openai import ChatOpenAI, OpenAIEmbeddings

    @tool
    def search_trains(dep: str, arr: str, date: str) -> str:
        """두 역 사이 특정 날짜의 열차 시간표가 필요할 때 부른다."""
        return ""

    llm = ChatOpenAI(model=os.getenv("LLM_MODEL"), base_url=base, api_key=key)
    print("[gms] ping:", llm.invoke("한 단어로 답해: 안녕").content[:40])
    msg = llm.bind_tools([search_trains]).invoke("내일 광주송정에서 용산 가는 열차 시간 알려줘")
    print("[gms] tool_calls:", [c["name"] for c in msg.tool_calls])
    try:
        emb = OpenAIEmbeddings(model=os.getenv("EMBEDDING_MODEL"), base_url=base, api_key=key)
        print("[gms] embedding dim:", len(emb.embed_query("테스트")))
    except Exception as e:  # noqa: BLE001 — 지원 여부 확인용
        print("[gms] embedding FAIL", type(e).__name__)


ALL = {"kakao": kakao, "tago_train": tago_train, "odsay": odsay, "mobility": mobility,
       "kma": kma, "its": its, "tago_bus": tago_bus, "gms": gms}

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", choices=list(ALL))
    args = ap.parse_args()
    for name in args.only or ALL:
        try:
            ALL[name]()
        except Exception as e:  # noqa: BLE001 — 확인 스크립트는 다음 API로 계속
            print(f"[{name}] ERROR {type(e).__name__}: {scrub(str(e))[:200]}")
    sys.exit(0)
