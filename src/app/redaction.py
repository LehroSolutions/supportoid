"""Helpers for redacting secrets and basic PII before persistence."""

from __future__ import annotations

import re
from typing import Any


_SENSITIVE_KEY_RE = re.compile(
    r"(password|passwd|pwd|secret|token|api[_-]?key|authorization|cookie)",
    re.IGNORECASE,
)

_TEXT_REPLACEMENTS: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"),
        "[REDACTED_EMAIL]",
    ),
    (
        re.compile(r"\b(?:\+?\d[\d\s().-]{7,}\d)\b"),
        "[REDACTED_PHONE]",
    ),
    (
        re.compile(r"\b(?:\d[ -]*?){13,19}\b"),
        "[REDACTED_CARD]",
    ),
    (
        re.compile(r"\bBearer\s+[A-Za-z0-9._-]+\b", re.IGNORECASE),
        "Bearer [REDACTED_TOKEN]",
    ),
    (
        re.compile(r"\b(?:sk|pk|rk)_[A-Za-z0-9_-]{16,}\b", re.IGNORECASE),
        "[REDACTED_KEY]",
    ),
    (
        re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}\b"),
        "[REDACTED_GITHUB_TOKEN]",
    ),
]


def redact_text(value: str) -> str:
    text = value
    for pattern, replacement in _TEXT_REPLACEMENTS:
        text = pattern.sub(replacement, text)
    return text


def redact_value(value: Any, key: str | None = None) -> Any:
    if key and _SENSITIVE_KEY_RE.search(key):
        return "[REDACTED]"

    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, list):
        return [redact_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_value(item) for item in value)
    if isinstance(value, dict):
        return {
            item_key: redact_value(item_value, key=str(item_key))
            for item_key, item_value in value.items()
        }
    return value
