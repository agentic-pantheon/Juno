"""Build the LangGraph supervisor and sub-agents from settings and assistant plugins."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph.state import CompiledStateGraph

from juno.agents import build_supervisor
from juno.agents.registry import SubagentSpec
from juno.plugins import load_assistant_specs
from juno.settings import Settings


@dataclass(frozen=True)
class SupervisorBundle:
    """Compiled supervisor graph plus metadata for transport layers (e.g. approval UI gating)."""

    graph: CompiledStateGraph
    wallet_approval_supervisor_tool_names: frozenset[str]


def build_subagent_specs(settings: Settings) -> list[SubagentSpec]:
    """Load assistant sub-agents via ``importlib.metadata`` entry points (``juno.assistants``)."""

    specs = load_assistant_specs(settings)
    if not specs:
        raise ValueError(
            "No enabled assistant plugins found. Install a package that registers setuptools "
            "entry points under the group juno.assistants (for example mercury with "
            "pip install mercury), or adjust JUNO_DISABLED_ASSISTANTS.",
        )
    return specs


def build_supervisor_bundle(
    settings: Settings,
    checkpointer: BaseCheckpointSaver | None = None,
) -> SupervisorBundle:
    """Load plugins, build sub-agents and supervisor once; includes approval-ui metadata."""
    specs = build_subagent_specs(settings)
    graph = build_supervisor(
        model=settings.openai_model,
        subagents=specs,
        supervisor_prompt_path=settings.juno_supervisor_prompt_path,
        long_term_memory_dir=settings.juno_long_term_memory_dir,
        checkpointer=checkpointer,
    )
    return SupervisorBundle(
        graph=graph,
        wallet_approval_supervisor_tool_names=wallet_approval_supervisor_tool_names(specs),
    )


def build_supervisor_graph(settings: Settings) -> CompiledStateGraph:
    """Load plugins, build sub-agents, and return the checkpointed supervisor graph."""
    return build_supervisor_bundle(settings).graph


def wallet_approval_supervisor_tool_names(specs: Sequence[SubagentSpec]) -> frozenset[str]:
    """Supervisor tool names (``spec.name``) that may trigger wallet approval UI."""
    return frozenset(s.name for s in specs if s.supports_wallet_approval_ui)


__all__ = [
    "SupervisorBundle",
    "build_subagent_specs",
    "build_supervisor_bundle",
    "build_supervisor_graph",
    "wallet_approval_supervisor_tool_names",
]
