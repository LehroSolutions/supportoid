from __future__ import annotations

import shutil
import secrets
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolate_runtime_defaults(tmp_path, monkeypatch):
    """Legacy Settings() fixtures must never write into a developer's runtime data."""
    from src.config.settings import Settings

    original_init = Settings.__init__
    paths = {
        "model_dir": "models", "kb_dir": "knowledge", "feedback_dir": "feedback",
        "training_dir": "training", "cost_dir": "costs", "trace_dir": "traces",
        "sqlite_path": "app.db",
    }

    def isolated_init(settings, *args, **kwargs):
        original_init(settings, *args, **kwargs)
        for name, relative in paths.items():
            if getattr(settings, name) == getattr(Settings, name):
                setattr(settings, name, str(tmp_path / relative))

    monkeypatch.setattr(Settings, "__init__", isolated_init)
    for name in paths:
        monkeypatch.delenv(f"SUPPORTOID_{name.upper()}", raising=False)


@pytest.fixture()
def tmp_path() -> Path:
    root = Path.cwd() / ".pytest-fixtures"
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"case_{secrets.token_hex(8)}"
    path.mkdir(parents=True, exist_ok=False)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)
