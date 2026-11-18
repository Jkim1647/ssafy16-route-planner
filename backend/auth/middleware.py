"""요청마다 JWT 쿠키를 확인해 현재 사용자를 정한다. 로그인 필수 모드에서 로그인 안 한 API 요청은 401."""
import json
from http.cookies import CookieError, SimpleCookie

from backend.auth import jwt
from backend.auth.context import LOCAL, reset_user, set_user

COOKIE = "rp_session"
PUBLIC = ("/api/auth/", "/api/config/status")


def session_claims(scope, secret: str) -> dict | None:
    raw = next((v.decode("latin-1") for k, v in scope.get("headers", []) if k == b"cookie"), "")
    c = SimpleCookie()
    try:
        c.load(raw)
    except CookieError:
        return None
    return jwt.decode(c[COOKIE].value, secret) if COOKIE in c else None


class AuthMiddleware:
    def __init__(self, app, secret: str, required: bool):
        self.app, self.secret, self.required = app, secret, required

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        claims = session_claims(scope, self.secret)
        path = scope.get("path", "")
        if claims is None and self.required and path.startswith("/api/") and not path.startswith(PUBLIC) \
                and scope.get("method") != "OPTIONS":
            body = json.dumps({"detail": "로그인이 필요해요."}, ensure_ascii=False).encode()
            await send({"type": "http.response.start", "status": 401,
                        "headers": [(b"content-type", b"application/json"),
                                    (b"content-length", str(len(body)).encode())]})
            await send({"type": "http.response.body", "body": body})
            return
        token = set_user(claims["sub"], claims.get("email")) if claims else set_user(*LOCAL)
        try:
            await self.app(scope, receive, send)
        finally:
            reset_user(token)
