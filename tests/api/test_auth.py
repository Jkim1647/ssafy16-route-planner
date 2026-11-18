"""로그인(Google OIDC + JWT 쿠키)과 사용자별 데이터 분리."""
import time
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

from backend.agent.graph import AnalyzeOut, Changes
from backend.auth import jwt as jwt_mod
from backend.container import Container
from backend.main import create_app
from tests.api.test_api import PLAN
from tests.fakes import FakeLLM

SECRET = "test-secret-0123456789abcdef0123456789"


@pytest.fixture
def make_client(tmp_path, monkeypatch):
    def make(required=True, **env):
        monkeypatch.setenv("DB_PATH", str(tmp_path / "app.db"))
        monkeypatch.setenv("AUTH_REQUIRED", "true" if required else "false")
        monkeypatch.setenv("JWT_SECRET", SECRET)
        monkeypatch.setenv("CALENDAR_BACKEND", "local")
        for k, v in env.items():
            monkeypatch.setenv(k, v)
        llm = FakeLLM()
        app = create_app(Container.build(llm_factory=lambda: llm))
        tc = TestClient(app, raise_server_exceptions=False, base_url="http://127.0.0.1")
        tc.llm = llm
        return tc
    return make


def login(client, user="google:a", email="a@example.com"):
    client.app.state.container.users.upsert(user, email, "A", None)
    client.cookies.set("rp_session", jwt_mod.encode({"sub": user, "email": email}, SECRET, ttl_sec=3600))
    return client


# ---------------------------------------------------------------- JWT
def test_jwt_roundtrip_and_tamper():
    tok = jwt_mod.encode({"sub": "u1"}, SECRET, ttl_sec=60)
    assert jwt_mod.decode(tok, SECRET)["sub"] == "u1"
    head, body, sig = tok.split(".")
    assert jwt_mod.decode(f"{head}.{body}.{sig[:-2]}AA", SECRET) is None       # 서명 위조
    assert jwt_mod.decode(tok, "other-secret-0123456789abcdef0123") is None      # 다른 키
    assert jwt_mod.decode("garbage", SECRET) is None


def test_jwt_rejects_expired_and_alg_none():
    old = jwt_mod.encode({"sub": "u1"}, SECRET, ttl_sec=-1)
    assert jwt_mod.decode(old, SECRET) is None
    none_tok = jwt_mod._b64(b'{"alg":"none","typ":"JWT"}') + "." + jwt_mod._b64(
        ('{"sub":"u1","exp":%d}' % (time.time() + 60)).encode()) + "."
    assert jwt_mod.decode(none_tok, SECRET) is None


# ---------------------------------------------------------------- 로그인 필요 모드
def test_requires_login_when_enabled(make_client):
    c = make_client(required=True)
    assert c.get("/api/plans").status_code == 401
    assert c.post("/api/chat", json={"message": "안녕"}).status_code == 401
    me = c.get("/api/auth/me").json()
    assert me["user"] is None and me["auth_required"] is True
    assert c.get("/api/config/status").status_code == 200


def test_bad_cookie_is_401(make_client):
    c = make_client(required=True)
    c.cookies.set("rp_session", "not-a-token")
    assert c.get("/api/plans").status_code == 401


def test_users_cannot_see_each_others_plans(make_client):
    a = login(make_client(required=True))
    pid = a.post("/api/plans", json=PLAN).json()["plan"]["id"]
    assert len(a.get("/api/plans").json()) == 1
    a.cookies.clear()
    b = login(a, user="google:b", email="b@example.com")
    assert b.get("/api/plans").json() == []
    assert b.get(f"/api/plans/{pid}").status_code == 404
    assert b.put(f"/api/plans/{pid}", json={"title": "x"}).status_code == 404
    assert b.delete(f"/api/plans/{pid}").status_code == 404
    assert b.post(f"/api/plans/{pid}/calendar", json={}).status_code == 404


def test_overlap_check_is_per_user(make_client):
    a = login(make_client(required=True))
    a.post("/api/plans", json=PLAN)
    a.cookies.clear()
    b = login(a, user="google:b", email="b@example.com")
    assert b.post("/api/plans", json=PLAN).json()["overlaps"] == []


def test_logs_are_per_user(make_client):
    a = login(make_client(required=True))
    a.llm.responses = [AnalyzeOut(intent="chat", intent_reason="인사", changes=Changes())]
    sid = a.post("/api/chat", json={"message": "안녕"}).json()["session_id"]
    assert [s["session_id"] for s in a.get("/api/logs").json()] == [sid]
    a.cookies.clear()
    b = login(a, user="google:b", email="b@example.com")
    assert b.get("/api/logs").json() == []
    assert b.get(f"/api/logs/{sid}").status_code == 404
    assert b.delete(f"/api/logs/{sid}").status_code == 404


