"""HTTP client for Mercury FastAPI.

Default: ``POST {base_url}/v1/mercury/invoke`` with a **flat** JSON body (Mercury E2E shape).

Each request sends ``X-Request-ID`` (UUID) unless disabled. When ``idempotency_key`` is passed,
the client sets header ``Idempotency-Key`` and ``idempotency_key`` on the payload root (flat mode)
or inner dict (nested mode).

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

import asyncio
import json
import logging
import uuid
from typing import Any, Literal, Protocol, runtime_checkable

import httpx
from langsmith import traceable
from pydantic import ValidationError

from mercury.graph.runtime import GraphRuntime
from mercury.invoke import get_invoke_guide_markdown, invoke_mercury
from mercury.service.errors import GraphInvocationError
from mercury.service.models import MercuryInvokeRequest, MercuryInvokeResponse

from juno.assistants.protocol import (
    AssistantTurnAgentError,
    AssistantTurnHttpError,
    AssistantTurnResult,
    parse_mercury_body,
)

logger = logging.getLogger(__name__)

# Matches Mercury FastAPI ``GET /v1/mercury/invoke/guide`` (see ``mercury.service.api``).
_LOCAL_INVOKE_GUIDE_PATH = "/v1/mercury/invoke/guide"


@runtime_checkable
class MercuryAssistantRunnerLike(Protocol):
    """Minimal surface used by ``build_mercury_subagent``."""

    def fetch_get_text(self, relative_path: str) -> str: ...

    def run_turn(
        self,
        payload: dict[str, Any],
        *,
        idempotency_key: str | None = None,
    ) -> AssistantTurnResult: ...


def _response_to_result(response: httpx.Response) -> AssistantTurnResult:
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


def _json_body_for_request(
    payload: dict[str, Any],
    *,
    idempotency_key: str | None,
    request_body_mode: Literal["flat", "nested_input"],
) -> dict[str, Any]:
    inner = dict(payload)
    if idempotency_key is not None:
        inner.setdefault("idempotency_key", idempotency_key)
    if request_body_mode == "flat":
        return inner
    return {"input": inner}


def _headers(*, idempotency_key: str | None, x_request_id: str | None) -> dict[str, str]:
    h: dict[str, str] = {"Content-Type": "application/json"}
    if idempotency_key is not None:
        h["Idempotency-Key"] = idempotency_key
    if x_request_id:
        h["X-Request-ID"] = x_request_id
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


def _local_response_to_result(response: MercuryInvokeResponse) -> AssistantTurnResult:
    raw = response.model_dump(mode="json")
    error = raw.get("error")
    if isinstance(error, dict):
        msg = error.get("message") or raw.get("message") or "Mercury request failed"
        code = error.get("code")
        details = error.get("details")
        return AssistantTurnAgentError(
            message=str(msg),
            code=str(code) if code is not None else None,
            details=details if isinstance(details, dict) else None,
        )
    status = raw.get("status")
    if status in {"failed", "rejected"}:
        msg = raw.get("message") or "Mercury request failed"
        return AssistantTurnAgentError(message=str(msg), code=str(status))
    return parse_mercury_body(raw)


class MercuryAssistantRunner:
    """Sync/async runner for Mercury HTTP (configurable path and body shape)."""

    def __init__(
        self,
        base_url: str,
        *,
        timeout_s: float = 60.0,
        transport: httpx.BaseTransport | None = None,
        http_path: str = "/v1/mercury/invoke",
        request_body_mode: Literal["flat", "nested_input"] = "flat",
        send_x_request_id: bool = True,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        path = http_path.strip()
        if not path.startswith("/"):
            path = "/" + path
        self._http_path = path
        self._request_body_mode = request_body_mode
        self._send_x_request_id = send_x_request_id
        self.timeout_s = timeout_s
        self._transport = transport

    def fetch_get_text(self, relative_path: str) -> str:
        """GET ``{base_url}{relative_path}`` and return response body as text (for invoke guides).

        Uses the same timeout and optional mock ``transport`` as :meth:`run_turn`.
        Non-success HTTP statuses return a short inline message instead of raising.
        """
        path = relative_path.strip()
        if not path.startswith("/"):
            path = "/" + path
        url = f"{self.base_url}{path}"
        with httpx.Client(timeout=self.timeout_s, transport=self._transport) as client:
            response = client.get(url)
        if response.status_code >= 400:
            return f"(Remote guide unavailable: HTTP {response.status_code})"
        return response.text

    def run_turn(
        self,
        payload: dict[str, Any],
        *,
        idempotency_key: str | None = None,
    ) -> AssistantTurnResult:
        return _traced_mercury_run_turn(self, payload, idempotency_key=idempotency_key)

    def _execute_sync_turn(
        self,
        payload: dict[str, Any],
        *,
        idempotency_key: str | None,
    ) -> AssistantTurnResult:
        url = f"{self.base_url}{self._http_path}"
        body = _json_body_for_request(
            payload,
            idempotency_key=idempotency_key,
            request_body_mode=self._request_body_mode,
        )
        rid = str(uuid.uuid4()) if self._send_x_request_id else None
        headers = _headers(idempotency_key=idempotency_key, x_request_id=rid)
        with httpx.Client(timeout=self.timeout_s, transport=self._transport) as client:
            response = client.post(url, json=body, headers=headers)
        return _response_to_result(response)

    async def arun_turn(
        self,
        payload: dict[str, Any],
        *,
        idempotency_key: str | None = None,
    ) -> AssistantTurnResult:
        url = f"{self.base_url}{self._http_path}"
        body = _json_body_for_request(
            payload,
            idempotency_key=idempotency_key,
            request_body_mode=self._request_body_mode,
        )
        rid = str(uuid.uuid4()) if self._send_x_request_id else None
        headers = _headers(idempotency_key=idempotency_key, x_request_id=rid)
        async with httpx.AsyncClient(timeout=self.timeout_s, transport=self._transport) as client:
            response = await client.post(url, json=body, headers=headers)
        return _response_to_result(response)


class LocalMercuryAssistantRunner:
    """In-process Mercury runner using :func:`mercury.invoke.invoke_mercury`.

    Surface matches :class:`MercuryAssistantRunner`: ``run_turn``, ``arun_turn``, and
    ``fetch_get_text`` for invoke-guide markdown. Intended for local/editable Mercury;
    factory wiring is handled separately.
    """

    def __init__(
        self,
        runtime: GraphRuntime,
        *,
        send_x_request_id: bool = True,
    ) -> None:
        self._runtime = runtime
        self._send_x_request_id = send_x_request_id

    def fetch_get_text(self, relative_path: str) -> str:
        """Return invoke-guide Markdown for the native guide path; otherwise a fixed placeholder.

        Unlike the HTTP runner, there is no GET server; paths other than
        ``/v1/mercury/invoke/guide`` resolve to a deterministic ``(Local guide unavailable:…)``
        message so middleware behavior stays predictable.
        """
        path = relative_path.strip()
        if not path.startswith("/"):
            path = "/" + path
        if path.rstrip("/") == _LOCAL_INVOKE_GUIDE_PATH.rstrip("/"):
            return get_invoke_guide_markdown()
        return f"(Local guide unavailable: unsupported path {path})"

    def run_turn(
        self,
        payload: dict[str, Any],
        *,
        idempotency_key: str | None = None,
    ) -> AssistantTurnResult:
        return _traced_local_mercury_run_turn(self, payload, idempotency_key=idempotency_key)

    def _execute_local_turn(
        self,
        payload: dict[str, Any],
        *,
        idempotency_key: str | None,
    ) -> AssistantTurnResult:
        body = dict(payload)
        if idempotency_key is not None:
            body.setdefault("idempotency_key", idempotency_key)
        try:
            request = MercuryInvokeRequest.model_validate(body)
        except ValidationError as exc:
            return AssistantTurnAgentError(
                message="Mercury request validation failed",
                code="validation_error",
                details={"errors": exc.errors()},
            )
        rid = str(uuid.uuid4()) if self._send_x_request_id else None
        try:
            response = invoke_mercury(
                self._runtime,
                request,
                x_request_id=rid,
                idempotency_key=idempotency_key,
            )
        except GraphInvocationError as exc:
            return AssistantTurnAgentError(
                message=str(exc) if str(exc) else "Mercury graph invocation failed",
                code=GraphInvocationError.error_code,
                details=None,
            )
        except Exception as exc:
            logger.exception("Mercury local invocation failed")
            return AssistantTurnAgentError(
                message="Mercury invocation failed unexpectedly",
                code="internal_error",
                details={"error_type": type(exc).__name__},
            )
        return _local_response_to_result(response)

    async def arun_turn(
        self,
        payload: dict[str, Any],
        *,
        idempotency_key: str | None = None,
    ) -> AssistantTurnResult:
        return await asyncio.to_thread(self.run_turn, payload, idempotency_key=idempotency_key)


@traceable(run_type="tool", name="mercury_http")
def _traced_mercury_run_turn(
    runner: MercuryAssistantRunner,
    payload: dict[str, Any],
    *,
    idempotency_key: str | None = None,
) -> AssistantTurnResult:
    return runner._execute_sync_turn(payload, idempotency_key=idempotency_key)


@traceable(run_type="tool", name="mercury_local")
def _traced_local_mercury_run_turn(
    runner: LocalMercuryAssistantRunner,
    payload: dict[str, Any],
    *,
    idempotency_key: str | None = None,
) -> AssistantTurnResult:
    return runner._execute_local_turn(payload, idempotency_key=idempotency_key)


__all__ = ["LocalMercuryAssistantRunner", "MercuryAssistantRunner", "MercuryAssistantRunnerLike"]
