"""Pydantic models for Mercury `/v1/agent` JSON responses.

Mercury is assumed to return a JSON object. Shapes may be flat or partially nested
under ``data``. The runner merges top-level keys with ``data`` (later wins on conflict)
before interpreting fields.

**Assumed success examples (flat):**

.. code-block:: json

    {"agent_reply": "Here is the answer."}

.. code-block:: json

    {"task_result": {"status": "completed", "items": [1, 2]}}

.. code-block:: json

    {
      "agent_reply": "Task finished.",
      "task_result": {"summary": "ok"}
    }

**Nested under ``data``:**

.. code-block:: json

    {"data": {"agent_reply": "Nested reply"}}

**Wallet approval:**

.. code-block:: json

    {
      "wallet_approval_required": true,
      "approval_token": "tok_abc",
      "approval_id": "apr_123"
    }

.. code-block:: json

    {
      "wallet_approval_required": {
        "token": "tok_abc",
        "expires_at": "2026-01-01T00:00:00Z"
      }
    }

**Agent-level error (semantic, not HTTP):**

.. code-block:: json

    {"agent_error": {"message": "Tool failed", "code": "tool_error"}}

.. code-block:: json

    {"agent_error": "Something went wrong"}
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Result variants (discriminated by ``kind``)
# ---------------------------------------------------------------------------


class AssistantTurnSuccess(BaseModel):
    """Terminal success: optional user-facing text and/or structured task output."""

    kind: Literal["success"] = "success"
    agent_reply: str | None = None
    task_result: dict[str, Any] | None = None


class AssistantTurnWalletApproval(BaseModel):
    """Mercury indicates the user must approve a wallet action."""

    kind: Literal["wallet_approval_required"] = "wallet_approval_required"
    approval_token: str | None = None
    approval_id: str | None = None
    #: Any additional fields from Mercury (e.g. amounts, chain, expiry).
    extras: dict[str, Any] = Field(default_factory=dict)


class AssistantTurnAgentError(BaseModel):
    """Error reported by the agent service in the JSON body."""

    kind: Literal["agent_error"] = "agent_error"
    message: str
    code: str | None = None
    details: dict[str, Any] | None = None


class AssistantTurnHttpError(BaseModel):
    """Non-success HTTP status from the Mercury endpoint."""

    kind: Literal["http_error"] = "http_error"
    status_code: int
    body_snippet: str
    message: str | None = None


type AssistantTurnResult = (
    AssistantTurnSuccess
    | AssistantTurnWalletApproval
    | AssistantTurnAgentError
    | AssistantTurnHttpError
)


def _merge_mercury_payload(raw: dict[str, Any]) -> dict[str, Any]:
    """Flatten ``data`` into the effective dict for key lookup."""
    out = dict(raw)
    data = out.get("data")
    if isinstance(data, dict):
        merged = {**out, **data}
        merged.pop("data", None)
        return merged
    return out


def parse_mercury_body(raw: dict[str, Any]) -> AssistantTurnResult:
    """Map a parsed JSON object to a discriminated :class:`AssistantTurnResult` variant.

    Precedence: ``wallet_approval_required`` → ``agent_error`` → ``success``
    (with ``agent_reply`` / ``task_result`` taken from the merged payload).
    """
    effective = _merge_mercury_payload(raw)

    wa = effective.get("wallet_approval_required")
    if wa is True:
        known = {"wallet_approval_required", "data"}
        extras = {k: v for k, v in effective.items() if k not in known}
        token = effective.get("approval_token")
        if token is None and isinstance(effective.get("token"), str):
            token = effective.get("token")
        aid = effective.get("approval_id")
        if aid is None and isinstance(effective.get("id"), str):
            aid = effective.get("id")
        return AssistantTurnWalletApproval(
            approval_token=token if isinstance(token, str) else None,
            approval_id=aid if isinstance(aid, str) else None,
            extras=extras,
        )
    if isinstance(wa, dict) and wa:
        extras = dict(wa)
        token = extras.pop("approval_token", None) or extras.pop("token", None)
        aid = extras.pop("approval_id", None) or extras.pop("id", None)
        if not isinstance(token, str):
            token = None
        if not isinstance(aid, str):
            aid = None
        return AssistantTurnWalletApproval(
            approval_token=token,
            approval_id=aid,
            extras=extras,
        )

    ae = effective.get("agent_error")
    if ae is not None:
        if isinstance(ae, str):
            return AssistantTurnAgentError(message=ae)
        if isinstance(ae, dict):
            msg = ae.get("message")
            if msg is None:
                msg = ae.get("error")
            if msg is None:
                msg = str(ae) if ae else "Unknown agent error"
            else:
                msg = str(msg)
            code = ae.get("code")
            code_s = str(code) if code is not None else None
            detail_keys = {"message", "error", "code"}
            details = {k: v for k, v in ae.items() if k not in detail_keys} or None
            return AssistantTurnAgentError(message=msg, code=code_s, details=details)
        return AssistantTurnAgentError(message=str(ae))

    agent_reply = effective.get("agent_reply")
    if agent_reply is not None and not isinstance(agent_reply, str):
        agent_reply = str(agent_reply)

    task_result = effective.get("task_result")
    if task_result is not None and not isinstance(task_result, dict):
        task_result = {"value": task_result}

    return AssistantTurnSuccess(
        agent_reply=agent_reply if isinstance(agent_reply, str) else None,
        task_result=task_result if isinstance(task_result, dict) else None,
    )


__all__ = [
    "AssistantTurnAgentError",
    "AssistantTurnHttpError",
    "AssistantTurnResult",
    "AssistantTurnSuccess",
    "AssistantTurnWalletApproval",
    "parse_mercury_body",
]
