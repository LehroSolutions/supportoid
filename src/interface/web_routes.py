"""Server-rendered web routes for SupportOID."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import parse_qs

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from src.app.auth import AuthService, UserContext, get_current_user, require_roles
from src.app.dto import ChatRequest
from src.app.service import SupportOIDService
from src.app.dto import UserContextDTO


templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

router = APIRouter(tags=["web"])

# Serve static files from frontend/dist in production
FRONTEND_DIST = Path(__file__).parent.parent.parent / "frontend" / "dist"


def _service(request: Request) -> SupportOIDService:
    return request.app.state.service


def _auth(request: Request) -> AuthService:
    return request.app.state.auth


@router.get("/api/me", response_model=UserContextDTO)
async def api_me(request: Request, user: UserContext = Depends(get_current_user)):
    """Return current user info for SPA auth."""
    return UserContextDTO(username=user.username, role=user.role)


def serve_spa_or_redirect(redirect_url: str = None):
    """Serve React SPA index.html if it exists, otherwise redirect."""
    index_path = FRONTEND_DIST / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path))
    if redirect_url:
        return RedirectResponse(url=redirect_url, status_code=status.HTTP_302_FOUND)
    return None


@router.get("/", response_class=HTMLResponse)
async def home(request: Request):
    auth = _auth(request)
    token = request.cookies.get(auth.cookie_name)
    if auth.get_user(token):
        return serve_spa_or_redirect("/dashboard")
    return serve_spa_or_redirect("/login")


@router.get("/login")
async def login_page(request: Request, error: str = ""):
    # Serve React SPA if available, fallback to template
    index_path = FRONTEND_DIST / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path))
    auth = _auth(request)
    bootstrap_message = auth.bootstrap_hint if not auth.has_users else ""
    return templates.TemplateResponse(
        "login.html",
        {"request": request, "error": error or bootstrap_message},
    )


@router.post("/login")
async def login_submit(request: Request):
    body = (await request.body()).decode("utf-8")
    parsed = parse_qs(body)
    username = (parsed.get("username") or [""])[0]
    password = (parsed.get("password") or [""])[0]
    auth = _auth(request)
    if not auth.has_users:
        message = auth.bootstrap_hint
        accept_header = request.headers.get("accept", "")
        if "application/json" in accept_header:
            return JSONResponse(
                {"ok": False, "message": message},
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": message},
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    token = auth.login(
        username,
        password,
        user_agent=request.headers.get("User-Agent", ""),
        client_ip=getattr(request.client, "host", "") if request.client else "",
    )
    if not token:
        # Check if request is from SPA (Accepts JSON)
        accept_header = request.headers.get("accept", "")
        if "application/json" in accept_header:
            return JSONResponse(
                {"ok": False, "message": "Invalid credentials"},
                status_code=status.HTTP_401_UNAUTHORIZED,
            )
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Invalid credentials"},
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
    
    # Check if request is from SPA (Accepts JSON)
    accept_header = request.headers.get("accept", "")
    if "application/json" in accept_header:
        user = auth.get_user(token)
        response = JSONResponse({
            "ok": True,
            "user": {"username": user.username, "role": user.role},
            "message": "Login successful"
        })
    else:
        response = RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    
    response.set_cookie(**auth.session_cookie_kwargs(token))
    return response


@router.post("/logout")
async def logout(request: Request):
    auth = _auth(request)
    token = request.cookies.get(auth.cookie_name)
    if token:
        auth.logout(token)
    
    # Check if request is from SPA (Accepts JSON)
    accept_header = request.headers.get("accept", "")
    if "application/json" in accept_header:
        response = JSONResponse({"ok": True, "message": "Logged out"})
    else:
        response = RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    
    response.delete_cookie(**auth.session_cookie_delete_kwargs())
    return response


@router.get("/dashboard")
async def dashboard(request: Request, user: UserContext = Depends(get_current_user)):
    # Serve React SPA if available, fallback to template
    index_path = FRONTEND_DIST / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path))
    service = _service(request)
    stats = service.get_stats_report()
    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request, "user": user, "stats": stats},
    )


@router.get("/chat")
async def chat_console(request: Request, user: UserContext = Depends(get_current_user)):
    # Serve React SPA if available, fallback to template
    index_path = FRONTEND_DIST / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path))
    return templates.TemplateResponse(
        "chat.html",
        {"request": request, "user": user, "result": None, "message": ""},
    )


@router.post("/chat", response_class=HTMLResponse)
async def chat_submit(
    request: Request,
    user: UserContext = Depends(get_current_user),
):
    body = (await request.body()).decode("utf-8")
    parsed = parse_qs(body)
    message = (parsed.get("message") or [""])[0]
    conversation_id = (parsed.get("conversation_id") or [""])[0] or None
    service = _service(request)
    result = service.chat(
        ChatRequest(
            message=message,
            conversation_id=conversation_id,
            user_id=user.username,
        ),
        actor=user,
    )
    return templates.TemplateResponse(
        "chat.html",
        {"request": request, "user": user, "result": result, "message": message},
    )


@router.get("/traces")
async def traces_page(request: Request, user: UserContext = Depends(get_current_user)):
    # Serve React SPA if available, fallback to template
    index_path = FRONTEND_DIST / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path))
    service = _service(request)
    traces = service.list_trace_summaries(limit=100)
    return templates.TemplateResponse(
        "traces.html",
        {"request": request, "user": user, "traces": traces},
    )


@router.get("/kb-quality")
async def kb_quality_page(
    request: Request,
    user: UserContext = Depends(require_roles("admin", "analyst")),
):
    # Serve React SPA if available, fallback to template
    index_path = FRONTEND_DIST / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path))
    service = _service(request)
    report = service.get_kb_quality_report()
    return templates.TemplateResponse(
        "kb_quality.html",
        {"request": request, "user": user, "report": report},
    )


@router.get("/analytics")
async def analytics_page(
    request: Request,
    user: UserContext = Depends(require_roles("admin", "analyst")),
):
    # Serve React SPA if available, fallback to template
    index_path = FRONTEND_DIST / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path))
    service = _service(request)
    stats = service.get_stats_report()
    costs = service.get_cost_summary()
    return templates.TemplateResponse(
        "analytics.html",
        {"request": request, "user": user, "stats": stats, "costs": costs},
    )
