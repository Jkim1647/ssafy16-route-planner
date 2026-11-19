"""FastAPI 앱. 실행: uvicorn backend.main:app --reload (8000번)."""
import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
import secrets

from backend.auth.middleware import AuthMiddleware
from backend.auth.routes import router as auth_router
from fastapi.responses import JSONResponse

from backend.api.routes import router
from backend.container import Container

log = logging.getLogger(__name__)
ALLOWED_ORIGINS = ["http://127.0.0.1:5500", "http://localhost:5500"]  # 프론트(5500)만 허용
# 이 컴퓨터 주소로 온 요청만 받는다. 악성 도메인을 127.0.0.1로 바꿔치기하는 공격(DNS rebinding)은
# Host 헤더가 그 도메인이라 여기서 거절된다.
ALLOWED_HOSTS = ["127.0.0.1", "localhost"]


def create_app(container: Container | None = None) -> FastAPI:
    """앱 팩토리. container를 주면 그것을(테스트에서 가짜 LLM 주입), 없으면 설정으로 Container를 만든다.
    JWT_SECRET이 없거나 32자 미만이면 실행마다 임시 키를 만들어, 서버를 다시 켜면 로그인이 풀린다.
    """
    app = FastAPI(title="이동 플래너 API", version="1.0",
                  description="Agent 기반 이동 플래너 — 대화·계획 관리·실행 로그")
    app.state.container = container or Container.build()
    s = app.state.container.settings
    if not s.JWT_SECRET or len(s.JWT_SECRET) < 32:
        if s.AUTH_REQUIRED:
            log.warning("JWT_SECRET이 없거나 짧아 임시 키를 씁니다(서버를 다시 켜면 다시 로그인해야 함).")
        app.state.jwt_secret = secrets.token_urlsafe(48)
    else:
        app.state.jwt_secret = s.JWT_SECRET
    # 바깥쪽부터 CORS → Host 검사 → 로그인 확인 순서(나중에 추가한 것이 바깥)
    app.add_middleware(AuthMiddleware, secret=app.state.jwt_secret, required=s.AUTH_REQUIRED)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=ALLOWED_HOSTS)
    app.add_middleware(CORSMiddleware, allow_origins=ALLOWED_ORIGINS, allow_methods=["GET", "POST", "PUT", "DELETE"],
                       allow_headers=["Content-Type"], allow_credentials=True)

    @app.exception_handler(Exception)
    async def _hide_detail(request: Request, exc: Exception):  # 원문은 서버 로그에만(NF3002)
        log.exception("unhandled error")
        return JSONResponse(status_code=500, content={"detail": "서버 오류가 발생했어요."})

    app.include_router(auth_router)
    app.include_router(router)
    return app


def __getattr__(name):  # `uvicorn backend.main:app` 시점에 앱 생성(import만으로 DB를 만들지 않도록)
    if name == "app":
        globals()["app"] = create_app()
        return globals()["app"]
    raise AttributeError(name)
