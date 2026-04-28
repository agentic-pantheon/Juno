"""LangChain supervisor and Mercury sub-agent graphs."""

from __future__ import annotations

import json
import uuid

import httpx
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, HumanMessage

from juno.agents import build_mercury_subagent, build_supervisor
from juno.assistants.loader import AssistantManifest
from juno.assistants.mercury_runner import MercuryAssistantRunner


class FakeMessagesListChatModelWithTools(FakeMessagesListChatModel):
    """:class:`FakeMessagesListChatModel` does not implement ``bind_tools``; agents require it."""

    def bind_tools(self, tools, *, tool_choice=None, **kwargs):  # type: ignore[no-untyped-def]
        return self


def _thread_config() -> dict:
    return {"configurable": {"thread_id": f"test-{uuid.uuid4()}"}}


def test_supervisor_no_tool_plain_done() -> None:
    model = FakeMessagesListChatModelWithTools(responses=[AIMessage(content="done")])
    manifest = AssistantManifest(runner="mercury", base_url_env="X", system_prompt="S")

    def boom(request: httpx.Request) -> httpx.Response:
        raise AssertionError("Mercury should not be called")

    runner = MercuryAssistantRunner("https://unused.test", transport=httpx.MockTransport(boom))
    sub = build_mercury_subagent(model=model, manifest=manifest, runner=runner)
    sup = build_supervisor(model=model, mercury_subagent=sub)

    out = sup.invoke({"messages": [HumanMessage("hello")]}, _thread_config())
    assert out["messages"][-1].content == "done"


def test_mercury_turn_tool_surfaces_agent_reply() -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={"agent_reply": "Mercury says hi"})

    runner = MercuryAssistantRunner("https://mercury.test", transport=httpx.MockTransport(handler))
    manifest = AssistantManifest(runner="mercury", base_url_env="X", system_prompt="Specialist")

    responses = [
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "mercury_turn",
                    "args": {"mercury_instruction": "greet"},
                    "id": "call-sub-1",
                    "type": "tool_call",
                }
            ],
        ),
        AIMessage(content="wrapped up."),
    ]
    model = FakeMessagesListChatModelWithTools(responses=responses)
    sub = build_mercury_subagent(model=model, manifest=manifest, runner=runner)

    out = sub.invoke({"messages": [HumanMessage("user task")]}, _thread_config())
    tool_contents = [m.content for m in out["messages"] if m.type == "tool"]
    assert any("Mercury says hi" in str(c) for c in tool_contents)
    assert len(captured) == 1
    body = json.loads(captured[0].content.decode())
    assert "messages" in body


def test_supervisor_two_step_mercury_path() -> None:
    sub_responses = [
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "mercury_turn",
                    "args": {"mercury_instruction": "run task"},
                    "id": "call-turn-1",
                    "type": "tool_call",
                }
            ],
        ),
        AIMessage(content="Mercury specialist summarized."),
    ]
    sub_model = FakeMessagesListChatModelWithTools(responses=sub_responses)

    super_responses = [
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "mercury",
                    "args": {"request": "Do the mercury thing"},
                    "id": "call-mercury-1",
                    "type": "tool_call",
                }
            ],
        ),
        AIMessage(content="Supervisor final."),
    ]
    super_model = FakeMessagesListChatModelWithTools(responses=super_responses)

    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={"agent_reply": "API ok"})

    runner = MercuryAssistantRunner("https://mercury.test", transport=httpx.MockTransport(handler))
    manifest = AssistantManifest(runner="mercury", base_url_env="X", system_prompt="Sub sys")

    sub = build_mercury_subagent(model=sub_model, manifest=manifest, runner=runner)
    sup = build_supervisor(model=super_model, mercury_subagent=sub)

    out = sup.invoke(
        {
            "messages": [HumanMessage("Hi")],
            "user_id": "user-1",
            "wallet_id": "w-1",
            "chain": "base",
        },
        _thread_config(),
    )
    assert out["messages"][-1].content == "Supervisor final."
    assert len(captured) == 1
    body = json.loads(captured[0].content.decode())
    assert body.get("user_id") == "user-1"
    assert body.get("wallet_id") == "w-1"
    assert body.get("chain") == "base"
