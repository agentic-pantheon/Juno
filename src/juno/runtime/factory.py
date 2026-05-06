"""Build the LangGraph supervisor and sub-agents from settings and manifests."""

from __future__ import annotations

import os
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from langgraph.graph.state import CompiledStateGraph

from juno.agents import build_mercury_subagent, build_supervisor, default_mercury_subagent_spec
from juno.agents.registry import SubagentSpec
from juno.assistants.loader import AssistantManifest, discover_assistants
from juno.assistants.mercury_runner import MercuryAssistantRunner
from juno.settings import Settings


@dataclass(frozen=True)
class SupervisorBundle:
    """Compiled supervisor graph plus metadata for transport layers (e.g. approval UI gating)."""

    graph: CompiledStateGraph
    wallet_approval_supervisor_tool_names: frozenset[str]


def resolve_assistant_base_url(manifest: AssistantManifest, settings: Settings) -> str:
    """Prefer ``os.environ[manifest.base_url_env]``, then mercury-specific Settings fallback."""
    env_val = os.environ.get(manifest.base_url_env, "").strip()
    if env_val:
        return env_val.rstrip("/")
    if manifest.runner == "mercury":
        base = settings.mercury_base_url.strip()
        if base:
            return base.rstrip("/")
    raise ValueError(
        f"Assistant {manifest.runner!r} base URL is empty. Set environment variable "
        f"{manifest.base_url_env!r} (or for Mercury, MERCURY_BASE_URL via Settings).",
    )


def build_subagent_specs(settings: Settings) -> list[SubagentSpec]:
    """Dispatch on ``AssistantManifest.runner`` and return one :class:`SubagentSpec` per assistant."""
    assistants_root = (
        settings.juno_assistants_dir if settings.juno_assistants_dir is not None else Path("assistants")
    )
    manifests = discover_assistants(assistants_root)
    mercury_manifest = manifests.get("mercury")
    if mercury_manifest is None:
        raise ValueError(
            f"No mercury assistant manifest under {assistants_root.resolve()}. Add assistants/mercury.yaml.",
        )
    if mercury_manifest.runner != "mercury":
        raise ValueError(
            f"Expected runner 'mercury' for assistants/mercury.yaml, got {mercury_manifest.runner!r}.",
        )
    base_url = resolve_assistant_base_url(mercury_manifest, settings)
    runner = MercuryAssistantRunner(
        base_url,
        http_path=settings.mercury_http_path,
        request_body_mode=settings.mercury_request_body_mode,
    )
    sub = build_mercury_subagent(
        model=settings.openai_model,
        manifest=mercury_manifest,
        runner=runner,
    )
    return [default_mercury_subagent_spec(sub)]


def build_supervisor_bundle(settings: Settings) -> SupervisorBundle:
    """Load manifests, build sub-agents and supervisor once; includes approval-ui metadata."""
    specs = build_subagent_specs(settings)
    graph = build_supervisor(
        model=settings.openai_model,
        subagents=specs,
        supervisor_prompt_path=settings.juno_supervisor_prompt_path,
        long_term_memory_dir=settings.juno_long_term_memory_dir,
    )
    return SupervisorBundle(
        graph=graph,
        wallet_approval_supervisor_tool_names=wallet_approval_supervisor_tool_names(specs),
    )


def build_supervisor_graph(settings: Settings) -> CompiledStateGraph:
    """Load manifests, build sub-agents, and return the checkpointed supervisor graph."""
    return build_supervisor_bundle(settings).graph


def wallet_approval_supervisor_tool_names(specs: Sequence[SubagentSpec]) -> frozenset[str]:
    """Supervisor tool names (``spec.name``) that may trigger wallet approval UI."""
    return frozenset(s.name for s in specs if s.supports_wallet_approval_ui)


__all__ = [
    "SupervisorBundle",
    "build_subagent_specs",
    "build_supervisor_bundle",
    "build_supervisor_graph",
    "resolve_assistant_base_url",
    "wallet_approval_supervisor_tool_names",
]
