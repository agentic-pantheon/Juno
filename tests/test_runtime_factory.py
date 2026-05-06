"""Runtime factory: manifests, base URL resolution, supervisor bundle."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from juno.assistants.loader import AssistantManifest
from juno.runtime.factory import (
    build_subagent_specs,
    build_supervisor_bundle,
    resolve_assistant_base_url,
)
from juno.settings import Settings


def test_resolve_assistant_base_url_prefers_manifest_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MERCURY_BASE_URL", "https://from-env.test")
    m = AssistantManifest(runner="mercury", base_url_env="MERCURY_BASE_URL", system_prompt="")
    s = Settings(mercury_base_url="https://from-settings.test")
    assert resolve_assistant_base_url(m, s) == "https://from-env.test"


def test_resolve_assistant_base_url_falls_back_to_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MERCURY_BASE_URL", raising=False)
    m = AssistantManifest(runner="mercury", base_url_env="MERCURY_BASE_URL", system_prompt="")
    s = Settings(mercury_base_url="https://fallback.test")
    assert resolve_assistant_base_url(m, s) == "https://fallback.test"


def test_resolve_assistant_base_url_empty_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MERCURY_BASE_URL", raising=False)
    m = AssistantManifest(runner="mercury", base_url_env="MERCURY_BASE_URL", system_prompt="")
    s = Settings(mercury_base_url="")
    with pytest.raises(ValueError, match="base URL"):
        resolve_assistant_base_url(m, s)


def test_build_subagent_specs_requires_mercury_yaml(tmp_path) -> None:
    s = Settings(
        mercury_base_url="https://m.test",
        juno_assistants_dir=tmp_path,
    )
    with pytest.raises(ValueError, match="mercury"):
        build_subagent_specs(s)


def test_build_supervisor_bundle_includes_wallet_approval_tool_names(tmp_path) -> None:
    import shutil

    repo_assistants = Path(__file__).resolve().parents[1] / "assistants"
    shutil.copytree(repo_assistants, tmp_path / "assistants")
    s = Settings(
        mercury_base_url="https://m.test",
        juno_assistants_dir=tmp_path / "assistants",
        juno_supervisor_prompt_path=Path(__file__).resolve().parents[1] / "config" / "juno.supervisor.md",
    )
    fake_graph = MagicMock(name="compiled_graph")
    with patch("juno.runtime.factory.build_mercury_subagent") as mock_build:
        mock_build.return_value = MagicMock(name="subagent")
        with patch("juno.runtime.factory.build_supervisor", return_value=fake_graph):
            bundle = build_supervisor_bundle(s)
    assert bundle.graph is fake_graph
    assert bundle.wallet_approval_supervisor_tool_names == frozenset({"mercury"})


def test_build_supervisor_bundle_resolves_agent_model_once(tmp_path) -> None:
    import shutil

    repo_assistants = Path(__file__).resolve().parents[1] / "assistants"
    shutil.copytree(repo_assistants, tmp_path / "assistants")
    s = Settings(
        mercury_base_url="https://m.test",
        juno_assistants_dir=tmp_path / "assistants",
        juno_supervisor_prompt_path=Path(__file__).resolve().parents[1] / "config" / "juno.supervisor.md",
    )
    sentinel = object()
    fake_graph = MagicMock(name="compiled_graph")
    with patch("juno.runtime.factory.build_agent_chat_model", return_value=sentinel) as mock_model:
        with patch("juno.runtime.factory.build_mercury_subagent") as mock_sub:
            mock_sub.return_value = MagicMock(name="subagent")
            with patch("juno.runtime.factory.build_supervisor", return_value=fake_graph) as mock_sup:
                build_supervisor_bundle(s)
    mock_model.assert_called_once_with(s)
    assert mock_sub.call_args.kwargs["model"] is sentinel
    assert mock_sup.call_args.kwargs["model"] is sentinel
