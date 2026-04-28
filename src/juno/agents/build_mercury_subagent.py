"""Mercury specialist sub-agent: one tool that POSTs a turn via :class:`MercuryAssistantRunner`."""

from __future__ import annotations

from typing import Annotated, Any

from langchain.agents import create_agent
from langchain.tools import InjectedState, tool
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, convert_to_openai_messages
from langgraph.graph.state import CompiledStateGraph

from juno.agents.mercury_payload import turn_result_to_tool_text
from juno.agents.state import CustomAgentState
from juno.assistants.loader import AssistantManifest
from juno.assistants.mercury_runner import MercuryAssistantRunner


def build_mercury_subagent(
    *,
    model: str | BaseChatModel,
    manifest: AssistantManifest,
    runner: MercuryAssistantRunner,
) -> CompiledStateGraph:
    """Build a LangChain agent whose only tool forwards turns to Mercury."""
    full_system = manifest.system_prompt.strip()
    if manifest.instructions_md:
        full_system = full_system + "\n\n" + manifest.instructions_md

    @tool
    def mercury_turn(
        mercury_instruction: str,
        state: Annotated[dict[str, Any], InjectedState],
    ) -> str:
        """Send a focused instruction to the Mercury assistant backend.

        Use this when you need Mercury to run agent logic, tools, or blockchain
        actions described in ``mercury_instruction``. The current conversation
        context is forwarded automatically; you only provide what Mercury should do next.
        """
        msgs = list(state.get("messages", []))
        oai_messages = convert_to_openai_messages(msgs + [HumanMessage(content=mercury_instruction)])
        payload: dict[str, Any] = {"messages": oai_messages}
        for key in ("user_id", "wallet_id", "chain", "approval_response"):
            if key in state and state[key] is not None:
                payload[key] = state[key]
        result = runner.run_turn(payload)
        return turn_result_to_tool_text(result)

    return create_agent(
        model=model,
        tools=[mercury_turn],
        system_prompt=full_system,
        state_schema=CustomAgentState,
        checkpointer=None,
    )


__all__ = ["build_mercury_subagent"]
