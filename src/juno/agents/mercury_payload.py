"""Stringify :class:`AssistantTurnResult` for tool messages back to the model."""

from __future__ import annotations

import json

from juno.assistants.protocol import (
    AssistantTurnAgentError,
    AssistantTurnHttpError,
    AssistantTurnResult,
    AssistantTurnSuccess,
    AssistantTurnWalletApproval,
)


def turn_result_to_tool_text(result: AssistantTurnResult) -> str:
    """Format a Mercury turn result as plain text for the LLM."""
    if isinstance(result, AssistantTurnSuccess):
        if result.agent_reply:
            return result.agent_reply
        if result.task_result is not None:
            return json.dumps(result.task_result, default=str)
        return "Success (no reply or task_result)."
    if isinstance(result, AssistantTurnWalletApproval):
        parts = [
            "Wallet approval required.",
            f"approval_token={result.approval_token!r}",
            f"approval_id={result.approval_id!r}",
        ]
        hint_parts: list[str] = []
        if result.extras:
            hint_parts.append(f"details={json.dumps(result.extras, default=str)}")
        hint_parts.append("Ask the user to complete wallet approval before continuing.")
        parts.append(" ".join(hint_parts))
        return "\n".join(parts)
    if isinstance(result, AssistantTurnAgentError):
        line = f"Agent error: {result.message}"
        if result.code:
            line += f" (code={result.code})"
        if result.details:
            line += f" details={json.dumps(result.details, default=str)}"
        return line
    if isinstance(result, AssistantTurnHttpError):
        msg = result.message or f"HTTP {result.status_code}"
        return f"HTTP error {result.status_code}: {msg}\nBody (snippet): {result.body_snippet}"
    return f"Unknown result: {result!r}"


__all__ = ["turn_result_to_tool_text"]
