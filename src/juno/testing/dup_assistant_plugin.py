"""Registers two specs with duplicate tool names (host duplicate detection tests)."""

from __future__ import annotations

from unittest.mock import MagicMock

from juno.agents.registry import SubagentSpec
from juno.plugins import JunoPluginContext


def create_bad(ctx: JunoPluginContext) -> tuple[SubagentSpec, ...]:
    _ = ctx
    g = MagicMock()
    return (
        SubagentSpec(name="dup", description="first", graph=g),
        SubagentSpec(name="dup", description="second", graph=g),
    )


__all__ = ["create_bad"]
