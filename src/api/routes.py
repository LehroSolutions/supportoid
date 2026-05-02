"""FastAPI routes for SupportOID v1 with admin endpoints and hardened errors."""

from __future__ import annotations

import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field

from src.app.auth import AuthService, UserContext, get_current_user, require_roles
from src.app.dto import (
    ChatRequest,
    ChatResponse,
    CostSummary,
    FeedbackAck,
    FeedbackRequest,
    KBQualityReport,
    LoginRequest,
    LoginResponse,
    PaginationResponse,
    ProblemDetail,
    StatsReport,
    TraceSummary,
    UserContextDTO,
)
from src.app.service import SupportOIDService


def _service(request: Request) -> SupportOIDService:
    return request.app.state.service


def _auth(request: Request) -> AuthService:
    return request.app.state.auth


def _deprecation_headers(response: Response, successor: str) -> None:
    response.headers["Deprecation"] = "true"
    response.headers["Sunset"] = "2026-12-31"
    response.headers["Link"] = f'<{successor}>; rel="successor-version"'


def _bootstrap_message(auth: AuthService) -> str:
    return auth.bootstrap_hint


def _legacy_actor(request: Request) -> UserContext:
    auth = _auth(request)
    token = request.cookies.get(auth.cookie_name)
    user = auth.get_user(token)
    if user:
        return user
    raise HTTPException(status_code=401, detail="Authentication required")


class SyncRequest(BaseModel):
    limit: int = Field(default=100, ge=1, le=1000)


router = APIRouter(prefix="/api/v1", tags=["supportoid-v1"])
legacy_router = APIRouter(prefix="/api", tags=["supportoid-legacy"])


# ── Auth ──


@router.post("/auth/login", response_model=LoginResponse)
async def login(payload: LoginRequest, response: Response, request: Request):
    auth = _auth(request)
    rl = auth.login_rate_limiter
    rl_stats = rl.stats
    key = payload.username
    response.headers["X-RateLimit-Limit"] = str(rl_stats["max_attempts"])
    response.headers["X-RateLimit-Remaining"] = str(rl.remaining_attempts(key))
    response.headers["X-RateLimit-Reset"] = str(rl_stats["window_seconds"])
    if not auth.has_users:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return LoginResponse(ok=False, message=_bootstrap_message(auth))
    token = auth.login(
        payload.username,
        payload.password,
        user_agent=request.headers.get("User-Agent", ""),
        client_ip=getattr(request.client, "host", "") if request.client else "",
    )
    if not token:
        return LoginResponse(ok=False, message="Invalid credentials")
    response.set_cookie(**auth.session_cookie_kwargs(token))
    user = auth.get_user(token)
    return LoginResponse(
        ok=True,
        user=UserContextDTO(username=user.username, role=user.role),
        message="Login successful",
    )


@router.post("/auth/logout", response_model=LoginResponse)
async def logout(response: Response, request: Request):
    auth = _auth(request)
    token = request.cookies.get(auth.cookie_name)
    if token:
        auth.logout(token)
    response.delete_cookie(**auth.session_cookie_delete_kwargs())
    return LoginResponse(ok=True, message="Logged out")


@router.get("/auth/me", response_model=UserContextDTO)
async def me(user: UserContext = Depends(get_current_user)):
    return UserContextDTO(username=user.username, role=user.role)


# ── Chat ──


@router.post(
    "/chat",
    response_model=ChatResponse,
    dependencies=[Depends(require_roles("admin", "support", "analyst"))],
)
async def chat(
    req: ChatRequest, request: Request, user: UserContext = Depends(get_current_user)
):
    service = _service(request)
    return service.chat(req, actor=user.username)


# ── Feedback ──


@router.post(
    "/feedback",
    response_model=FeedbackAck,
    dependencies=[Depends(require_roles("admin", "support", "analyst"))],
)
async def feedback(req: FeedbackRequest, request: Request):
    service = _service(request)
    return service.record_feedback(req)


# ── Traces ──


