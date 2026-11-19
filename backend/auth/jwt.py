"""HS256 JWT (표준 라이브러리만 사용). 알고리즘은 HS256 하나만 받는다(alg none·다른 알고리즘 거절).

새 의존성을 넣지 않기 위해 직접 구현했다: 고정 헤더 비교, 상수 시간 서명 비교, exp 확인만 한다.
"""
import base64
import hashlib
import hmac
import json
import time

_HEADER = {"alg": "HS256", "typ": "JWT"}


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _sign(msg: str, secret: str) -> str:
    return _b64(hmac.new(secret.encode(), msg.encode(), hashlib.sha256).digest())


def encode(claims: dict, secret: str, ttl_sec: int) -> str:
    """claims에 iat·exp(지금 + ttl_sec초)를 붙여 HS256으로 서명한 토큰 문자열."""
    now = int(time.time())
    payload = {**claims, "iat": now, "exp": now + ttl_sec}
    msg = _b64(json.dumps(_HEADER, separators=(",", ":")).encode()) + "." + \
        _b64(json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode())
    return msg + "." + _sign(msg, secret)


def decode(token: str, secret: str) -> dict | None:
    """검증된 claims, 아니면 None(형식·헤더·서명·만료 중 하나라도 틀리면)."""
    try:
        head, body, sig = token.split(".")
        if json.loads(_unb64(head)) != _HEADER:
            return None
        if not hmac.compare_digest(_sign(f"{head}.{body}", secret), sig):
            return None
        claims = json.loads(_unb64(body))
        if not isinstance(claims, dict) or int(claims.get("exp", 0)) <= time.time() or not claims.get("sub"):
            return None
        return claims
    except (ValueError, TypeError, UnicodeDecodeError):
        return None
