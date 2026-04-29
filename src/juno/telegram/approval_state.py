"""Pending inline approval state stored in ``Application.bot_data``."""

from __future__ import annotations

from typing import Any

_PENDING_APPROVAL_KEY = "pending_approval_by_chat"
_LAST_APPROVAL_TOKEN_KEY = "last_approval_token_by_chat"


def _pending_map(bot_data: dict[str, Any]) -> dict[int, str]:
    return bot_data.setdefault(_PENDING_APPROVAL_KEY, {})


def _token_map(bot_data: dict[str, Any]) -> dict[int, str | None]:
    return bot_data.setdefault(_LAST_APPROVAL_TOKEN_KEY, {})


def pop_pending_approval(bot_data: dict[str, Any], chat_id: int) -> str | None:
    m = _pending_map(bot_data)
    return m.pop(chat_id, None)


def set_pending_approval(bot_data: dict[str, Any], chat_id: int, value: str) -> None:
    _pending_map(bot_data)[chat_id] = value


def get_last_approval_token(bot_data: dict[str, Any], chat_id: int) -> str | None:
    return _token_map(bot_data).get(chat_id)


def set_last_approval_token(bot_data: dict[str, Any], chat_id: int, token: str | None) -> None:
    _token_map(bot_data)[chat_id] = token


def pop_last_approval_token(bot_data: dict[str, Any], chat_id: int) -> str | None:
    return _token_map(bot_data).pop(chat_id, None)


__all__ = [
    "get_last_approval_token",
    "pop_last_approval_token",
    "pop_pending_approval",
    "set_last_approval_token",
    "set_pending_approval",
]
