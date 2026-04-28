"""Tests for identity and assistant manifest loaders."""

from pathlib import Path

import pytest

from juno import AssistantManifest, discover_assistants, load_identity
from juno.identity import JunoIdentityNotFoundError

_REPO_ROOT = Path(__file__).resolve().parents[1]


def test_load_identity_example() -> None:
    identity = load_identity(_REPO_ROOT / "config" / "juno.identity.yaml.example")
    assert identity.agent_id == "juno_supervisor"
    assert identity.secrets.openai_api_key_env == "OPENAI_API_KEY"


def test_load_identity_missing() -> None:
    with pytest.raises(JunoIdentityNotFoundError):
        load_identity(_REPO_ROOT / "config" / "nonexistent.identity.yaml")


def test_discover_assistants_mercury() -> None:
    manifests = discover_assistants(_REPO_ROOT / "assistants")
    assert "mercury" in manifests
    m: AssistantManifest = manifests["mercury"]
    assert m.runner == "mercury"
    assert m.base_url_env == "MERCURY_BASE_URL"
    assert m.instructions_md is not None
    assert "Mercury" in m.instructions_md
