"""Assistant manifests and discovery (YAML under ``assistants/`` directory)."""

from juno.assistants.loader import (
    AssistantManifest,
    discover_assistants,
    runner_key_for_assistant,
)

__all__ = [
    "AssistantManifest",
    "discover_assistants",
    "runner_key_for_assistant",
]
