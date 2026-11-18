"""환경변수 설정. 키는 .env에서만 읽고 코드에 적지 않는다(NF3001)."""
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
SECRET_KEYS = ("GMS_API_KEY", "KAKAO_REST_KEY", "ODSAY_API_KEY", "DATA_GO_KR_KEY", "ITS_API_KEY")
_TRUE = {"1", "true", "on", "yes"}


def _str(name, default=None):
    v = os.getenv(name)
    return v.strip() if v and v.strip() else default


def _int(name, default):
    v = _str(name)
    return int(v) if v is not None else default


def _bool(name, default):
    v = _str(name)
    return v.lower() in _TRUE if v is not None else default


@dataclass(frozen=True)
class Settings:
    GMS_API_KEY: str | None
    GMS_BASE_URL: str | None
    LLM_MODEL: str
    LLM_REASONING_EFFORT: str | None
    EMBEDDING_MODEL: str
    KAKAO_REST_KEY: str | None
    ODSAY_API_KEY: str | None
    DATA_GO_KR_KEY: str | None
    ITS_API_KEY: str | None
    AGENT_MODE: str
    WORKER_LLM: bool
    MAX_REPLAN: int
    WORKER_MAX_RETRY: int
    LOGGING_ENABLED: bool
    CALENDAR_BACKEND: str
    GOOGLE_CALENDAR_ID: str
    DEBUG_FORCE: str | None
    ODSAY_DAILY_LIMIT: int
    ODSAY_RESERVE: int
    QUOTA_USE_RESERVE: bool
    ITS_MONTHLY_LIMIT: int
    ITS_DAILY_SOFT: int
    DB_PATH: str
    CHROMA_DIR: str

    def key_status(self) -> dict[str, bool]:
        """키 이름 → 설정 여부. 값은 절대 포함하지 않는다(NF3002)."""
        return {k: bool(getattr(self, k)) for k in SECRET_KEYS}


def get_settings() -> Settings:
    load_dotenv(ROOT / ".env")  # 이미 있는 환경변수는 덮어쓰지 않음
    return Settings(
        GMS_API_KEY=_str("GMS_API_KEY"),
        GMS_BASE_URL=_str("GMS_BASE_URL"),
        LLM_MODEL=_str("LLM_MODEL", "gpt-6-luna"),
        LLM_REASONING_EFFORT=_str("LLM_REASONING_EFFORT"),
        EMBEDDING_MODEL=_str("EMBEDDING_MODEL", "text-embedding-3-small"),
        KAKAO_REST_KEY=_str("KAKAO_REST_KEY"),
        ODSAY_API_KEY=_str("ODSAY_API_KEY"),
        DATA_GO_KR_KEY=_str("DATA_GO_KR_KEY"),
        ITS_API_KEY=_str("ITS_API_KEY"),
        AGENT_MODE=_str("AGENT_MODE", "single"),
        WORKER_LLM=_bool("WORKER_LLM", True),
        MAX_REPLAN=_int("MAX_REPLAN", 3),
        WORKER_MAX_RETRY=_int("WORKER_MAX_RETRY", 2),
        LOGGING_ENABLED=_bool("LOGGING_ENABLED", True),
        CALENDAR_BACKEND=_str("CALENDAR_BACKEND", "local"),
        GOOGLE_CALENDAR_ID=_str("GOOGLE_CALENDAR_ID", "primary"),
        DEBUG_FORCE=_str("DEBUG_FORCE"),
        ODSAY_DAILY_LIMIT=_int("ODSAY_DAILY_LIMIT", 30),
        ODSAY_RESERVE=_int("ODSAY_RESERVE", 6),
        QUOTA_USE_RESERVE=_bool("QUOTA_USE_RESERVE", False),
        ITS_MONTHLY_LIMIT=_int("ITS_MONTHLY_LIMIT", 100),
        ITS_DAILY_SOFT=_int("ITS_DAILY_SOFT", 4),
        DB_PATH=_str("DB_PATH", str(ROOT / "data" / "app.db")),
        CHROMA_DIR=_str("CHROMA_DIR", str(ROOT / "data" / "chroma")),
    )
