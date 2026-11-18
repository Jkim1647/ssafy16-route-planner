"""요청마다 '현재 사용자'를 담는 컨텍스트. 로그인을 끈 모드에서는 이 컴퓨터 사용자 한 명("local")."""
from contextlib import contextmanager
from contextvars import ContextVar

LOCAL = ("local", None)
_user: ContextVar[tuple[str, str | None]] = ContextVar("rp_user", default=LOCAL)


def current_user_id() -> str:
    return _user.get()[0]


def current_email() -> str | None:
    return _user.get()[1]


def set_user(user_id: str, email: str | None):
    return _user.set((user_id, email))


def reset_user(token) -> None:
    _user.reset(token)


@contextmanager
def use_user(user_id: str, email: str | None = None):
    token = set_user(user_id, email)
    try:
        yield
    finally:
        reset_user(token)
