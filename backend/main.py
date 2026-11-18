"""FastAPI 앱. 실행: uvicorn backend.main:app --reload (8000번)."""
import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.api.routes import router
from backend.container import Container

log = logging.getLogger(__name__)
ALLOWED_ORIGINS = ["http://127.0.0.1:5500", "http://localhost:5500"]  # VS Code Live Server만 허용


def create_app(container: Container | None = None) -> FastAPI:
    app = FastAPI(title="이동 플래너 API", version="1.0",
                  description="Agent 기반 이동 플래너 — 대화·계획 관리·실행 로그")
    app.state.container = container or Container.build()
    app.add_middleware(CORSMiddleware, allow_origins=ALLOWED_ORIGINS, allow_methods=["GET", "POST", "PUT", "DELETE"],
                       allow_headers=["Content-Type"])

    @app.exception_handler(Exception)
    async def _hide_detail(request: Request, exc: Exception):  # 원문은 서버 로그에만(NF3002)
        log.exception("unhandled error")
        return JSONResponse(status_code=500, content={"detail": "서버 오류가 발생했어요."})

    app.include_router(router)
    return app


def __getattr__(name):  # `uvicorn backend.main:app` 시점에 앱 생성(import만으로 DB를 만들지 않도록)
    if name == "app":
        globals()["app"] = create_app()
        return globals()["app"]
    raise AttributeError(name)
