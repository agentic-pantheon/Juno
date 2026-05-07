"""Central factory for supervisor/sub-agent chat models (standard vs Shroud)."""

from __future__ import annotations

import os

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI

from juno.settings import Settings


def _openai_compatible_model_id(openai_model: str) -> str:
    """Map LangChain-style ids such as ``openai:gpt-4o-mini`` to an OpenAI-compatible ``model`` name."""
    s = openai_model.strip()
    if ":" in s:
        return s.split(":", 1)[1].strip()
    return s


def build_agent_chat_model(settings: Settings) -> str | BaseChatModel:
    """Return a LangChain ``create_agent`` model argument.

    In normal mode, returns ``settings.openai_model`` unchanged (framework-supported model string).

    When ``settings.juno_use_shroud`` is true, returns :class:`~langchain_openai.ChatOpenAI` targeting
    ``settings.juno_llm_base_url`` with Shroud vault headers (no upstream provider API key).

    Raises:
        ValueError: Shroud enabled but required configuration or agent key env is missing.
    """
    if not settings.juno_use_shroud:
        return settings.openai_model

    env_name = settings.juno_shroud_agent_key_env.strip()
    if not env_name:
        msg = (
            "Shroud is enabled but juno_shroud_agent_key_env is empty; configure which "
            "environment variable supplies X-Shroud-Agent-Key."
        )
        raise ValueError(msg)

    agent_key = os.environ.get(env_name, "").strip()
    if not agent_key:
        raise ValueError(
            f"Shroud is enabled but environment variable {env_name!r} is unset or empty.",
        )

    base_url = settings.juno_llm_base_url.strip()
    if not base_url:
        msg = (
            "Shroud is enabled but juno_llm_base_url is empty; set an OpenAI-compatible base URL."
        )
        raise ValueError(msg)

    model_id = _openai_compatible_model_id(settings.openai_model)
    headers: dict[str, str] = {
        "X-Shroud-Agent-Key": agent_key,
        "X-Shroud-Provider": settings.juno_shroud_provider.strip(),
    }
    if settings.juno_shroud_model_header:
        headers["X-Shroud-Model"] = model_id

    # Upstream provider keys are not used; Shroud validates vault credentials via headers.
    return ChatOpenAI(
        model=model_id,
        base_url=base_url,
        api_key="unused",
        default_headers=headers,
    )
