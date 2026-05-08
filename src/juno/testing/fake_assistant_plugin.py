"""Fake Juno assistant plugin for host integration tests."""

from __future__ import annotations

from unittest.mock import MagicMock

from juno.agents.registry import SubagentSpec
from juno.plugins import JunoPluginContext


def create_stub(ctx: JunoPluginContext) -> tuple[SubagentSpec, ...]:
    _ = ctx
    graph = MagicMock(name="compiled_stub_subagent")
    return (
        SubagentSpec(
            name="stub_agent",
            description="Synthetic assistant for Juno host tests.",
            graph=graph,
            supports_wallet_approval_ui=True,
        ),
    )


__all__ = ["create_stub"]
