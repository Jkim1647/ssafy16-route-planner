"""실행 이벤트 버스(F3012). 발행하는 쪽은 누가 구독하는지 모르고, 구독자 실패가 메인 흐름을 막지 않는다."""
import datetime as dt
import logging
from typing import Callable

log = logging.getLogger(__name__)


class EventBus:
    """동기 발행·구독 버스. publish는 구독자를 차례로 부르고, 구독자 예외는 경고 로그만 남기고 삼킨다."""
    def __init__(self):
        self._subs: list[Callable[[dict], None]] = []

    def subscribe(self, fn: Callable[[dict], None]) -> None:
        self._subs.append(fn)

    @property
    def subscriber_count(self) -> int:
        return len(self._subs)

    def publish(self, event: dict) -> None:
        for fn in list(self._subs):
            try:
                fn(event)
            except Exception:  # 로깅 실패가 대화를 깨면 안 된다(F3013)
                log.warning("event subscriber failed", exc_info=True)


class Emitter:
    """한 실행(run)의 이벤트를 세션·실행 식별자와 순번을 붙여 발행하고, 응답용 사본을 모은다."""

    def __init__(self, bus: EventBus, session_id: str, run_id: str):
        self.bus, self.session_id, self.run_id = bus, session_id, run_id
        self.seq = 0
        self.events: list[dict] = []

    def emit(self, type: str, *, agent: str = "main", node: str | None = None,
             payload: dict | None = None, duration_ms: int | None = None) -> dict:
        self.seq += 1
        e = {"session_id": self.session_id, "run_id": self.run_id, "seq": self.seq,
             "ts": dt.datetime.now().isoformat(timespec="milliseconds"), "agent": agent, "type": type,
             "node": node, "payload": payload or {}, "duration_ms": duration_ms}
        self.events.append(e)
        self.bus.publish(e)
        return e


def build_bus(event_repo, enabled: bool = True) -> EventBus:
    """LoggerAgent를 구독시킨 버스. enabled=False(LOGGING_ENABLED off)면 구독자가 없어 이벤트가 DB에 저장되지 않는다."""
    from backend.events.logger_agent import LoggerAgent

    bus = EventBus()
    if enabled:
        bus.subscribe(LoggerAgent(event_repo))
    return bus
