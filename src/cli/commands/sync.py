"""Convex sync command wrapper."""

from src.app.service import SupportOIDService
from src.config.settings import Settings


def run_command(limit: int = 100) -> str:
    service = SupportOIDService(Settings.from_env())
    result = service.run_sync(limit=limit)
    return str(result)

