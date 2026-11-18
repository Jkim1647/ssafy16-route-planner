"""SQLite 연결과 스키마. 호출마다 새 연결(FastAPI 스레드 안전)."""
import os
import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS plans(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  title TEXT NOT NULL, date TEXT NOT NULL, leave_at TEXT NOT NULL, arrive_at TEXT NOT NULL,
  origin_name TEXT NOT NULL, destination_name TEXT NOT NULL, legs_json TEXT NOT NULL DEFAULT '[]',
  total_fare INTEGER, source_run_id TEXT, calendar_event_id TEXT,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL, points_json TEXT NOT NULL DEFAULT '[]');
CREATE TABLE IF NOT EXISTS runs(
  run_id TEXT PRIMARY KEY, session_id TEXT NOT NULL, user_message TEXT, mode TEXT, status TEXT,
  replan_count INTEGER DEFAULT 0, llm_calls INTEGER DEFAULT 0, started_at TEXT, ended_at TEXT);
CREATE TABLE IF NOT EXISTS run_events(
  id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL, run_id TEXT NOT NULL, seq INTEGER NOT NULL,
  ts TEXT NOT NULL, agent TEXT, type TEXT NOT NULL, node TEXT, payload_json TEXT, duration_ms INTEGER);
CREATE INDEX IF NOT EXISTS idx_events_session ON run_events(session_id, run_id, seq);
CREATE TABLE IF NOT EXISTS anomaly_reports(
  run_id TEXT PRIMARY KEY, verdict TEXT NOT NULL, findings_json TEXT NOT NULL, diagnosis TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS users(
  id TEXT PRIMARY KEY, email TEXT, name TEXT, picture TEXT, created_at TEXT NOT NULL, last_login TEXT);
CREATE TABLE IF NOT EXISTS local_calendar(
  id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, start TEXT NOT NULL, "end" TEXT NOT NULL, plan_id INTEGER);
"""


def connect(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(path: str) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with connect(path) as c:
        c.executescript(SCHEMA)
        # 1일차에 만든 DB에는 지점 칸이 없다 → 기존 계획은 빈 목록으로 두고 칸만 추가
        cols = {r[1] for r in c.execute("PRAGMA table_info(plans)")}
        if "points_json" not in cols:
            c.execute("ALTER TABLE plans ADD COLUMN points_json TEXT NOT NULL DEFAULT '[]'")
        # 로그인 도입 전 데이터는 이 컴퓨터 사용자("local") 것으로 둔다
        for table in ("plans", "runs", "local_calendar"):
            if "user_id" not in {r[1] for r in c.execute(f"PRAGMA table_info({table})")}:
                c.execute(f"ALTER TABLE {table} ADD COLUMN user_id TEXT NOT NULL DEFAULT 'local'")
