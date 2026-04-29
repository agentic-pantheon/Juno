"""Juno supervisor agent that delegates to the Mercury sub-agent via a tool."""

from __future__ import annotations

import os
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from langchain.agents import create_agent
from langchain.tools import ToolRuntime, tool
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.tools import BaseTool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph.state import CompiledStateGraph

from juno.agents.state import CustomAgentState

_ENV_SUPERVISOR_PROMPT_PATH = "JUNO_SUPERVISOR_PROMPT_PATH"
_DEFAULT_SUPERVISOR_PROMPT_REL = Path("config") / "juno.supervisor.md"


def resolve_supervisor_prompt_path(explicit: Path | None) -> Path:
    """Resolve path to the supervisor Markdown prompt (matches identity-style resolution)."""
    if explicit is not None:
        return explicit.expanduser().resolve()
    env = os.environ.get(_ENV_SUPERVISOR_PROMPT_PATH)
    if env:
        return Path(env).expanduser().resolve()
    return (Path.cwd() / _DEFAULT_SUPERVISOR_PROMPT_REL).resolve()


def load_supervisor_system_prompt(prompt_path: Path | None) -> str:
    """Read the default supervisor system prompt from disk (trimmed)."""
    resolved = resolve_supervisor_prompt_path(prompt_path)
    if not resolved.is_file():
        raise FileNotFoundError(
            f"Supervisor system prompt not found: {resolved}. "
            f"Set {_ENV_SUPERVISOR_PROMPT_PATH}, pass juno_supervisor_prompt_path in Settings, "
            f"or add {_DEFAULT_SUPERVISOR_PROMPT_REL.as_posix()} under the process working directory.",
        )
    return resolved.read_text(encoding="utf-8").strip()


def format_supervisor_tools_context(tools: Sequence[BaseTool]) -> str:
    """Build a Markdown block describing registered tools (names + descriptions from the tool objects)."""
    if not tools:
        return "## Tools available to you\n\n*(No tools registered.)*"
    lines: list[str] = [
        "## Tools available to you",
        "",
        "Registered for this deployment—you can only use these names when calling tools:",
        "",
    ]
    for t in tools:
        name = t.name
        desc = (t.description or "(no description)").strip()
        lines.append(f"### `{name}`")
        lines.append("")
        lines.append(desc)
        lines.append("")
    return "\n".join(lines).rstrip()


def compose_supervisor_system_prompt(base: str, tools: Sequence[BaseTool]) -> str:
    """Join static supervisor markdown with a dynamically generated tool roster."""
    base_stripped = base.strip()
    tool_block = format_supervisor_tools_context(tools)
    return f"{base_stripped}\n\n{tool_block}".strip()


_SUBAGENT_RESUME_AFTER_APPROVAL = (
    "Session already includes `approval_response` from Telegram (human approved). "
    "Call `mercury_invoke` now with `intent_json` that is IDENTICAL to your previous "
    "mercury_invoke for this operation: same `kind`, fields, amounts, addresses, and the "
    "same `idempotency_key` inside the intent as before. Do not substitute a new intent. "
    "Do not describe wallet UI steps; completion is via Mercury HTTP + 1Claw signer."
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
    supervisor_prompt_path: Path | None = None,
    system_prompt: str | None = None,
    inject_tools_context: bool = True,
) -> CompiledStateGraph:
    """Build the top-level supervisor with checkpointed state and a Mercury tool.

    If ``system_prompt`` is omitted, the default is loaded from ``supervisor_prompt_path``,
    ``JUNO_SUPERVISOR_PROMPT_PATH``, or ``config/juno.supervisor.md`` under the CWD.

    When ``inject_tools_context`` is True (default), the system prompt is ``base +`` a
    generated section listing each registered tool name and description—so routing rules
    stay with tool docstrings and manifests, not only in the Markdown file.
    """
    @tool
    def mercury(request: str, runtime: ToolRuntime) -> str:
        """Mercury specialist: real balances, wallets, Base/Ethereum/L2, txs, approvals.

        **When to call:** Any request involving money/crypto, wallets, holdings, named
        chains (e.g. Base, Ethereum, L2), transactions, swaps, transfers, approvals, gas,
        or addresses—or anything that needs live Mercury/backend data.

        Pass the user's goal in one ``request`` string (chain, wallet, tokens if mentioned).
        The Mercury sub-agent turns this into structured ``mercury_invoke`` JSON.

        **Do not call** for generic small talk with no backend data.

        **After Telegram Approve:** If state already contains ``approval_response``, call this
        again immediately with instructions for the specialist to repeat the **same**
        ``mercury_invoke`` intent as before (same ``kind``, fields, ``idempotency_key``)—never
        a new intent for the gated operation.

        Completion is normally a second Mercury HTTP request with approval; prefer that over
        asking the user to use browser wallets unless product docs say otherwise.
        """
        st = runtime.state
        sub_msgs: list[Any] = [HumanMessage(content=request)]
        if st.get("approval_response") is not None:
            sub_msgs.insert(0, SystemMessage(content=_SUBAGENT_RESUME_AFTER_APPROVAL))
        sub_input: dict[str, Any] = {"messages": sub_msgs}
        for key in ("user_id", "wallet_id", "chain", "approval_response"):
            if key in st and st[key] is not None:
                sub_input[key] = st[key]
        out = mercury_subagent.invoke(sub_input, runtime.config)
        msgs = out.get("messages", [])
        return _final_ai_content(msgs)

    tools: list[BaseTool] = [mercury]

    if system_prompt is not None:
        base = system_prompt
    else:
        base = load_supervisor_system_prompt(supervisor_prompt_path)

    if inject_tools_context:
        prompt = compose_supervisor_system_prompt(base, tools)
    else:
        prompt = base.strip()

    return create_agent(
        model=model,
        tools=tools,
        system_prompt=prompt,
        checkpointer=InMemorySaver(),
        state_schema=CustomAgentState,
    )


__all__ = [
    "build_supervisor",
    "compose_supervisor_system_prompt",
    "format_supervisor_tools_context",
    "load_supervisor_system_prompt",
    "resolve_supervisor_prompt_path",
]
