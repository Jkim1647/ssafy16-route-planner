"""Google 로그인(OpenID Connect, 인가 코드 방식). 서버가 코드를 토큰으로 바꾸고 id_token을 검증한다."""
from urllib.parse import urlencode

import requests

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"


def login_url(settings, state: str) -> str:
    return AUTH_URL + "?" + urlencode({
        "client_id": settings.GOOGLE_CLIENT_ID, "redirect_uri": settings.GOOGLE_REDIRECT_URI,
        "response_type": "code", "scope": "openid email profile", "state": state, "prompt": "select_account"})


def exchange_code(code: str, settings) -> dict:
    r = requests.post(TOKEN_URL, data={
        "code": code, "client_id": settings.GOOGLE_CLIENT_ID, "client_secret": settings.GOOGLE_CLIENT_SECRET,
        "redirect_uri": settings.GOOGLE_REDIRECT_URI, "grant_type": "authorization_code"}, timeout=10)
    r.raise_for_status()
    return r.json()


def verify_id_token(token: str, settings) -> dict:
    """서명·발급자·대상(aud=우리 클라이언트 ID)·만료를 google-auth로 검증한다."""
    from google.auth.transport.requests import Request
    from google.oauth2 import id_token
    return id_token.verify_oauth2_token(token, Request(), settings.GOOGLE_CLIENT_ID)
