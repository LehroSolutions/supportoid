"""SupportOID main entrypoint: FastAPI app factory + serve command."""

from __future__ import annotations

import logging
import secrets
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from src.api.agent_routes import router as agent_router
from src.api.routes import legacy_router, router as api_router
from src.app.automation import AutomationService
from src.app.automation_store import AutomationStore
from src.app.auth import AuthService
from src.app.service import SupportOIDService
from src.config.settings import Settings
from src.interface.web_routes import router as web_router, FRONTEND_DIST

logger = logging.getLogger("supportoid")


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state._start_time = time.time()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    logger.info("SupportOID starting up")
    yield
    logger.info("SupportOID shutting down gracefully")


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or Settings.from_env()

    app = FastAPI(
        title="SupportOID",
        version="10.0",
        description="Production-ready support orchestration platform",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=app_settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def security_headers_middleware(request: Request, call_next):
        response = await call_next(request)
        nonce = getattr(request.state, "csp_nonce", "")
        script_nonce = f" 'nonce-{nonce}'" if nonce else ""
        csp = (
            f"default-src 'self'; "
            f"script-src 'self'{script_nonce}; "
            f"style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            f"font-src 'self' https://fonts.gstatic.com; "
            f"img-src 'self' data:; "
            f"connect-src 'self'; "
            f"frame-ancestors 'none'; "
            f"base-uri 'self'; "
            f"form-action 'self'"
        )
        response.headers["Content-Security-Policy"] = csp
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=()"
        )
        return response

    @app.middleware("http")
    async def csrf_middleware(request: Request, call_next):
        csrf_cookie = request.cookies.get("csrf_token")
        if not csrf_cookie:
            csrf_cookie = secrets.token_hex(32)
        request.state.csrf_token = csrf_cookie

        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            if request.url.path.startswith("/api/"):
                has_origin = bool(
                    request.headers.get("Origin") or request.headers.get("Referer")
                )
                if has_origin and csrf_cookie:
                    header_token = request.headers.get("X-CSRF-Token")
                    if not header_token or header_token != csrf_cookie:
                        return JSONResponse(
                            status_code=403,
                            content={
                                "type": "https://supportoid.dev/errors/csrf",
                                "title": "CSRF validation failed",
                                "status": 403,
                                "detail": "Missing or invalid CSRF token",
                            },
                        )

        response = await call_next(request)
        response.set_cookie(
            key="csrf_token",
            value=csrf_cookie,
            httponly=False,
            samesite="lax",
            secure=app_settings.deployment_profile == "production",
            max_age=12 * 60 * 60,
            path="/",
        )
        return response

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        request.state.request_id = request_id
        start = time.monotonic()
        response = await call_next(request)
        duration_ms = round((time.monotonic() - start) * 1000, 1)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Response-Time-ms"] = str(duration_ms)
        return response

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        request_id = getattr(request.state, "request_id", "unknown")
        logger.error("Unhandled exception: %s [request_id=%s]", exc, request_id)
        return JSONResponse(
            status_code=500,
            content={
                "type": "https://supportoid.dev/errors/internal",
                "title": "Internal Server Error",
                "status": 500,
                "detail": "An unexpected error occurred.",
                "request_id": request_id,
            },
            media_type="application/problem+json",
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        request_id = getattr(request.state, "request_id", "unknown")
        if isinstance(exc.detail, dict):
            payload = dict(exc.detail)
            payload.setdefault("status", exc.status_code)
            payload.setdefault(
                "type",
                f"https://supportoid.dev/errors/{exc.status_code}",
            )
            payload.setdefault("request_id", request_id)
            return JSONResponse(
                status_code=exc.status_code,
                content=payload,
                media_type="application/problem+json",
            )
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "type": f"https://supportoid.dev/errors/{exc.status_code}",
                "title": exc.detail if isinstance(exc.detail, str) else "Error",
                "status": exc.status_code,
                "detail": exc.detail
                if isinstance(exc.detail, str)
                else str(exc.detail),
                "request_id": request_id,
            },
            media_type="application/problem+json",
        )

    @app.exception_handler(RequestValidationError)
    async def request_validation_handler(
        request: Request, exc: RequestValidationError
    ):
        request_id = getattr(request.state, "request_id", "unknown")
        return JSONResponse(
            status_code=422,
            content={
                "type": "https://supportoid.dev/errors/validation",
                "title": "Validation failed",
                "status": 422,
                "detail": "Request validation failed",
                "errors": exc.errors(),
                "request_id": request_id,
            },
            media_type="application/problem+json",
        )

    app.state.settings = app_settings
    app.state.automation_store = AutomationStore(app_settings.sqlite_path)
    app.state.service = SupportOIDService(app_settings)
    app.state.auth = AuthService(
        users=app_settings.auth_users,
        session_ttl_seconds=app_settings.session_ttl_seconds,
        cookie_name=app_settings.session_cookie_name,
        secure_cookies=app_settings.deployment_profile == "production",
        automation_store=app.state.automation_store,
        agent_token_ttl_seconds=app_settings.agent_token_ttl_seconds,
        allow_password_fallback=app_settings.deployment_profile == "test",
    )
    app.state.automation = AutomationService(
        service=app.state.service,
        auth=app.state.auth,
        store=app.state.automation_store,
        start_time_provider=lambda: getattr(app.state, "_start_time", time.time()),
    )

    app.include_router(web_router)
    app.include_router(api_router)
    app.include_router(agent_router)
    app.include_router(legacy_router)

    if FRONTEND_DIST.exists():
        app.mount(
            "/assets",
            StaticFiles(directory=str(FRONTEND_DIST / "assets")),
            name="assets",
        )

    @app.get("/{full_path:path}")
    async def serve_spa_catchall(request: Request, full_path: str):
        if full_path.startswith("api/") or full_path.startswith("login"):
            return None
        index_path = FRONTEND_DIST / "index.html"
        if index_path.exists():
            return FileResponse(str(index_path))
        return None

    return app


def run() -> None:
    import uvicorn

    settings = Settings.from_env()
    uvicorn.run(
        "src.main:create_app",
        host=settings.host,
        port=settings.port,
        factory=True,
        reload=False,
    )


if __name__ == "__main__":
    run()
