"""Juno host: entry-point discovery and plugin disable list."""

from __future__ import annotations

from importlib.metadata import EntryPoint
from unittest.mock import MagicMock, patch

import pytest

from juno.plugins import JUNO_ASSISTANTS_ENTRY_GROUP, parse_disabled_plugin_names
from juno.runtime.factory import build_subagent_specs, build_supervisor_bundle
from juno.settings import Settings

_REPO_CONFIG = __import__("pathlib").Path(__file__).resolve().parents[1] / "config" / "juno.supervisor.md"


def _stub_entry_point() -> EntryPoint:
    return EntryPoint(
        name="stub",
        group=JUNO_ASSISTANTS_ENTRY_GROUP,
        value="juno.testing.fake_assistant_plugin:create_stub",
    )


def _patch_entry_points(entries: list[EntryPoint]) -> object:
    mock_root = MagicMock()

    def _select(*, group: str) -> tuple[EntryPoint, ...]:
        if group == JUNO_ASSISTANTS_ENTRY_GROUP:
            return tuple(entries)
        return ()

    mock_root.select = _select
    return mock_root


def test_parse_disabled_plugin_names_handles_comments_and_case() -> None:
    raw = " mercury ,, Other # comment"
    assert parse_disabled_plugin_names(raw) == frozenset({"mercury", "other"})


def test_build_subagent_specs_no_plugins_raises() -> None:
    s = Settings(juno_supervisor_prompt_path=_REPO_CONFIG)
    with patch("juno.plugins.entry_points", return_value=_patch_entry_points([])):
        with pytest.raises(ValueError, match="No enabled assistant plugins"):
            build_subagent_specs(s)


def test_build_subagent_specs_respects_disabled_case_insensitive() -> None:
    s = Settings(juno_supervisor_prompt_path=_REPO_CONFIG, juno_disabled_assistants="Stub")
    with patch("juno.plugins.entry_points", return_value=_patch_entry_points([_stub_entry_point()])):
        with pytest.raises(ValueError, match="No enabled assistant plugins"):
            build_subagent_specs(s)


def test_duplicate_subagent_names_within_one_plugin_raise() -> None:
    dup_ep = EntryPoint(
        name="bad",
        group=JUNO_ASSISTANTS_ENTRY_GROUP,
        value="juno.testing.dup_assistant_plugin:create_bad",
    )
    with patch("juno.plugins.entry_points", return_value=_patch_entry_points([dup_ep])):
        s = Settings(juno_supervisor_prompt_path=_REPO_CONFIG)
        with pytest.raises(ValueError, match="Duplicate subagent tool name"):
            build_subagent_specs(s)


def test_build_supervisor_bundle_with_stub_plugin() -> None:
    s = Settings(juno_supervisor_prompt_path=_REPO_CONFIG)
    fake_graph = MagicMock(name="supervisor_graph")
    with patch("juno.plugins.entry_points", return_value=_patch_entry_points([_stub_entry_point()])):
        with patch("juno.runtime.factory.build_supervisor", return_value=fake_graph) as mock_sup:
            bundle = build_supervisor_bundle(s)
    assert bundle.graph is fake_graph
    assert bundle.wallet_approval_supervisor_tool_names == frozenset({"stub_agent"})
    assert mock_sup.call_args.kwargs["subagents"][0].name == "stub_agent"
