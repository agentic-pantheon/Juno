"""Per-chat session fields (chain, wallet) stored in ``Application.bot_data``."""

from __future__ import annotations

from typing import Any, TypedDict


class ChatSessionFields(TypedDict):
    wallet_id: str | None
    chain: str | None


def get_chat_session(bot_data: dict[str, Any], chat_id: int) -> ChatSessionFields:
    sessions: dict[int, ChatSessionFields] = bot_data.setdefault("chat_sessions", {})
    if chat_id not in sessions:
        sessions[chat_id] = ChatSessionFields(wallet_id=None, chain=None)
    return sessions[chat_id]


def clear_chat_session(bot_data: dict[str, Any], chat_id: int) -> None:
    sessions: dict[int, ChatSessionFields] = bot_data.setdefault("chat_sessions", {})
    sessions[chat_id] = ChatSessionFields(wallet_id=None, chain=None)
