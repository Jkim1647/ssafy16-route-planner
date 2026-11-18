"""외부 API 영구 캐시 + 일일 쿼터(설계 19장). ODsay 하루 30회·ITS 월 100회를 지킨다."""
import datetime as dt
import json
import os
import sqlite3
import time
from typing import Callable

from backend.tools.base import RATE_LIMITED, fail

COORD_KEYS = {"sx", "sy", "ex", "ey", "x", "y", "lat", "lon"}


def normalize_args(args: dict) -> str:
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
    def __init__(self, db_path: str, today: Callable[[], dt.date] = dt.date.today):
        self.db_path = db_path
        self.today = today
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        with self._conn() as c:
            c.execute("CREATE TABLE IF NOT EXISTS api_cache(key TEXT PRIMARY KEY, value_json TEXT, expires_at REAL)")
            c.execute("CREATE TABLE IF NOT EXISTS api_quota(day TEXT, api TEXT, used INTEGER, PRIMARY KEY(day, api))")

    def _conn(self):
        return sqlite3.connect(self.db_path)

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
            row = c.execute("SELECT value_json FROM api_cache WHERE key=? AND expires_at>?", (key, now)).fetchone()
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
    global _default
    _default = budget
