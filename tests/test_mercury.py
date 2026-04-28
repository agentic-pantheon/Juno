"""Mercury protocol parsing and HTTP runner."""

import json

import httpx
import pytest

from juno.assistants.mercury_runner import MercuryAssistantRunner
from juno.assistants.protocol import (
    AssistantTurnAgentError,
    AssistantTurnHttpError,
    AssistantTurnSuccess,
    AssistantTurnWalletApproval,
    parse_mercury_body,
)


def test_parse_success_flat() -> None:
    r = parse_mercury_body({"agent_reply": "Hello"})
    assert isinstance(r, AssistantTurnSuccess)
    assert r.agent_reply == "Hello"
    assert r.task_result is None


def test_parse_success_nested_data() -> None:
    r = parse_mercury_body({"data": {"agent_reply": "Nested", "task_result": {"x": 1}}})
    assert isinstance(r, AssistantTurnSuccess)
    assert r.agent_reply == "Nested"
    assert r.task_result == {"x": 1}


def test_parse_wallet_bool() -> None:
    r = parse_mercury_body(
        {"wallet_approval_required": True, "approval_token": "tok_1", "chain": "base"}
    )
    assert isinstance(r, AssistantTurnWalletApproval)
    assert r.approval_token == "tok_1"
    assert r.extras.get("chain") == "base"


def test_parse_wallet_dict() -> None:
    r = parse_mercury_body(
        {
            "wallet_approval_required": {
                "token": "t",
                "expires_at": "2026-01-01T00:00:00Z",
            }
        }
    )
    assert isinstance(r, AssistantTurnWalletApproval)
    assert r.approval_token == "t"
    assert r.extras.get("expires_at") == "2026-01-01T00:00:00Z"


def test_parse_agent_error_dict() -> None:
    r = parse_mercury_body({"agent_error": {"message": "bad", "code": "e1"}})
    assert isinstance(r, AssistantTurnAgentError)
    assert r.message == "bad"
    assert r.code == "e1"


def test_parse_agent_error_str() -> None:
    r = parse_mercury_body({"agent_error": "oops"})
    assert isinstance(r, AssistantTurnAgentError)
    assert r.message == "oops"


def test_parse_empty_wallet_dict_is_success() -> None:
    r = parse_mercury_body({"wallet_approval_required": {}})
    assert isinstance(r, AssistantTurnSuccess)


def test_run_turn_success_and_idempotency() -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={"agent_reply": "ok"})

    runner = MercuryAssistantRunner(
        "https://mercury.test",
        transport=httpx.MockTransport(handler),
    )
    out = runner.run_turn({"messages": []}, idempotency_key="idem-1")
    assert isinstance(out, AssistantTurnSuccess)
    assert out.agent_reply == "ok"
    assert len(captured) == 1
    req = captured[0]
    assert req.headers.get("Idempotency-Key") == "idem-1"
    assert b'"idempotency_key":"idem-1"' in (req.content or b"")


def test_run_turn_body_idempotency_key_not_overwritten() -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={"agent_reply": "x"})

    runner = MercuryAssistantRunner(
        "https://mercury.test",
        transport=httpx.MockTransport(handler),
    )
    runner.run_turn({"idempotency_key": "from-body"}, idempotency_key="from-arg")
    payload = json.loads(captured[0].content.decode())
    assert payload["idempotency_key"] == "from-body"
    assert captured[0].headers.get("Idempotency-Key") == "from-arg"


def test_run_turn_http_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(502, text="bad gateway")

    runner = MercuryAssistantRunner(
        "https://mercury.test",
        transport=httpx.MockTransport(handler),
    )
    out = runner.run_turn({})
    assert isinstance(out, AssistantTurnHttpError)
    assert out.status_code == 502
    assert "bad gateway" in out.body_snippet


@pytest.mark.asyncio
async def test_arun_turn() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"task_result": {"n": 2}})

    runner = MercuryAssistantRunner(
        "https://mercury.test",
        transport=httpx.MockTransport(handler),
    )
    out = await runner.arun_turn({})
    assert isinstance(out, AssistantTurnSuccess)
    assert out.task_result == {"n": 2}
