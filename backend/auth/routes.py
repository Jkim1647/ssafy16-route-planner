"""로그인 API: 현재 사용자, Google 로그인 시작·콜백, 로그아웃."""
import hmac
import logging
import secrets

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import RedirectResponse

from backend.auth import google, jwt
from backend.auth.context import current_user_id
from backend.auth.middleware import COOKIE

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["로그인"])
STATE_COOKIE = "rp_oauth_state"
SESSION_TTL = 7 * 24 * 3600


def _c(request: Request):
    return request.app.state.container


def _configured(s) -> bool:
    return bool(s.GOOGLE_CLIENT_ID and s.GOOGLE_CLIENT_SECRET)


@router.get("/me")
def me(request: Request):
    c = _c(request)
    uid = current_user_id()
    user = c.users.get(uid) if uid != "local" else None
    return {"user": user, "auth_required": c.settings.AUTH_REQUIRED, "google_configured": _configured(c.settings)}


@router.get("/google/login")
def google_login(request: Request):
    s = _c(request).settings
    if not _configured(s):
        raise HTTPException(503, "Google 로그인이 설정되지 않았어요(.env의 GOOGLE_CLIENT_ID·SECRET).")
    state = secrets.token_urlsafe(24)  # 로그인 위조(CSRF) 방지: 돌아올 때 쿠키 값과 같아야 한다
    r = RedirectResponse(google.login_url(s, state), status_code=302)
    r.set_cookie(STATE_COOKIE, state, max_age=600, httponly=True, samesite="lax", path="/api/auth")
    return r


@router.get("/google/callback")
def google_callback(request: Request, code: str = "", state: str = "", error: str = ""):
    c = _c(request)
    s = c.settings
    expected = request.cookies.get(STATE_COOKIE) or ""
    if error or not code or not state or not expected or not hmac.compare_digest(state, expected):
        raise HTTPException(400, "로그인 요청이 올바르지 않아요. 다시 시도해 주세요.")
    try:
        tokens = google.exchange_code(code, s)
        claims = google.verify_id_token(tokens["id_token"], s)
    except Exception:
        log.exception("google login failed")
        raise HTTPException(400, "Google 로그인 확인에 실패했어요.")
    if not claims.get("email_verified"):
        raise HTTPException(400, "이메일 인증이 된 Google 계정만 쓸 수 있어요.")
    uid = "google:" + str(claims["sub"])
    c.users.upsert(uid, claims.get("email"), claims.get("name"), claims.get("picture"))
    r = RedirectResponse(s.FRONTEND_URL, status_code=302)
    r.set_cookie(COOKIE, jwt.encode({"sub": uid, "email": claims.get("email")}, request.app.state.jwt_secret,
                                    SESSION_TTL), max_age=SESSION_TTL, httponly=True, samesite="lax", path="/")
    r.delete_cookie(STATE_COOKIE, path="/api/auth")
    return r


@router.post("/logout", status_code=204)
def logout():
    r = Response(status_code=204)
    r.delete_cookie(COOKIE, path="/")
    return r
