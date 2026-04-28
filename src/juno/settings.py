"""Runtime settings loaded from environment (minimal scaffold)."""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Process-level settings; loaders also read ``JUNO_*`` env vars directly."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    juno_identity_path: Path | None = Field(
        default=None,
        description="Optional path to identity YAML; env ``JUNO_IDENTITY_PATH``.",
    )
    juno_assistants_dir: Path | None = Field(
        default=None,
        description="Optional assistants directory; env ``JUNO_ASSISTANTS_DIR``.",
    )
