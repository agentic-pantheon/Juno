"""Inject a remote invoke guide (GET) before the first model call in a sub-agent run."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from langchain.agents.middleware import before_model
from langchain_core.messages import SystemMessage, ToolMessage

from juno.agents.state import CustomAgentState

_GUIDE_MSG_PREFIX = "[juno:remote_invoke_guide]\n"


def build_remote_invoke_guide_middleware(guide_fetch: Callable[[], str]) -> Any:
    """Return ``before_model`` middleware that appends guide text once per invoke (before tools).

    Skips when any :class:`~langchain_core.messages.ToolMessage` is already in state, or when
    the guide was already injected (prefix marker). ``guide_fetch`` performs the HTTP GET (or
    mock); failures are turned into inline error text so the model can still proceed.
    """
    @before_model(state_schema=CustomAgentState, name="inject_remote_invoke_guide")
    def inject_remote_invoke_guide(state: CustomAgentState, runtime: Any) -> dict[str, Any] | None:
        _ = runtime
        msgs = state.get("messages") or []
        if any(isinstance(m, ToolMessage) for m in msgs):
            return None
        for m in msgs:
            if isinstance(m, SystemMessage):
                content = m.content
                if isinstance(content, str) and content.startswith(_GUIDE_MSG_PREFIX):
                    return None
        try:
            body = guide_fetch()
        except Exception as exc:  # noqa: BLE001 - surface any transport/URL failure to the model
            body = f"(Remote guide request failed: {exc})"
        text = f"{_GUIDE_MSG_PREFIX}Remote invoke guide (from server):\n\n{body.strip()}"
        return {"messages": [SystemMessage(content=text)]}

    return inject_remote_invoke_guide


__all__ = ["build_remote_invoke_guide_middleware"]
