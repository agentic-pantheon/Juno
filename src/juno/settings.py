"""Runtime settings loaded from environment (minimal scaffold)."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Placeholder; expand with OPENAI_MODEL, Mercury URL, Telegram token, etc."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
