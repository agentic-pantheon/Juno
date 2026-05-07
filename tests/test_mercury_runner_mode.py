"""Settings and factory wiring for ``mercury_runner_mode`` (http vs local)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from juno.assistants.mercury_runner import LocalMercuryAssistantRunner, MercuryAssistantRunner
from juno.runtime import factory as factory_module
from juno.runtime.factory import build_subagent_specs
from juno.settings import Settings


def _copy_assistants(tmp_path: Path) -> Path:
    import shutil

    repo_assistants = Path(__file__).resolve().parents[1] / "assistants"
    dest = tmp_path / "assistants"
    shutil.copytree(repo_assistants, dest)
    return dest


def test_settings_mercury_runner_mode_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MERCURY_RUNNER_MODE", "local")
    s = Settings()
    assert s.mercury_runner_mode == "local"


def test_settings_mercury_runner_mode_juno_alias(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MERCURY_RUNNER_MODE", raising=False)
    monkeypatch.setenv("JUNO_MERCURY_RUNNER_MODE", "local")
    s = Settings()
    assert s.mercury_runner_mode == "local"


def test_build_subagent_specs_http_mode_requires_base_url(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assistants = _copy_assistants(tmp_path)
    monkeypatch.delenv("MERCURY_BASE_URL", raising=False)
    s = Settings(
        mercury_runner_mode="http",
        mercury_base_url="",
        juno_assistants_dir=assistants,
        juno_supervisor_prompt_path=Path(__file__).resolve().parents[1] / "config" / "juno.supervisor.md",
    )
    with pytest.raises(ValueError, match="base URL"):
        build_subagent_specs(s)


def test_build_subagent_specs_local_mode_allows_empty_base_url(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assistants = _copy_assistants(tmp_path)
    monkeypatch.delenv("MERCURY_BASE_URL", raising=False)
    fake_runtime = object()

    def _fake_build_runtime(settings=None):
        assert settings is None
        return fake_runtime

    monkeypatch.setattr(factory_module, "build_mercury_graph_runtime_for_local", _fake_build_runtime)

    captured: dict[str, object] = {}

    def _capture_build(*, model, manifest, runner, **kwargs):
        captured["runner"] = runner
        return MagicMock(name="subagent_graph")

    monkeypatch.setattr(factory_module, "build_mercury_subagent", _capture_build)

    s = Settings(
        mercury_runner_mode="local",
        mercury_base_url="",
        juno_assistants_dir=assistants,
        juno_supervisor_prompt_path=Path(__file__).resolve().parents[1] / "config" / "juno.supervisor.md",
    )
    build_subagent_specs(s)
    runner = captured["runner"]
    assert isinstance(runner, LocalMercuryAssistantRunner)
    assert runner._runtime is fake_runtime  # type: ignore[attr-defined]


def test_build_subagent_specs_http_mode_builds_http_runner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assistants = _copy_assistants(tmp_path)
    monkeypatch.delenv("MERCURY_BASE_URL", raising=False)

    captured: dict[str, object] = {}

    def _capture_build(*, model, manifest, runner, **kwargs):
        captured["runner"] = runner
        return MagicMock(name="subagent_graph")

    monkeypatch.setattr(factory_module, "build_mercury_subagent", _capture_build)

    s = Settings(
        mercury_runner_mode="http",
        mercury_base_url="https://mercury.example",
        juno_assistants_dir=assistants,
        juno_supervisor_prompt_path=Path(__file__).resolve().parents[1] / "config" / "juno.supervisor.md",
    )
    build_subagent_specs(s)
    runner = captured["runner"]
    assert isinstance(runner, MercuryAssistantRunner)
    assert runner.base_url == "https://mercury.example"
