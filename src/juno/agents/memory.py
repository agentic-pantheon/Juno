"""Supervisor long-term memory: update tool and model-call profile injection."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from langchain.agents.middleware import wrap_model_call
from langchain.agents.middleware.types import ModelRequest
from langchain.tools import ToolRuntime, tool
from langchain_core.messages import AIMessage, SystemMessage
from langchain_core.tools import BaseTool

from juno.agents.state import CustomAgentState
from juno.memory import UserMemoryProfile, format_user_memory_for_prompt, load_user_memory, merge_user_memory

_LTM_HEADING = "## Long-term profile"
_LTM_ONBOARDING = (
    "No long-term profile is saved for this user yet. At the start of the conversation, "
    "ask the user for the details you should remember: their name, preferred agent name, "
    "wallet address if any, preferred tone (default concise), and the agent mission. "
    "Make this a brief setup question before handling other work; do not invent any values. "
    "When the user answers, call `update_user_memory` with the provided fields."
)


def _system_message_text(msg: SystemMessage | None) -> str:
    if msg is None:
        return ""
    content = msg.content
    if isinstance(content, str):
        return content
    return str(content)


def _profile_effective_summary(profile: UserMemoryProfile) -> str:
    tone = (profile.tone or "").strip() or "concise"
    parts: list[str] = [f"tone={tone!r}"]
    if profile.user_name:
        parts.append(f"user_name={profile.user_name!r}")
    if profile.agent_name:
        parts.append(f"agent_name={profile.agent_name!r}")
    if profile.wallet_address:
        parts.append(f"wallet_address={profile.wallet_address!r}")
    if profile.mission:
        mission = profile.mission.strip()
        if len(mission) > 80:
            mission = mission[:77] + "..."
        parts.append(f"mission={mission!r}")
    return ", ".join(parts)


def _is_start_of_thread(state: dict[str, Any]) -> bool:
    messages = state.get("messages") or []
    return not any(isinstance(message, AIMessage) for message in messages)


def build_update_user_memory_tool(memory_dir: Path) -> BaseTool:
    """Return the ``update_user_memory`` tool bound to ``memory_dir``."""

    @tool("update_user_memory")
    def update_user_memory(
        runtime: ToolRuntime,
        user_name: str | None = None,
        agent_name: str | None = None,
        wallet_address: str | None = None,
        tone: str | None = None,
        mission: str | None = None,
    ) -> str:
        """Persist optional user preferences for this Telegram user (tone, names, wallet, mission).

        Only non-null arguments overwrite stored fields. Requires ``user_id`` in agent state.
        """
        state = runtime.state
        user_id = state.get("user_id") if state else None
        if not user_id:
            return (
                "Error: no user_id in session state; cannot update long-term memory. "
                "The user must be identified first."
            )

        merged = merge_user_memory(
            memory_dir,
            str(user_id),
            user_name=user_name,
            agent_name=agent_name,
            wallet_address=wallet_address,
            tone=tone,
            mission=mission,
        )
        summary = _profile_effective_summary(merged)
        return f"Long-term memory saved. Effective profile: {summary}."

    return update_user_memory


def build_long_term_memory_model_middleware(memory_dir: Path) -> Any:
    """Inject a formatted long-term profile into the model request system message (per model call)."""

    @wrap_model_call(state_schema=CustomAgentState, name="inject_long_term_profile")
    def inject_long_term_profile(
        request: ModelRequest[Any],
        handler: Any,
    ) -> Any:
        state = request.state
        user_id = state.get("user_id") if state else None
        if not user_id:
            return handler(request)

        profile = load_user_memory(memory_dir, str(user_id))
        block = format_user_memory_for_prompt(profile)
        section = f"{_LTM_HEADING}\n\n{block}"
        if not profile.has_saved_context() and _is_start_of_thread(state):
            section = f"{section}\n\n{_LTM_ONBOARDING}"

        base_text = _system_message_text(request.system_message).rstrip()
        if base_text:
            new_content = f"{base_text}\n\n{section}"
        else:
            new_content = section

        return handler(request.override(system_message=SystemMessage(content=new_content)))

    return inject_long_term_profile


__all__ = [
    "build_long_term_memory_model_middleware",
    "build_update_user_memory_tool",
]
