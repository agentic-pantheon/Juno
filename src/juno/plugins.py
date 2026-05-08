"""Discover assistant packages via setuptools entry points (group ``juno.assistants``)."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from importlib.metadata import entry_points
from typing import TYPE_CHECKING, TypeAlias

from juno.agents.registry import SubagentSpec

if TYPE_CHECKING:
    from juno.settings import Settings

logger = logging.getLogger(__name__)

JUNO_ASSISTANTS_ENTRY_GROUP = "juno.assistants"


@dataclass(frozen=True)
class JunoPluginContext:
    """Host context passed to assistant plugins — no assistant-specific fields."""

    settings: Settings


AssistantPluginFn: TypeAlias = Callable[[JunoPluginContext], Sequence[SubagentSpec]]


def parse_disabled_plugin_names(raw: str) -> frozenset[str]:
    """Parse ``JUNO_DISABLED_ASSISTANTS`` (comma-separated entry-point names, ``#`` comments allowed)."""

    names: list[str] = []
    for part in raw.split(","):
        s = part.split("#", 1)[0].strip()
        if s:
            names.append(s.casefold())
    return frozenset(names)


def _normalize_plugin_specs(result: Iterable[SubagentSpec] | SubagentSpec) -> tuple[SubagentSpec, ...]:
    if isinstance(result, SubagentSpec):
        return (result,)
    return tuple(result)


def load_assistant_specs(settings: Settings) -> list[SubagentSpec]:
    """Load all enabled assistant plugins from entry points ``juno.assistants``.

    Skips plugins whose entry-point names are listed in ``settings.juno_disabled_assistants``.
    Duplicate :class:`~juno.agents.registry.SubagentSpec` tool names raise ``ValueError``.
    """

    disabled = parse_disabled_plugin_names(getattr(settings, "juno_disabled_assistants", ""))
    try:
        eps = entry_points().select(group=JUNO_ASSISTANTS_ENTRY_GROUP)
    except Exception:
        eps = ()

    sorted_eps = sorted(eps, key=lambda e: e.name)

    ctx = JunoPluginContext(settings=settings)
    specs: list[SubagentSpec] = []
    seen_tools: dict[str, str] = {}

    for ep in sorted_eps:
        plug_name = ep.name.casefold()
        if plug_name in disabled:
            logger.debug("Skipping disabled assistant plugin %r", ep.name)
            continue
        try:
            factory = ep.load()
        except Exception:
            logger.exception("Failed to load juno assistant entry point %r", ep.name)
            raise
        if not callable(factory):
            raise TypeError(f"Entry point {ep.name!r} must be callable; got {type(factory)}")
        result = factory(ctx)
        for spec in _normalize_plugin_specs(result):
            dup_from = seen_tools.get(spec.name)
            if dup_from is not None:
                raise ValueError(
                    f"Duplicate subagent tool name {spec.name!r}: from plugins {dup_from!r} and {ep.name!r}",
                )
            seen_tools[spec.name] = ep.name
            specs.append(spec)

    return specs


__all__ = [
    "AssistantPluginFn",
    "JUNO_ASSISTANTS_ENTRY_GROUP",
    "JunoPluginContext",
    "load_assistant_specs",
    "parse_disabled_plugin_names",
]
