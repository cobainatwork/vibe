"""FastAPI app for gateway: auth middleware + route wiring."""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from shared.auth import AuthError, verify_api_key
from shared.config import Config, load_config
from shared.db import connect, run_migrations

from gateway.rest_health import router as health_router
from gateway.rest_hotwords import router as hotwords_router
from gateway.rest_jobs import router as jobs_router
from gateway.rest_models import router as models_router
from gateway.ws_transcribe import router as ws_router


def create_app() -> FastAPI:
    cfg = load_config()
    app = FastAPI(title="VibeVoice Client")
    app.state.config = cfg

    # Migrate DB on startup
    conn = connect(cfg.db_path)
    run_migrations(conn)
    app.state.db = conn

    @app.middleware("http")
    async def auth_middleware(request: Request, call_next):
        try:
            verify_api_key(request.headers.get("x-api-key"), cfg.api_keys)
        except AuthError as e:
            return JSONResponse(
                {"error": "AUTH_FAIL", "detail": str(e)},
                status_code=401,
            )
        return await call_next(request)

    # Routes
    app.include_router(health_router, prefix="/v1")
    app.include_router(models_router, prefix="/v1")
    app.include_router(hotwords_router, prefix="/v1")
    app.include_router(jobs_router, prefix="/v1")
    # WS endpoint — auth is inline in handler (HTTP middleware does not apply)
    app.include_router(ws_router, prefix="/v1")
    return app
