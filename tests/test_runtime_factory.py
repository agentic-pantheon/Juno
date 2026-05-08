"""Runtime factory: plugin loading and supervisor bundle."""

from __future__ import annotations

from importlib.metadata import EntryPoint
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from juno.plugins import JUNO_ASSISTANTS_ENTRY_GROUP
from juno.runtime.factory import build_subagent_specs, build_supervisor_bundle
from juno.settings import Settings

_REPO_CONFIG = Path(__file__).resolve().parents[1] / "config" / "juno.supervisor.md"


def _stub_ep() -> EntryPoint:
    return EntryPoint(
        name="stub",
        group=JUNO_ASSISTANTS_ENTRY_GROUP,
        value="juno.testing.fake_assistant_plugin:create_stub",
    )


def _eps_mock(entries: list[EntryPoint]) -> MagicMock:
    root = MagicMock()

    def _select(*, group: str) -> tuple[EntryPoint, ...]:
        if group == JUNO_ASSISTANTS_ENTRY_GROUP:
            return tuple(entries)
        return ()

    root.select = _select
    return root


def test_build_subagent_specs_empty_plugins_raises() -> None:
    s = Settings(juno_supervisor_prompt_path=_REPO_CONFIG)
    with patch("juno.plugins.entry_points", return_value=_eps_mock([])):
        with pytest.raises(ValueError, match="No enabled assistant plugins"):
            build_subagent_specs(s)


def test_build_supervisor_bundle_includes_wallet_approval_tool_names() -> None:
    s = Settings(juno_supervisor_prompt_path=_REPO_CONFIG)
    fake_graph = MagicMock(name="compiled_graph")
    with patch("juno.plugins.entry_points", return_value=_eps_mock([_stub_ep()])):
        with patch("juno.runtime.factory.build_supervisor", return_value=fake_graph) as mock_supervisor:
            bundle = build_supervisor_bundle(s)
    assert bundle.graph is fake_graph
    assert bundle.wallet_approval_supervisor_tool_names == frozenset({"stub_agent"})
    assert mock_supervisor.call_args.kwargs.get("checkpointer") is None


def test_build_supervisor_bundle_forwards_injected_checkpointer() -> None:
    s = Settings(juno_supervisor_prompt_path=_REPO_CONFIG)
    fake_graph = MagicMock(name="compiled_graph")
    fake_cp = MagicMock(name="checkpointer")
    with patch("juno.plugins.entry_points", return_value=_eps_mock([_stub_ep()])):
        with patch("juno.runtime.factory.build_supervisor", return_value=fake_graph) as mock_supervisor:
            bundle = build_supervisor_bundle(s, checkpointer=fake_cp)
    assert bundle.graph is fake_graph
    assert mock_supervisor.call_args.kwargs["checkpointer"] is fake_cp
