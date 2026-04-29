"""Discover and parse ``assistants/*.yaml`` manifests."""

from __future__ import annotations

import os
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, ValidationError

_ENV_ASSISTANTS_DIR = "JUNO_ASSISTANTS_DIR"
_DEFAULT_ASSISTANTS_REL = Path("assistants")


class AssistantManifest(BaseModel):
    """Per-assistant config: runner id, env for HTTP base URL, prompts, requirements."""

    runner: str
    base_url_env: str
    system_prompt: str
    requires_session_fields: list[str] = Field(default_factory=list)
    prompt_md_path: str | None = None
    #: Filled by :func:`discover_assistants` when a Markdown file is present—not from YAML.
    instructions_md: str | None = None


def runner_key_for_assistant(manifest: AssistantManifest) -> str:
    """Return the runner registry key for this manifest (typically ``manifest.runner``)."""
    return manifest.runner


def _default_assistants_dir() -> Path:
    env = os.environ.get(_ENV_ASSISTANTS_DIR)
    if env:
        return Path(env).expanduser().resolve()
    return (Path.cwd() / _DEFAULT_ASSISTANTS_REL).resolve()


def _should_skip_yaml(path: Path) -> bool:
    name = path.name
    stem = path.stem
    if stem.startswith("__"):
        return True
    if name.endswith(".example.yaml") or ".example.yaml" in name:
        return True
    return False


def _load_instructions_md(
    assistants_dir: Path,
    stem: str,
    manifest: AssistantManifest,
) -> str | None:
    if manifest.prompt_md_path:
        md = (assistants_dir / manifest.prompt_md_path).resolve()
        if md.is_file():
            return md.read_text(encoding="utf-8")
        return None
    sibling = assistants_dir / f"{stem}.md"
    if sibling.is_file():
        return sibling.read_text(encoding="utf-8")
    return None


def discover_assistants(assistants_dir: Path | None = None) -> dict[str, AssistantManifest]:
    """Load every ``*.yaml`` manifest under the assistants directory.

    If ``assistants_dir`` is omitted, uses :envvar:`JUNO_ASSISTANTS_DIR` or ``./assistants``
    relative to the process current working directory.

    Skips names starting with ``__`` and files matching ``*.example.yaml``.

    Keys are manifest stems (e.g. ``mercury`` for ``mercury.yaml``).
    ``instructions_md`` is set from ``prompt_md_path`` or a sibling ``<stem>.md`` when readable.
    """
    base = assistants_dir.expanduser().resolve() if assistants_dir is not None else _default_assistants_dir()
    if not base.is_dir():
        return {}

    out: dict[str, AssistantManifest] = {}
    for yaml_path in sorted(base.glob("*.yaml")):
        if _should_skip_yaml(yaml_path):
            continue
        stem = yaml_path.stem
        raw_text = yaml_path.read_text(encoding="utf-8")
        try:
            data = yaml.safe_load(raw_text)
        except yaml.YAMLError as exc:
            raise ValueError(f"Invalid YAML in {yaml_path}: {exc}") from exc
        if not isinstance(data, dict):
            raise ValueError(f"{yaml_path} must contain a YAML mapping at the root.")
        try:
            manifest = AssistantManifest.model_validate(data)
        except ValidationError as exc:
            raise ValueError(f"Invalid assistant manifest {yaml_path}: {exc}") from exc
        instructions = _load_instructions_md(base, stem, manifest)
        if instructions is not None:
            manifest = manifest.model_copy(update={"instructions_md": instructions})
        out[stem] = manifest
    return out
