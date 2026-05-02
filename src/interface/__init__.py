"""Public interface exports for the supported FastAPI web surface."""

from src.interface.web_routes import router as web_router

__all__ = ["web_router"]
