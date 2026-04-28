"""Runtime settings loaded from environment (minimal scaffold)."""

from pathlib import Path

from pydantic import AliasChoices, Field
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
    telegram_bot_token: str = Field(
        default="",
        description="Telegram Bot API token; env ``TELEGRAM_BOT_TOKEN``.",
    )
    openai_model: str = Field(
        default="openai:gpt-4o-mini",
        validation_alias=AliasChoices("JUNO_MODEL", "OPENAI_MODEL"),
        description="Chat model id for LangChain agents; env ``JUNO_MODEL`` or ``OPENAI_MODEL``.",
    )
    mercury_base_url: str = Field(
        default="",
        description=(
            "Mercury HTTP API base URL (no trailing path); env ``MERCURY_BASE_URL``. "
            "Required for real Mercury runs; empty is rejected at bot startup."
        ),
    )
    juno_use_stream: bool = Field(
        default=False,
        description="If true, send periodic typing while the supervisor runs; env ``JUNO_USE_STREAM``.",
    )
