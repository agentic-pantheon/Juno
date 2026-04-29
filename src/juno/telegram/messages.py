"""LangChain message helpers for Telegram."""

from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, ToolMessage


def msg_content_str(content: str | list[str | dict[str, Any]]) -> str:
    if isinstance(content, str):
        return content
    return str(content)


def final_ai_content(messages: list[BaseMessage]) -> str:
    for m in reversed(messages):
        if isinstance(m, AIMessage):
            return msg_content_str(m.content)
    return ""


def messages_blob_for_approval(messages: list[BaseMessage]) -> str:
    """All model + tool text turns (Mercury results often only appear on ToolMessage)."""
    parts: list[str] = []
    for m in messages:
        if isinstance(m, AIMessage):
            parts.append(msg_content_str(m.content))
        elif isinstance(m, ToolMessage):
            parts.append(str(m.content))
        elif getattr(m, "type", None) == "tool":
            parts.append(str(m.content))
    return "\n".join(parts)


__all__ = ["final_ai_content", "messages_blob_for_approval", "msg_content_str"]
