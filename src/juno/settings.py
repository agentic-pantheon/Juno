"""Runtime settings loaded from environment (minimal scaffold)."""

from pathlib import Path
from typing import Literal

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
    juno_supervisor_prompt_path: Path | None = Field(
        default=None,
        description=(
            "Optional path to supervisor system prompt Markdown; env ``JUNO_SUPERVISOR_PROMPT_PATH``. "
            "When unset, ``config/juno.supervisor.md`` under the process working directory is used."
        ),
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
    mercury_runner_mode: Literal["http", "local"] = Field(
        default="http",
        validation_alias=AliasChoices(
            "mercury_runner_mode",
            "MERCURY_RUNNER_MODE",
            "JUNO_MERCURY_RUNNER_MODE",
        ),
        description=(
            "Mercury assistant transport: ``http`` (remote API) or ``local`` (in-process graph). "
            "Env ``MERCURY_RUNNER_MODE`` or ``JUNO_MERCURY_RUNNER_MODE``."
        ),
    )
    mercury_base_url: str = Field(
        default="",
        description=(
            "Mercury HTTP API base URL (no trailing path); env ``MERCURY_BASE_URL``. "
            "Required when ``mercury_runner_mode`` is ``http``; ignored for ``local``."
        ),
    )
    mercury_http_path: str = Field(
        default="/v1/mercury/invoke",
        description=(
            "Mercury invoke path; env MERCURY_HTTP_PATH. "
            "Default /v1/mercury/invoke (structured intent). Use /v1/agent for pan-agentikit envelope."
        ),
    )
    mercury_request_body_mode: Literal["flat", "nested_input"] = Field(
        default="flat",
        description=(
            "flat: JSON body is the Mercury invoke dict as-is. "
            "nested_input: wrap as {input: dict}. Env MERCURY_REQUEST_BODY_MODE."
        ),
    )
    juno_disabled_assistants: str = Field(
        default="",
        validation_alias=AliasChoices("JUNO_DISABLED_ASSISTANTS", "juno_disabled_assistants"),
        description=(
            "Comma-separated ``juno.assistants`` entry-point names to skip (e.g. ``mercury``). "
            "Env ``JUNO_DISABLED_ASSISTANTS``."
        ),
    )
    juno_use_stream: bool = Field(
        default=False,
        description="If true, send periodic typing while the supervisor runs; env ``JUNO_USE_STREAM``.",
    )
    juno_long_term_memory_dir: Path = Field(
        default=Path("data") / "juno_long_term_memory",
        validation_alias=AliasChoices("JUNO_LONGTERM_MEMORY_DIR"),
        description=(
            "Directory for per-user long-term memory JSON files; env ``JUNO_LONGTERM_MEMORY_DIR``. "
            "Default ``data/juno_long_term_memory`` relative to the process working directory."
        ),
    )
    juno_checkpointer_database_url: str = Field(
        default="",
        description=(
            "Secret-bearing PostgreSQL DSN for supervisor checkpoint persistence; env ``JUNO_CHECKPOINTER_DATABASE_URL``. "
            "When empty, an in-memory checkpointer fallback is used."
        ),
    )
