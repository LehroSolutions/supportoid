"""Data migration command wrapper."""

from src.app.service import SupportOIDService
from src.config.settings import Settings


def run_command() -> str:
    service = SupportOIDService(Settings.from_env())
    result = service.migrate_legacy_data()
    return str(result)