def test_logout_clears_cookie(make_client):
    a = login(make_client(required=True))
    assert a.get("/api/auth/me").json()["user"]["email"] == "a@example.com"
    r = a.post("/api/auth/logout", json={})
    assert r.status_code == 204
    sc = r.headers["set-cookie"].lower()
    assert sc.startswith("rp_session=") and "max-age=0" in sc and "path=/" in sc  # 브라우저에 세션 쿠키 삭제 지시
    a.cookies.clear()
    assert a.get("/api/plans").status_code == 401


# ---------------------------------------------------------------- 로그인 끔(기존 동작)
def test_optional_mode_works_without_login(make_client):
    c = make_client(required=False)
    assert c.post("/api/plans", json=PLAN).status_code == 201
    assert c.get("/api/auth/me").json()["user"] is None


# ---------------------------------------------------------------- Google 로그인 흐름
def test_google_login_redirects_with_state(make_client):
    c = make_client(required=True, GOOGLE_CLIENT_ID="cid.apps.googleusercontent.com", GOOGLE_CLIENT_SECRET="sec",
                    GOOGLE_REDIRECT_URI="http://127.0.0.1:8000/api/auth/google/callback")
    r = c.get("/api/auth/google/login", follow_redirects=False)
    assert r.status_code == 302
    q = parse_qs(urlparse(r.headers["location"]).query)
    assert urlparse(r.headers["location"]).netloc == "accounts.google.com"
    assert q["client_id"] == ["cid.apps.googleusercontent.com"] and q["scope"] == ["openid email profile"]
    assert q["redirect_uri"] == ["http://127.0.0.1:8000/api/auth/google/callback"]
    assert q["state"][0] and c.cookies.get("rp_oauth_state") == q["state"][0]


def test_google_callback_rejects_bad_state(make_client):
    c = make_client(required=True, GOOGLE_CLIENT_ID="cid", GOOGLE_CLIENT_SECRET="sec")
    c.get("/api/auth/google/login", follow_redirects=False)
    r = c.get("/api/auth/google/callback?code=x&state=wrong", follow_redirects=False)
    assert r.status_code == 400


def test_google_callback_success_sets_session(make_client, monkeypatch):
    from backend.auth import google as g
    c = make_client(required=True, GOOGLE_CLIENT_ID="cid", GOOGLE_CLIENT_SECRET="sec",
                    FRONTEND_URL="http://127.0.0.1:5500/")
    monkeypatch.setattr(g, "exchange_code", lambda code, s: {"id_token": "idt"})
    monkeypatch.setattr(g, "verify_id_token", lambda tok, s: {"sub": "123", "email": "me@example.com",
                                                               "email_verified": True, "name": "나", "picture": None})
    state = parse_qs(urlparse(c.get("/api/auth/google/login", follow_redirects=False).headers["location"]).query)["state"][0]
    r = c.get(f"/api/auth/google/callback?code=abc&state={state}", follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"] == "http://127.0.0.1:5500/"
    assert "httponly" in r.headers["set-cookie"].lower()
    assert c.get("/api/auth/me").json()["user"]["email"] == "me@example.com"


def test_google_callback_rejects_unverified_email(make_client, monkeypatch):
    from backend.auth import google as g
    c = make_client(required=True, GOOGLE_CLIENT_ID="cid", GOOGLE_CLIENT_SECRET="sec")
    monkeypatch.setattr(g, "exchange_code", lambda code, s: {"id_token": "idt"})
    monkeypatch.setattr(g, "verify_id_token", lambda tok, s: {"sub": "1", "email": "x@example.com", "email_verified": False})
    state = parse_qs(urlparse(c.get("/api/auth/google/login", follow_redirects=False).headers["location"]).query)["state"][0]
    assert c.get(f"/api/auth/google/callback?code=abc&state={state}", follow_redirects=False).status_code == 400


# ---------------------------------------------------------------- 실제 Google 캘린더는 소유자만
def test_google_calendar_only_for_owner(monkeypatch, tmp_path):
    from backend.auth.context import use_user
    from backend.calendar.base import get_calendar
    from backend.settings import get_settings
    monkeypatch.setenv("DB_PATH", str(tmp_path / "x.db"))
    monkeypatch.setenv("CALENDAR_BACKEND", "google")
    monkeypatch.setenv("AUTH_REQUIRED", "true")
    monkeypatch.setenv("CALENDAR_OWNER_EMAIL", "owner@example.com")
    with use_user("google:o", "owner@example.com"):
        assert get_calendar(get_settings()).name == "google"
    with use_user("google:x", "other@example.com"):
        assert get_calendar(get_settings()).name == "local"
