"""Load Juno identity from YAML (`config/juno.identity.yaml` by default)."""

from __future__ import annotations

import os
from pathlib import Path
import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

_DEFAULT_IDENTITY_REL = Path("config") / "juno.identity.yaml"
_ENV_IDENTITY_PATH = "JUNO_IDENTITY_PATH"


class JunoIdentityNotFoundError(FileNotFoundError):
    """Raised when the identity file path does not exist or is not a file."""


class JunoIdentityValidationError(ValueError):
    """Raised when the identity YAML is present but fails Pydantic validation."""


class JunoSecrets(BaseModel):
    """Env var names for secrets (values are never read from YAML)."""

    model_config = ConfigDict(extra="allow")

    openai_api_key_env: str = Field(
        ...,
        description="Environment variable name holding the OpenAI API key.",
    )


class DefaultSessionFields(BaseModel):
    """Default session-related fields merged when absent (Mercury / graph state)."""

    model_config = ConfigDict(extra="allow")

    user_id: str | None = None
    wallet_id: str | None = None
    chain: str | None = None


class JunoIdentity(BaseModel):
    """Juno agent identity and default session metadata."""

    agent_id: str
    display_name: str
    secrets: JunoSecrets
    default_session_fields: DefaultSessionFields


def _resolve_identity_path(path: Path | None) -> Path:
    if path is not None:
        return path.expanduser().resolve()
    env = os.environ.get(_ENV_IDENTITY_PATH)
    if env:
        return Path(env).expanduser().resolve()
    return (Path.cwd() / _DEFAULT_IDENTITY_REL).resolve()


def load_identity(path: Path | None = None) -> JunoIdentity:
    """Load and validate identity from YAML.

    If ``path`` is omitted, uses :envvar:`JUNO_IDENTITY_PATH` or
    ``config/juno.identity.yaml`` under the current working directory.
    You may point ``path`` at ``config/juno.identity.yaml.example`` for local dev.

    Raises:
        JunoIdentityNotFoundError: If the resolved path is missing or not a file.
        JunoIdentityValidationError: If YAML parses but validation fails.
    """
    resolved = _resolve_identity_path(path)
    if not resolved.is_file():
        hint = (
            "Set JUNO_IDENTITY_PATH, or copy config/juno.identity.yaml.example to "
            "config/juno.identity.yaml."
        )
        raise JunoIdentityNotFoundError(
            f"Identity file not found: {resolved}. {hint}",
        )
    raw_text = resolved.read_text(encoding="utf-8")
    try:
        data = yaml.safe_load(raw_text)
    except yaml.YAMLError as exc:
        raise JunoIdentityValidationError(
            f"Invalid YAML in identity file {resolved}: {exc}",
        ) from exc
    if not isinstance(data, dict):
        raise JunoIdentityValidationError(
            f"Identity file {resolved} must contain a YAML mapping at the root.",
        )
    try:
        return JunoIdentity.model_validate(data)
    except ValidationError as exc:
        raise JunoIdentityValidationError(
            f"Invalid identity schema in {resolved}: {exc}",
        ) from exc
