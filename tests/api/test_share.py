"""계획 공유 링크(읽기 전용): 주인만 만들고 끊는다, 링크는 로그인 없이 보이되 개인 식별 정보는 빼고 보낸다."""
from tests.api.test_auth import login, make_client  # noqa: F401

PLAN = {"title": "집 → 교육장", "date": "2026-11-20", "leave_at": "08:25", "arrive_at": "08:50", "origin_name": "집",
        "destination_name": "교육장", "total_fare": 1250,
        "legs": [{"mode": "bus", "name": "34", "minutes": 18, "source": "odsay"}],
        "points": [{"kind": "origin", "name": "집", "x": 126.84, "y": 35.22},
                   {"kind": "destination", "name": "교육장", "x": 126.80, "y": 35.19}]}
JSON = {"content-type": "application/json"}


def owner_with_plan(make_client):
    c = login(make_client(required=True), "google:a", "a@example.com")
    pid = c.post("/api/plans", json=PLAN).json()["plan"]["id"]
    return c, pid


def test_share_create_view_revoke(make_client):
    c, pid = owner_with_plan(make_client)
    r = c.post(f"/api/plans/{pid}/share", json={})
    assert r.status_code == 200
    token = r.json()["token"]
    assert len(token) >= 20
    assert c.post(f"/api/plans/{pid}/share", json={}).json()["token"] == token  # 다시 눌러도 같은 링크
    assert c.get(f"/api/plans/{pid}").json()["share_token"] == token

    c.cookies.clear()  # 로그인하지 않은 사람
    v = c.get(f"/api/shared/{token}")
    assert v.status_code == 200
    body = v.json()
    assert body["title"] == "집 → 교육장" and body["legs"][0]["name"] == "34" and len(body["points"]) == 2
    for private in ("id", "user_id", "calendar_event_id", "source_run_id", "share_token"):
        assert private not in body

    login(c, "google:a", "a@example.com")
    assert c.delete(f"/api/plans/{pid}/share").status_code == 204
    c.cookies.clear()
    assert c.get(f"/api/shared/{token}").status_code == 404


def test_only_owner_can_share_or_revoke(make_client):
    c, pid = owner_with_plan(make_client)
    token = c.post(f"/api/plans/{pid}/share", json={}).json()["token"]
    login(c, "google:b", "b@example.com")
    assert c.post(f"/api/plans/{pid}/share", json={}).status_code == 404
    assert c.delete(f"/api/plans/{pid}/share").status_code == 404
    assert c.get(f"/api/shared/{token}").status_code == 200  # 링크 자체는 여전히 유효


def test_share_requires_json_and_bad_tokens_404(make_client):
    c, pid = owner_with_plan(make_client)
    assert c.post(f"/api/plans/{pid}/share", content="x", headers={"content-type": "text/plain"}).status_code == 415
    c.cookies.clear()
    for bad in ("short", "a" * 100, "..%2F..%2Fetc", "not-a-real-token-1234567890"):
        assert c.get(f"/api/shared/{bad}").status_code == 404


def test_deleting_plan_kills_link(make_client):
    c, pid = owner_with_plan(make_client)
    token = c.post(f"/api/plans/{pid}/share", json={}).json()["token"]
    c.delete(f"/api/plans/{pid}")
    assert c.get(f"/api/shared/{token}").status_code == 404
