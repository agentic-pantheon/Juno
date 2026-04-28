"""HTTP client for Mercury FastAPI: ``POST {base_url}/v1/agent``.

**Request:** JSON object (your turn payload). When ``idempotency_key`` is passed to
:meth:`MercuryAssistantRunner.run_turn` / :meth:`MercuryAssistantRunner.arun_turn`,
the client sends header ``Idempotency-Key`` and sets body field ``idempotency_key``
only if that key is not already present in the payload.

**Successful JSON examples** (see :mod:`juno.assistants.protocol` for full assumed shapes):

.. code-block:: json

    {"agent_reply": "Done."}

.. code-block:: json

    {"data": {"task_result": {"ok": true}}}

**Error responses:** HTTP 4xx/5xx are returned as :class:`AssistantTurnHttpError`
(with a short text snippet of the body). Invalid JSON on 200 is returned as
:class:`AssistantTurnAgentError` with ``code="invalid_json"``.
"""

from __future__ import annotations

import json
from typing import Any

import httpx

from juno.assistants.protocol import (
    AssistantTurnAgentError,
    AssistantTurnHttpError,
    AssistantTurnResult,
    parse_mercury_body,
)

_AGENT_PATH = "/v1/agent"


def _json_body_for_request(
    payload: dict[str, Any],
    *,
    idempotency_key: str | None,
) -> dict[str, Any]:
    body = dict(payload)
    if idempotency_key is not None:
        body.setdefault("idempotency_key", idempotency_key)
    return body


def _headers(*, idempotency_key: str | None) -> dict[str, str]:
    h: dict[str, str] = {"Content-Type": "application/json"}
    if idempotency_key is not None:
        h["Idempotency-Key"] = idempotency_key
    return h


def _body_snippet(text: str, max_len: int = 2000) -> str:
    text = text.strip()
    if len(text) <= max_len:
        return text
    return text[:max_len] + "…"


def _map_http_error(response: httpx.Response) -> AssistantTurnHttpError:
    return AssistantTurnHttpError(
        status_code=response.status_code,
        body_snippet=_body_snippet(response.text),
        message=f"Mercury returned HTTP {response.status_code}",
    )


class MercuryAssistantRunner:
    """Sync/async runner for Mercury ``/v1/agent``."""

    def __init__(
        self,
        base_url: str,
        *,
        timeout_s: float = 60.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s
        self._transport = transport

    def run_turn(
        self,
        payload: dict[str, Any],
        *,
        idempotency_key: str | None = None,
    ) -> AssistantTurnResult:
        url = f"{self.base_url}{_AGENT_PATH}"
        body = _json_body_for_request(payload, idempotency_key=idempotency_key)
        headers = _headers(idempotency_key=idempotency_key)
        with httpx.Client(timeout=self.timeout_s, transport=self._transport) as client:
            response = client.post(url, json=body, headers=headers)
        if response.status_code >= 400:
            return _map_http_error(response)
        try:
            data = response.json()
        except json.JSONDecodeError:
            return AssistantTurnAgentError(
                message="Response body was not valid JSON",
                code="invalid_json",
                details={"body_snippet": _body_snippet(response.text)},
            )
        if not isinstance(data, dict):
            return AssistantTurnAgentError(
                message="Mercury JSON root must be an object",
                code="invalid_shape",
                details={"got_type": type(data).__name__},
            )
        return parse_mercury_body(data)

    async def arun_turn(
        self,
        payload: dict[str, Any],
        *,
        idempotency_key: str | None = None,
    ) -> AssistantTurnResult:
        url = f"{self.base_url}{_AGENT_PATH}"
        body = _json_body_for_request(payload, idempotency_key=idempotency_key)
        headers = _headers(idempotency_key=idempotency_key)
        async with httpx.AsyncClient(timeout=self.timeout_s, transport=self._transport) as client:
            response = await client.post(url, json=body, headers=headers)
        if response.status_code >= 400:
            return _map_http_error(response)
        try:
            data = response.json()
        except json.JSONDecodeError:
            return AssistantTurnAgentError(
                message="Response body was not valid JSON",
                code="invalid_json",
                details={"body_snippet": _body_snippet(response.text)},
            )
        if not isinstance(data, dict):
            return AssistantTurnAgentError(
                message="Mercury JSON root must be an object",
                code="invalid_shape",
                details={"got_type": type(data).__name__},
            )
        return parse_mercury_body(data)


__all__ = ["MercuryAssistantRunner"]
