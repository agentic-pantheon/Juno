"""Pure helpers for Telegram / Mercury message text."""

from __future__ import annotations

import re

# Matches ``approval_token='...'`` from :func:`juno.agents.mercury_payload.turn_result_to_tool_text`.
_APPROVAL_TOKEN_SINGLE = re.compile(r"approval_token='([^']*)'")
_APPROVAL_TOKEN_DOUBLE = re.compile(r'approval_token="([^"]*)"')


def extract_approval_token(text: str) -> str | None:
    """Return the Mercury ``approval_token`` value if present in tool/summary text."""
    if not text:
        return None
    m = _APPROVAL_TOKEN_SINGLE.search(text)
    if m:
        return m.group(1)
    m = _APPROVAL_TOKEN_DOUBLE.search(text)
    return m.group(1) if m else None


__all__ = ["extract_approval_token"]
