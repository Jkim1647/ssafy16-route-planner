import ast
import pathlib

from backend.db.database import init_db
from backend.db.repositories import EventRepo
from backend.events.bus import EventBus, Emitter, build_bus
from backend.events.logger_agent import LoggerAgent


def test_publish_without_subscribers_ok():
    EventBus().publish({"type": "x"})


def test_failing_subscriber_does_not_raise():
    bus = EventBus()
    got = []

    def bad(e):
        raise RuntimeError("db down")

    bus.subscribe(bad)
    bus.subscribe(got.append)
    bus.publish({"type": "x"})
    assert got == [{"type": "x"}]


def test_emitter_seq_increments():
    bus = EventBus()
    em = Emitter(bus, "s1", "r1")
    a = em.emit("node_start", node="analyze")
    b = em.emit("node_end", node="analyze", payload={"intent": "chat"}, duration_ms=3)
    assert (a["seq"], b["seq"]) == (1, 2)
    assert b["session_id"] == "s1" and b["run_id"] == "r1" and b["agent"] == "main"
    assert em.events == [a, b]


def test_logger_agent_appends_in_order(tmp_path):
    db = str(tmp_path / "a.db")
    init_db(db)
    bus = EventBus()
    bus.subscribe(LoggerAgent(EventRepo(db)))
    em = Emitter(bus, "s1", "r1")
    for t in ("run_start", "node_start", "run_end"):
        em.emit(t)
    assert [e["type"] for e in EventRepo(db).get_session("s1")] == ["run_start", "node_start", "run_end"]


def test_logger_agent_swallow_storage_failure():
    class Broken:
        def append(self, e):
            raise OSError("disk full")

    LoggerAgent(Broken())({"type": "x"})


def test_logging_disabled_no_subscriber(tmp_path):
    db = str(tmp_path / "a.db")
    init_db(db)
    assert build_bus(EventRepo(db), enabled=False).subscriber_count == 0
    assert build_bus(EventRepo(db), enabled=True).subscriber_count == 1


def test_logger_agent_does_not_import_llm():
    src = pathlib.Path("backend/events/logger_agent.py").read_text(encoding="utf-8")
    names = {n.module or "" for n in ast.walk(ast.parse(src)) if isinstance(n, ast.ImportFrom)}
    names |= {a.name for n in ast.walk(ast.parse(src)) if isinstance(n, ast.Import) for a in n.names}
    assert not any("langchain" in n or "openai" in n or "llm" in n for n in names)