@router.get(
    "/traces",
    response_model=PaginationResponse,
    dependencies=[Depends(require_roles("admin", "analyst", "support"))],
)
async def list_traces(
    request: Request,
    response: Response,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    service = _service(request)
    response.headers["X-Request-ID"] = getattr(request.state, "request_id", "")
    return service.list_trace_page(limit=limit, offset=offset)


@router.get(
    "/traces/{session_id}",
    dependencies=[Depends(require_roles("admin", "analyst", "support"))],
)
async def get_trace(session_id: str, request: Request):
    service = _service(request)
    trace = service.get_trace(session_id)
    if not trace:
        raise HTTPException(status_code=404, detail="Trace not found")
    return trace


# ── Stats & Costs ──


@router.get(
    "/stats",
    response_model=StatsReport,
    dependencies=[Depends(require_roles("admin", "analyst"))],
)
async def get_stats(request: Request):
    service = _service(request)
    return service.get_stats_report()


@router.get(
    "/costs",
    response_model=CostSummary,
    dependencies=[Depends(require_roles("admin", "analyst"))],
)
async def get_costs(request: Request, conversation_id: Optional[str] = None):
    service = _service(request)
    return service.get_cost_summary(conversation_id=conversation_id)


# ── KB Quality ──


@router.get(
    "/kb-quality",
    response_model=KBQualityReport,
    dependencies=[Depends(require_roles("admin", "analyst"))],
)
async def kb_quality(request: Request):
    service = _service(request)
    return service.get_kb_quality_report()


# ── Sync & Migrate ──


@router.post(
    "/sync",
    dependencies=[Depends(require_roles("admin"))],
)
async def sync(payload: SyncRequest, request: Request):
    service = _service(request)
    return service.run_sync(limit=payload.limit)


@router.post(
    "/migrate",
    dependencies=[Depends(require_roles("admin"))],
)
async def migrate(request: Request):
    service = _service(request)
    return service.migrate_legacy_data()


@router.get("/intents")
async def list_intents(request: Request):
    service = _service(request)
    classifier = getattr(getattr(service, "orchestrator", None), "classifier", None)
    if classifier is None and hasattr(
        getattr(service, "orchestrator", None), "original"
    ):
        classifier = getattr(service.orchestrator.original, "classifier", None)
    if not classifier:
        return {"intents": []}
    try:
        classes = classifier.pipeline.classes_.tolist()
    except Exception:
        classes = []
    return {"intents": classes}


# ── Health (lightweight) ──


@router.get("/health")
async def health(request: Request):
    auth: AuthService = _auth(request)
    service = _service(request)
    return service.get_health_report(
        auth,
        start_time=getattr(request.app.state, "_start_time", time.time()),
    )


# ── Admin endpoints (new) ──


@router.get(
    "/admin/security/report",
    dependencies=[Depends(require_roles("admin"))],
)
async def admin_security_report(request: Request):
    auth = _auth(request)
    service = _service(request)
    return service.get_security_report(auth)


@router.get(
    "/admin/cache/stats",
    dependencies=[Depends(require_roles("admin"))],
)
async def admin_cache_stats(request: Request):
    service = _service(request)
    return service.get_cache_stats()


@router.post(
    "/admin/cache/clear",
    dependencies=[Depends(require_roles("admin"))],
)
async def admin_cache_clear(request: Request):
    service = _service(request)
    return service.clear_cache()


@router.get(
    "/admin/memory/status",
    dependencies=[Depends(require_roles("admin"))],
)
async def admin_memory_status(request: Request):
    service = _service(request)
    return service.get_memory_status()


@router.post(
    "/admin/memory/cleanup",
    dependencies=[Depends(require_roles("admin"))],
)
async def admin_memory_cleanup(request: Request):
    service = _service(request)
    return service.cleanup_memory()


@router.get(
    "/admin/sessions",
    dependencies=[Depends(require_roles("admin"))],
)
async def admin_sessions(request: Request):
    auth = _auth(request)
    return _service(request).get_sessions_report(auth)


@router.get(
    "/admin/rate-limit",
    dependencies=[Depends(require_roles("admin"))],
)
async def admin_rate_limit(request: Request):
    auth = _auth(request)
    return _service(request).get_rate_limit_report(auth)


@router.get(
    "/admin/tier",
    dependencies=[Depends(require_roles("admin"))],
)
async def admin_tier(request: Request):
    return _service(request).get_tier_report()


# ── Legacy aliases ──


@legacy_router.post("/chat")
async def legacy_chat(req: ChatRequest, request: Request, response: Response):
    _deprecation_headers(response, "/api/v1/chat")
    actor = _legacy_actor(request)
    return _service(request).chat(req, actor=actor.username)


@legacy_router.post("/feedback")
async def legacy_feedback(req: FeedbackRequest, request: Request, response: Response):
    _deprecation_headers(response, "/api/v1/feedback")
    _legacy_actor(request)
    return _service(request).record_feedback(req)


@legacy_router.get("/stats")
async def legacy_stats(request: Request, response: Response):
    _deprecation_headers(response, "/api/v1/stats")
    _legacy_actor(request)
    return _service(request).get_stats_report()


@legacy_router.get("/health")
async def legacy_health(request: Request, response: Response):
    _deprecation_headers(response, "/api/v1/health")
    _legacy_actor(request)
    return await health(request)


@legacy_router.get("/costs")
async def legacy_costs(
    request: Request, response: Response, conversation_id: Optional[str] = None
):
    _deprecation_headers(response, "/api/v1/costs")
    _legacy_actor(request)
    return _service(request).get_cost_summary(conversation_id=conversation_id)


@legacy_router.get("/traces")
async def legacy_traces(
    request: Request,
    response: Response,
    limit: int = Query(default=50, ge=1, le=200),
):
    _deprecation_headers(response, "/api/v1/traces")
    _legacy_actor(request)
    return _service(request).list_trace_page(limit=limit, offset=0)


@legacy_router.get("/kb-quality")
async def legacy_kb_quality(request: Request, response: Response):
    _deprecation_headers(response, "/api/v1/kb-quality")
    _legacy_actor(request)
    return _service(request).get_kb_quality_report()
