"""저장한 장소(집·교육장 등): 사용자별 CRUD, 장소 검색, 대화에서 이름으로 바로 쓰기."""
from backend.tools import registry
from backend.tools.base import Tool, fail, ok
from tests.agent.test_graph import DAY, A, Reply, env  # noqa: F401
from tests.api.test_auth import login, make_client  # noqa: F401

HOME = {"label": "집", "kind": "home", "name": "쌍암공원", "address": "광주 광산구 첨단동", "x": 126.84, "y": 35.22}
EDU = {"label": "교육장", "kind": "school", "name": "SSAFY 광주", "address": "광주 광산구 하남산단6번로", "x": 126.80, "y": 35.19}


def test_place_crud(make_client):
    c = make_client(required=False)
    r = c.post("/api/places", json=HOME)
    assert r.status_code == 201
    pid = r.json()["id"]
    c.post("/api/places", json=EDU)
    assert [p["label"] for p in c.get("/api/places").json()] == ["집", "교육장"]
    assert c.put(f"/api/places/{pid}", json={**HOME, "name": "새 집"}).json()["name"] == "새 집"
    assert c.delete(f"/api/places/{pid}").status_code == 204
    assert [p["label"] for p in c.get("/api/places").json()] == ["교육장"]


def test_place_label_unique_and_validated(make_client):
    c = make_client(required=False)
    c.post("/api/places", json=HOME)
    assert c.post("/api/places", json={**HOME, "name": "다른 곳"}).status_code == 409
    assert c.post("/api/places", json={**HOME, "label": ""}).status_code == 422
    assert c.post("/api/places", json={**HOME, "label": "가" * 21}).status_code == 422
    assert c.post("/api/places", json={**HOME, "label": "x", "y": 95}).status_code == 422


def test_places_are_per_user(make_client):
    a = login(make_client(required=True))
    pid = a.post("/api/places", json=HOME).json()["id"]
    a.cookies.clear()
    b = login(a, user="google:b", email="b@example.com")
    assert b.get("/api/places").json() == []
    assert b.post("/api/places", json=HOME).status_code == 201  # 같은 이름이어도 사용자마다 따로
    assert b.delete(f"/api/places/{pid}").status_code == 404


def test_place_search_uses_tool(make_client, monkeypatch):
    c = make_client(required=False)
    tools = dict(registry._TOOLS)
    tools["search_places"] = Tool("search_places", "d", {"type": "object", "properties": {}},
                                  lambda query, near_x=None, near_y=None: ok({"places": [
                                      {"name": "SSAFY 광주", "address": "광주", "x": 126.8, "y": 35.19, "place_url": "u"}]})
                                  if query == "싸피" else fail("NO_DATA", "없음"), "external")
    monkeypatch.setattr(registry, "_TOOLS", tools)
    assert c.get("/api/places/search", params={"q": "싸피"}).json()[0]["name"] == "SSAFY 광주"
    assert c.get("/api/places/search", params={"q": "없는곳"}).status_code == 404
    assert c.get("/api/places/search", params={"q": ""}).status_code == 422


def test_chat_uses_saved_place_by_label(env):
    from backend.db.repositories import PlaceRepo
    from backend.schemas import PlaceIn
    world, llm, make, db = env
    PlaceRepo(db).create(PlaceIn(**HOME))
    llm.responses = [A("plan_trip", origin="집", destination="강남역", date=DAY, arrive_by="14:00"), Reply(text="ok")]
    res = make()("집에서 강남역 2시까지")
    queries = [e["payload"]["args"]["query"] for e in res.events
               if e["type"] == "tool_call" and e["payload"]["tool"] == "search_places"]
    assert queries == ["강남역"]  # "집"은 검색하지 않고 저장한 좌표를 씀
    assert res.cards and res.cards[0]["points"][0]["name"] == "쌍암공원"
    assert any(e["type"] == "saved_place" for e in res.events)
