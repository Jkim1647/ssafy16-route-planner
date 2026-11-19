"""요청마다 JWT 쿠키를 확인해 현재 사용자를 정한다. 로그인 필수 모드에서 로그인 안 한 API 요청은 401."""
import json
from http.cookies import CookieError, SimpleCookie

from backend.auth import jwt
from backend.auth.context import LOCAL, reset_user, set_user

COOKIE = "rp_session"
PUBLIC = ("/api/auth/", "/api/config/status", "/api/shared/")  # 공유 링크는 로그인 없이(읽기 전용, 토큰으로만)


def session_claims(scope, secret: str) -> dict | None:
    """ASGI scope의 Cookie 헤더에서 세션 JWT를 꺼내 검증된 claims를 돌려준다. 쿠키가 없거나 형식·서명·만료가 틀리면 None."""
    raw = next((v.decode("latin-1") for k, v in scope.get("headers", []) if k == b"cookie"), "")
    c = SimpleCookie()
    try:
        c.load(raw)
    except CookieError:
        return None
    return jwt.decode(c[COOKIE].value, secret) if COOKIE in c else None


class AuthMiddleware:
    """요청마다 현재 사용자 컨텍스트(set_user)를 정하고 응답 뒤 되돌리는 ASGI 미들웨어.
    required(AUTH_REQUIRED)일 때 로그인 없는 /api/ 요청은 401, 단 PUBLIC 경로와 OPTIONS(CORS 사전 요청)는 통과.
    로그인하지 않은 요청은 로컬 사용자("local")로 본다.
    """
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
