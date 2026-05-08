"""Subagent registration for the supervisor graph."""

from __future__ import annotations

from dataclasses import dataclass

from langgraph.graph.state import CompiledStateGraph


@dataclass(frozen=True)
class SubagentSpec:
    """Declares one supervisor tool that wraps a compiled sub-agent graph."""

    name: str
    description: str
    graph: CompiledStateGraph
    state_keys: tuple[str, ...] = ("user_id", "wallet_id", "chain", "approval_response")
    resume_instruction: str | None = None
    #: When True, Telegram may show inline Approve/Decline for wallet-gated tool output.
    supports_wallet_approval_ui: bool = False


__all__ = ["SubagentSpec"]
