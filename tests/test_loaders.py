"""Tests for identity and assistant manifest loaders."""

from pathlib import Path

import pytest

from juno import AssistantManifest, discover_assistants, load_identity
from juno.agents.build_supervisor import (
    compose_supervisor_system_prompt,
    load_supervisor_system_prompt,
)
from juno.identity import JunoIdentityNotFoundError

_REPO_ROOT = Path(__file__).resolve().parents[1]


def test_load_identity_example() -> None:
    identity = load_identity(_REPO_ROOT / "config" / "juno.identity.yaml.example")
    assert identity.agent_id == "juno_supervisor"
    assert identity.secrets.openai_api_key_env == "OPENAI_API_KEY"


def test_load_identity_missing() -> None:
    with pytest.raises(JunoIdentityNotFoundError):
        load_identity(_REPO_ROOT / "config" / "nonexistent.identity.yaml")


def test_discover_assistants_with_sidecar_markdown(tmp_path: Path) -> None:
    (tmp_path / "alpha.yaml").write_text(
        "runner: custom\nbase_url_env: ALPHA_BASE\nsystem_prompt: ''\n",
        encoding="utf-8",
    )
    (tmp_path / "alpha.md").write_text("# Specialist Alpha\nRuns sample tasks.", encoding="utf-8")
    manifests = discover_assistants(tmp_path)
    assert "alpha" in manifests
    m: AssistantManifest = manifests["alpha"]
    assert m.runner == "custom"
    assert m.base_url_env == "ALPHA_BASE"
    assert m.instructions_md is not None
    assert "Specialist Alpha" in m.instructions_md


def test_load_supervisor_prompt_md() -> None:
    md = _REPO_ROOT / "config" / "juno.supervisor.md"
    text = load_supervisor_system_prompt(md)
    assert "Juno" in text
    assert "## Tools available" not in text  # appended at build time, not in file


def test_compose_supervisor_prompt_includes_tools() -> None:
    from langchain.tools import tool

    @tool
    def mercury(request: str) -> str:
        """Mercury specialist body for tests."""
        return "ok"

    base = load_supervisor_system_prompt(_REPO_ROOT / "config" / "juno.supervisor.md")
    full = compose_supervisor_system_prompt(base, [mercury])
    assert "### `mercury`" in full
    assert "Mercury specialist body" in full
