"""Juno supervisor agent that delegates to the Mercury sub-agent via a tool."""

from __future__ import annotations

from typing import Any

from langchain.agents import create_agent
from langchain.tools import ToolRuntime, tool
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph.state import CompiledStateGraph

from juno.agents.state import CustomAgentState

_DEFAULT_SUPERVISOR_PROMPT = (
    "You are Juno, a supervisor that coordinates user requests. "
    "Delegate Mercury-specific work (assistant backend, tools, wallet flows) "
    "to the Mercury specialist using the mercury tool with a clear, high-level request. "
    "Summarize outcomes for the user."
)


def _message_content_as_str(content: str | list[str | dict[Any, Any]]) -> str:
    if isinstance(content, str):
        return content
    return str(content)


def _final_ai_content(messages: list[BaseMessage]) -> str:
    for m in reversed(messages):
        if isinstance(m, AIMessage):
            return _message_content_as_str(m.content)
    return ""


def build_supervisor(
    *,
    model: str | BaseChatModel,
    mercury_subagent: CompiledStateGraph,
    system_prompt: str | None = None,
) -> CompiledStateGraph:
    """Build the top-level supervisor with checkpointed state and a Mercury tool."""
    prompt = system_prompt if system_prompt is not None else _DEFAULT_SUPERVISOR_PROMPT

    @tool
    def mercury(request: str, runtime: ToolRuntime) -> str:
        """Route a high-level user request to the Mercury specialist assistant.

        Pass the full intent (what the user wants Mercury to do) in ``request``;
        the specialist has tools to call the Mercury HTTP API. Use this whenever
        the user needs Mercury capabilities rather than answering from general knowledge alone.
        """
        st = runtime.state
        sub_input: dict[str, Any] = {"messages": [HumanMessage(content=request)]}
        for key in ("user_id", "wallet_id", "chain", "approval_response"):
            if key in st and st[key] is not None:
                sub_input[key] = st[key]
        out = mercury_subagent.invoke(sub_input, runtime.config)
        msgs = out.get("messages", [])
        return _final_ai_content(msgs)

    return create_agent(
        model=model,
        tools=[mercury],
        system_prompt=prompt,
        checkpointer=InMemorySaver(),
        state_schema=CustomAgentState,
    )


__all__ = ["build_supervisor"]
