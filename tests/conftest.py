from __future__ import annotations

import shutil
import secrets
from pathlib import Path

import pytest


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
