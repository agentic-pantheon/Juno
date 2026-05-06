"""Juno supervisor agent that delegates to specialist sub-agents via tools."""

from __future__ import annotations

import logging
import os
import time
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

from juno.agents.memory import build_long_term_memory_model_middleware, build_update_user_memory_tool
from juno.agents.registry import SubagentSpec
from juno.agents.state import CustomAgentState
from juno.logging_config import get_trace_id

logger = logging.getLogger(__name__)

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


def _message_content_as_str(content: str | list[str | dict[Any, Any]]) -> str:
    if isinstance(content, str):
        return content
    return str(content)


def _final_ai_content(messages: list[BaseMessage]) -> str:
    for m in reversed(messages):
        if isinstance(m, AIMessage):
            return _message_content_as_str(m.content)
    return ""


def _subagent_tools_from_specs(specs: Sequence[SubagentSpec]) -> list[BaseTool]:
    """Build one LangChain tool per subagent spec (stable tool names from ``spec.name``)."""
    tools: list[BaseTool] = []
    seen: set[str] = set()
    for spec in specs:
        if spec.name in seen:
            msg = f"Duplicate subagent tool name: {spec.name!r}"
            raise ValueError(msg)
        seen.add(spec.name)
        tools.append(_create_subagent_tool(spec))
    return tools


def _create_subagent_tool(spec: SubagentSpec) -> BaseTool:
    graph = spec.graph
    keys = spec.state_keys
    resume = spec.resume_instruction

    @tool(spec.name, description=spec.description)
    def _delegate(request: str, runtime: ToolRuntime) -> str:
        tid = get_trace_id()
        preview = request if len(request) <= 200 else request[:200] + "…"
        logger.info(
            "phase=subagent_delegate_start trace_id=%s subagent=%s request_len=%s",
            tid,
            spec.name,
            len(request),
        )
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                "phase=subagent_delegate_preview trace_id=%s subagent=%s preview=%r",
                tid,
                spec.name,
                preview,
            )
        st = runtime.state
        sub_msgs: list[Any] = [HumanMessage(content=request)]
        if resume is not None and st.get("approval_response") is not None:
            sub_msgs.insert(0, SystemMessage(content=resume))
        sub_input: dict[str, Any] = {"messages": sub_msgs}
        for key in keys:
            if key in st and st[key] is not None:
                sub_input[key] = st[key]
        t0 = time.perf_counter()
        try:
            out = graph.invoke(sub_input, runtime.config)
        finally:
            logger.info(
                "phase=subagent_delegate_end trace_id=%s subagent=%s duration_ms=%.1f",
                tid,
                spec.name,
                (time.perf_counter() - t0) * 1000.0,
            )
        msgs = out.get("messages", [])
        return _final_ai_content(msgs)

    return _delegate


def build_supervisor(
    *,
    model: str | BaseChatModel,
    subagents: Sequence[SubagentSpec],
    additional_tools: Sequence[BaseTool] | None = None,
    long_term_memory_dir: Path | None = None,
    supervisor_prompt_path: Path | None = None,
    system_prompt: str | None = None,
    inject_tools_context: bool = True,
) -> CompiledStateGraph:
    """Build the top-level supervisor with checkpointed state and specialist tools.

    Provide one :class:`SubagentSpec` per top-level tool (e.g. ``mercury``).

    If ``system_prompt`` is omitted, the default is loaded from ``supervisor_prompt_path``,
    ``JUNO_SUPERVISOR_PROMPT_PATH``, or ``config/juno.supervisor.md`` under the CWD.

    When ``inject_tools_context`` is True (default), the system prompt is ``base +`` a
    generated section listing each registered tool name and description—so routing rules
    stay with tool docstrings and manifests, not only in the Markdown file.
    """
    if not subagents:
        raise ValueError("subagents must be non-empty.")

    tools = _subagent_tools_from_specs(tuple(subagents))
    extra_tools: list[BaseTool] = list(additional_tools) if additional_tools else []
    memory_middleware: tuple[Any, ...] = ()
    if long_term_memory_dir is not None:
        extra_tools.append(build_update_user_memory_tool(long_term_memory_dir))
        memory_middleware = (build_long_term_memory_model_middleware(long_term_memory_dir),)
    tools.extend(extra_tools)

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
        middleware=memory_middleware,
    )


__all__ = [
    "build_supervisor",
    "compose_supervisor_system_prompt",
    "format_supervisor_tools_context",
    "load_supervisor_system_prompt",
    "resolve_supervisor_prompt_path",
]
