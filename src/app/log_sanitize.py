"""Helpers for making untrusted values safe to embed in log records and headers."""

from __future__ import annotations

import re
from typing import Any

# Terminal escapes first: stripping control characters on their own would leave the
# sequence body ("[31m") behind as harmless-looking text instead of removing it.
_ANSI_ESCAPE_RE = re.compile(
    r"\x1b\]"
    r"[^\x07\x1b]*(?:\x07|\x1b\\)"
    r"|\x1b\[[0-9;?<>=]*[ -/]*[@-~]"
    r"|\x1b[ -/]*[0-~]"
)
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x1f\x7f-\x9f]")


def sanitize_log_value(value: Any, max_length: int = 200) -> str:
    """Return ``value`` as a single-line, escape-free string bounded in length."""
    text = "" if value is None else str(value)
    text = _ANSI_ESCAPE_RE.sub("", text)
    text = _CONTROL_CHARS_RE.sub("", text)
    if len(text) > max_length:
        text = text[: max_length - 3] + "..."
    return text
