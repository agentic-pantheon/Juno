"""Juno: Telegram-first LangChain supervisor with Mercury runners."""

from juno.assistants import (
    AssistantManifest,
    discover_assistants,
    runner_key_for_assistant,
)
from juno.identity import (
    DefaultSessionFields,
    JunoIdentity,
    JunoIdentityNotFoundError,
    JunoIdentityValidationError,
    JunoSecrets,
    load_identity,
)
from juno.settings import Settings

__version__ = "0.1.0"

__all__ = [
    "AssistantManifest",
    "DefaultSessionFields",
    "JunoIdentity",
    "JunoIdentityNotFoundError",
    "JunoIdentityValidationError",
    "JunoSecrets",
    "Settings",
    "__version__",
    "discover_assistants",
    "load_identity",
    "runner_key_for_assistant",
]
