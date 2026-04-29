"""Pure helpers for Telegram / Mercury message text."""

from __future__ import annotations

import re

# Matches ``approval_token='...'`` from :func:`juno.agents.mercury_payload.turn_result_to_tool_text`.
_APPROVAL_TOKEN_SINGLE = re.compile(r"approval_token='([^']*)'")
_APPROVAL_TOKEN_DOUBLE = re.compile(r'approval_token="([^"]*)"')
_IDEM_KEY_JSON = re.compile(r'"idempotency_key"\s*:\s*"([^"]*)"')
_IDEM_KEY_SNIPPET = re.compile(r"idempotency_key[=:]\s*['\"]([^'\"]+)['\"]")


def extract_approval_token(text: str) -> str | None:
    """Return the Mercury ``approval_token`` value if present in tool/summary text."""
    if not text:
        return None
    m = _APPROVAL_TOKEN_SINGLE.search(text)
    if m:
        return m.group(1)
    m = _APPROVAL_TOKEN_DOUBLE.search(text)
    return m.group(1) if m else None


def extract_idempotency_key(text: str) -> str | None:
    """Return Mercury transaction idempotency key from tool output / JSON snippet."""
    if not text:
        return None
    m = _IDEM_KEY_JSON.search(text)
    if m:
        return m.group(1)
    m = _IDEM_KEY_SNIPPET.search(text)
    return m.group(1) if m else None


def extract_approval_correlation_id(text: str) -> str | None:
    """Prefer idempotency key (value-moving), else approval_token (legacy)."""
    return extract_idempotency_key(text) or extract_approval_token(text)


__all__ = [
    "extract_approval_correlation_id",
    "extract_approval_token",
    "extract_idempotency_key",
]
