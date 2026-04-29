"""Custom agent state: session fields for Mercury and Telegram."""

from __future__ import annotations

from typing import Any

from langchain.agents.middleware.types import AgentState
from typing_extensions import NotRequired


class CustomAgentState(AgentState[Any]):
    """Extends :class:`AgentState` with optional session fields for Mercury."""

    user_id: NotRequired[str | None]
    wallet_id: NotRequired[str | None]
    chain: NotRequired[str | None]
    #: Mercury ``approval_response`` object (dict) or Telegram-held string (normalized in tools).
    approval_response: NotRequired[Any]


__all__ = ["CustomAgentState"]
