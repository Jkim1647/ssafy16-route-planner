"""외부 API 영구 캐시 + 일일 쿼터(설계 19장). ODsay 하루 30회·ITS 월 100회를 지킨다."""
import contextlib
import datetime as dt
import json
import os
import sqlite3
import time
from typing import Callable

from backend.tools.base import RATE_LIMITED, fail

COORD_KEYS = {"sx", "sy", "ex", "ey", "x", "y", "lat", "lon"}


def normalize_args(args: dict) -> str:
    """캐시·재사용 키용 인자 직렬화: 키 정렬 JSON, 좌표 인자(COORD_KEYS)는 소수 셋째 자리로 반올림해
    거의 같은 위치(약 100m 이내)를 같은 키로 본다.
    """
    norm = {k: round(float(v), 3) if k.lower() in COORD_KEYS and v is not None else v
            for k, v in args.items()}
    return json.dumps(norm, sort_keys=True, ensure_ascii=False)


def _limits() -> dict[str, dict]:
    use_reserve = os.getenv("QUOTA_USE_RESERVE", "false").lower() in {"1", "true", "on", "yes"}
    od_total = int(os.getenv("ODSAY_DAILY_LIMIT", "30"))
    od_res = int(os.getenv("ODSAY_RESERVE", "6"))
    return {
        "odsay": {"daily": od_total if use_reserve else od_total - od_res, "shown": od_total},
        "its": {"daily": int(os.getenv("ITS_DAILY_SOFT", "4")),
                "monthly": int(os.getenv("ITS_MONTHLY_LIMIT", "100")),
                "shown": int(os.getenv("ITS_MONTHLY_LIMIT", "100"))},
    }


class ApiBudget:
    """외부 API 영구 캐시(api_cache)와 API별 일·월 호출 수(api_quota)를 SQLite에 두는 관문. 외부 Tool은 cached_call로만 부른다.
    캐시 적중이면 호출 없음, 한도 초과면 RATE_LIMITED, 아니면 1회로 세고 호출(실패도 셈) 후 성공만 TTL 동안 캐시.
    today는 테스트에서 날짜를 바꾸려고 주입한다.
    """
    def __init__(self, db_path: str, today: Callable[[], dt.date] = dt.date.today):
        self.db_path = db_path
        self.today = today
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        with self._conn() as c:
            c.execute("CREATE TABLE IF NOT EXISTS api_cache(key TEXT PRIMARY KEY, value_json TEXT, expires_at REAL)")
            c.execute("CREATE TABLE IF NOT EXISTS api_quota(day TEXT, api TEXT, used INTEGER, PRIMARY KEY(day, api))")

    def _conn(self):
        return sqlite3.connect(self.db_path)

    @contextlib.contextmanager
    def no_cache(self):
        """캐시를 읽지 않고 실제로 호출한다(이상 징후 검증용 중복 호출 재현에만 사용)."""
        self._bypass = True
        try:
            yield
        finally:
            self._bypass = False

    def _used(self, c, api: str, day: dt.date) -> int:
        row = c.execute("SELECT used FROM api_quota WHERE day=? AND api=?", (day.isoformat(), api)).fetchone()
        return row[0] if row else 0

    def _month_used(self, c, api: str, day: dt.date) -> int:
        row = c.execute("SELECT COALESCE(SUM(used),0) FROM api_quota WHERE api=? AND day LIKE ?",
                        (api, day.strftime("%Y-%m-%%"))).fetchone()
        return row[0]

    def _over_limit(self, c, api: str, day: dt.date) -> bool:
        lim = _limits().get(api)
        if not lim:
            return False
        if self._used(c, api, day) >= lim["daily"]:
            return True
        return "monthly" in lim and self._month_used(c, api, day) >= lim["monthly"]

    def cached_call(self, api: str, args: dict, ttl_sec: int, fn: Callable[[], dict]) -> dict:
        key = f"{api}:{normalize_args(args)}"
        now, day = time.time(), self.today()
        with self._conn() as c:
            row = None if getattr(self, "_bypass", False) else \
                c.execute("SELECT value_json FROM api_cache WHERE key=? AND expires_at>?", (key, now)).fetchone()
            if row:
                return {**json.loads(row[0]), "cached": True}
            if self._over_limit(c, api, day):
                return {**fail(RATE_LIMITED, f"오늘 {api} 조회 한도에 도달했어요."), "cached": False}
            c.execute("INSERT INTO api_quota(day, api, used) VALUES(?,?,1) "
                      "ON CONFLICT(day, api) DO UPDATE SET used=used+1", (day.isoformat(), api))
        result = fn()  # 실패 응답도 호출 1회로 센다
        if result.get("ok") and ttl_sec > 0:
            with self._conn() as c:
                c.execute("INSERT OR REPLACE INTO api_cache VALUES(?,?,?)",
                          (key, json.dumps(result, ensure_ascii=False), now + ttl_sec))
        return {**result, "cached": False}

    def usage(self) -> dict[str, dict]:
        day = self.today()
        with self._conn() as c:
            return {api: {"used": self._month_used(c, api, day) if "monthly" in lim else self._used(c, api, day),
                          "limit": lim["shown"]}
                    for api, lim in _limits().items()}


_default: ApiBudget | None = None


def default_budget() -> ApiBudget:
    """앱 전역 예산 객체(설정의 DB_PATH 사용)."""
    global _default
    if _default is None:
        from backend.settings import get_settings
        _default = ApiBudget(get_settings().DB_PATH)
    return _default


def set_default_budget(budget: ApiBudget | None) -> None:
    """default_budget()이 돌려줄 전역 ApiBudget을 바꾼다. 테스트가 임시 DB로 갈아끼우는 데 쓰며,
    None이면 다음 default_budget() 호출 때 설정의 DB_PATH로 새로 만든다.
    """
    global _default
    _default = budget
