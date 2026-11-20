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


def ok(data, cached: bool | None = None) -> dict:
    """성공 결과. cached: 외부 API 결과를 영구 캐시에서 꺼냈는지(`ApiBudget.cached_call`의 값을 그대로 넘긴다).
    실행 로그의 '캐시' 표시가 이 값을 쓰므로, 캐시를 거치는 Tool은 가공한 결과에도 함께 넘겨야 한다."""
    r = {"ok": True, "data": data}
    if cached is not None:
        r["cached"] = cached
    return r


def fail(code: str, message: str) -> dict:
    return {"ok": False, "error": {"code": code, "message": message}}


def _type_mismatch(schema: dict, args: dict) -> str | None:
    """JSON Schema의 number·integer·string 타입과 맞지 않는 인자 이름(첫 번째). 숫자로 읽히는 문자열은 허용(기존 호출 호환)."""
    props = (schema or {}).get("properties") or {}
    for k, v in args.items():
        want = (props.get(k) or {}).get("type")
        if v is None or want not in ("number", "integer", "string"):
            continue
        if want == "string":
            if not isinstance(v, str):
                return k
            continue
        if isinstance(v, bool):
            return k
        if isinstance(v, str):
            try:
                n = float(v)
            except ValueError:
                return k
            if want == "integer" and not n.is_integer():
                return k
        elif not isinstance(v, (int, float)) or (want == "integer" and isinstance(v, float) and not v.is_integer()):
            return k
    return None


@dataclass
class Tool:
    name: str
    description: str  # 기능이 아니라 "언제 쓰는지" — 모델이 읽는다
    parameters: dict  # JSON Schema
    func: Callable[..., dict]
    kind: Literal["external", "local"]

    def run(self, **kwargs) -> dict:
        bad = _type_mismatch(self.parameters, kwargs)
        if bad:  # 잘못된 입력을 함수 안의 예외(UPSTREAM_ERROR)로 오인하지 않게 입력 규격으로 먼저 거른다
            return fail(BAD_ARGUMENT, f"입력값 형식이 규약과 다릅니다: {bad}")
        try:
            return self.func(**kwargs)
        except TypeError:
            return fail(BAD_ARGUMENT, "입력값이 규약과 다릅니다.")
        except Exception:  # 원문에는 키가 든 URL이 섞일 수 있어 로그에만 남긴다
            log.exception("tool %s failed", self.name)
            return fail(UPSTREAM_ERROR, "Tool 실행 중 오류입니다.")
