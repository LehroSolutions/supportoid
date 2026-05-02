"""SupportOID API package."""

from src.api.agent_routes import router as agent_router
from src.api.routes import legacy_router, router

__all__ = ["router", "legacy_router", "agent_router"]
