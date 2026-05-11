"""FastAPI 앱 진입점 — DI 조립 + CORS + 라우터 등록.

실행:
    uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

OpenAPI / Swagger UI:
    GET /docs       (Swagger UI)
    GET /redoc      (ReDoc)
    GET /openapi.json
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.routers import auth, cashback, dashboard, insights, settings, usage


def create_app() -> FastAPI:
    cfg = get_settings()
    app = FastAPI(
        title="ax_nilm API Server",
        version="0.1.0",
        description="NILM 기반 KEPCO 에너지캐시백 서비스 API",
    )

    # CORS — Frontend (Vite dev) 의 withCredentials 호출 허용
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.cors_origins_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )

    # 헬스체크 (배포 환경 readiness probe)
    @app.get("/healthz", tags=["meta"])
    def healthz() -> dict[str, str]:
        return {"status": "ok", "env": cfg.app_env}

    @app.get("/", tags=["meta"])
    def root() -> JSONResponse:
        return JSONResponse({"name": "ax_nilm API", "docs": "/docs"})

    # 라우터 등록
    app.include_router(auth.router)
    app.include_router(dashboard.router)
    app.include_router(usage.router)
    app.include_router(cashback.router)
    app.include_router(insights.router)
    app.include_router(settings.router)

    return app


app = create_app()
