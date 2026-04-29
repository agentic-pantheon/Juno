"""Format exceptions for safe, short user-facing messages."""

from __future__ import annotations

import re

# Patterns that might appear in upstream errors (do not echo raw secrets).
_REDACT_PATTERNS = (
    re.compile(r"gsk_[A-Za-z0-9_-]+", re.I),
    re.compile(r"sk-[A-Za-z0-9_-]+", re.I),
    re.compile(r"api[_-]?key[\"']?\s*[:=]\s*[\"']?[\w-]+", re.I),
)


def format_agent_error(exc: BaseException, *, max_len: int = 320) -> str:
    """Return a short message for Telegram: exception type + redacted message body."""
    name = type(exc).__name__
    msg = str(exc).strip() or "(no message)"
    for pat in _REDACT_PATTERNS:
        msg = pat.sub("[redacted]", msg)
    if len(msg) > max_len:
        msg = msg[: max_len - 1] + "…"
    return f"Request failed ({name}): {msg}"
