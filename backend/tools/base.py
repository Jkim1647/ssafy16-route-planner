"""Tool 공통 규약: 성공도 실패도 같은 모양으로 반환하고, 예외를 밖으로 던지지 않는다."""
import logging
from dataclasses import dataclass
from typing import Callable, Literal

log = logging.getLogger(__name__)

BAD_ARGUMENT = "BAD_ARGUMENT"
INVALID_KEY = "INVALID_KEY"
NOT_FOUND = "NOT_FOUND"
NO_DATA = "NO_DATA"
UPSTREAM_ERROR = "UPSTREAM_ERROR"
AMBIGUOUS_PLACE = "AMBIGUOUS_PLACE"
OUT_OF_RANGE = "OUT_OF_RANGE"
NO_INDEX = "NO_INDEX"
RATE_LIMITED = "RATE_LIMITED"
CONFLICT = "CONFLICT"  # 이미 처리된 요청(예: 이미 캘린더에 등록한 계획)


def ok(data) -> dict:
    return {"ok": True, "data": data}


def fail(code: str, message: str) -> dict:
    return {"ok": False, "error": {"code": code, "message": message}}


@dataclass
class Tool:
    name: str
    description: str  # 기능이 아니라 "언제 쓰는지" — 모델이 읽는다
    parameters: dict  # JSON Schema
    func: Callable[..., dict]
    kind: Literal["external", "local"]

    def run(self, **kwargs) -> dict:
        try:
            return self.func(**kwargs)
        except TypeError:
            return fail(BAD_ARGUMENT, "입력값이 규약과 다릅니다.")
        except Exception:  # 원문에는 키가 든 URL이 섞일 수 있어 로그에만 남긴다
            log.exception("tool %s failed", self.name)
            return fail(UPSTREAM_ERROR, "Tool 실행 중 오류입니다.")
