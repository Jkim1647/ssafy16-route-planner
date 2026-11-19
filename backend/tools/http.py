"""외부 API GET 헬퍼. 오류 메시지에 URL·파라미터(키 포함)를 절대 넣지 않는다(NF3002)."""
import requests

from backend.tools.base import INVALID_KEY, RATE_LIMITED, UPSTREAM_ERROR, fail, ok

TIMEOUT = 10


def fetch_json(url: str, *, params: dict | None = None, headers: dict | None = None) -> dict:
    """GET 후 JSON 본문을 ok(data)로 돌려준다. 실패: INVALID_KEY(401/403), RATE_LIMITED(429),
    UPSTREAM_ERROR(네트워크·그 밖의 4xx/5xx·JSON 아님). HTTP 200 안의 서비스 오류 코드는 호출하는 Tool이 따로 확인한다.
    """
    try:
        r = requests.get(url, params=params, headers=headers, timeout=TIMEOUT)
    except requests.RequestException:
        return fail(UPSTREAM_ERROR, "외부 API를 부르지 못했습니다.")
    if r.status_code in (401, 403):
        return fail(INVALID_KEY, "API 키가 없거나 올바르지 않습니다.")
    if r.status_code == 429:
        return fail(RATE_LIMITED, "외부 API 호출 한도를 넘었습니다.")
    if r.status_code >= 400:
        return fail(UPSTREAM_ERROR, f"외부 API 오류(HTTP {r.status_code})입니다.")
    try:
        return ok(r.json())
    except ValueError:
        return fail(UPSTREAM_ERROR, "외부 API 응답 형식이 올바르지 않습니다.")
