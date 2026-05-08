"""One supervisor graph invocation and Telegram reply (including approval keyboard)."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import uuid
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph.state import CompiledStateGraph
from telegram.constants import ChatAction
from telegram.ext import Application

from juno.logging_config import juno_trace_scope
from juno.settings import Settings
from juno.telegram.approval_state import (
    pop_last_approval_token,
    pop_pending_approval,
    set_last_approval_token,
)
from juno.telegram.approval_ui import (
    TELEGRAM_AFTER_APPROVE_SYSTEM,
    mercury_approval_inline_keyboard,
    should_show_wallet_approval_keyboard,
)
from juno.telegram.errors import format_agent_error
from juno.telegram.formatting import send_assistant_reply_html_safe
from juno.telegram.messages import final_ai_content, messages_blob_for_approval
from juno.telegram.parsing import extract_approval_correlation_id
from juno.telegram.session import get_chat_session

logger = logging.getLogger(__name__)


async def typing_while(
    bot: Any,
    chat_id: int,
    awaitable_result: Any,
) -> Any:
    stop = asyncio.Event()

    async def pump() -> None:
        while not stop.is_set():
            try:
                await bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
            except Exception:
                logger.debug("send_chat_action failed", exc_info=True)
            try:
                await asyncio.wait_for(stop.wait(), timeout=4.0)
            except asyncio.TimeoutError:
                continue

    task = asyncio.create_task(pump())
    try:
        return await awaitable_result
    finally:
        stop.set()
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


async def invoke_supervisor(
    application: Application,
    chat_id: int,
    supervisor: CompiledStateGraph,
    inp: dict[str, Any],
    config: dict[str, Any],
    *,
    use_typing: bool,
) -> dict[str, Any]:
    fut = asyncio.to_thread(supervisor.invoke, inp, config)
    if use_typing:
        return await typing_while(application.bot, chat_id, fut)
    return await fut


async def execute_supervisor_turn(
    application: Application,
    *,
    chat_id: int,
    user: Any,
    user_text: str,
    reply_to_message_id: int | None = None,
) -> None:
    """Run one supervisor invoke and send the reply (and optional approval keyboard)."""
    trace_id = uuid.uuid4().hex
    user_id = str(user.id) if user else None
    supervisor: CompiledStateGraph = application.bot_data["supervisor"]
    settings: Settings = application.bot_data["settings"]
    sess = get_chat_session(application.bot_data, chat_id)

    had_approval_merge = False
    approval_val: str | None = None
    pending = pop_pending_approval(application.bot_data, chat_id)
    if pending is not None:
        approval_val = pending
        had_approval_merge = True

    messages: list[Any] = []
    if had_approval_merge:
        messages.append(SystemMessage(content=TELEGRAM_AFTER_APPROVE_SYSTEM))
    messages.append(HumanMessage(content=user_text))

    inp: dict[str, Any] = {
        "messages": messages,
        "user_id": user_id,
        "wallet_id": sess["wallet_id"],
        "chain": sess["chain"],
    }
    if approval_val is not None:
        inp["approval_response"] = approval_val

    metadata = {
        "juno_trace_id": trace_id,
        "telegram_chat_id": chat_id,
        "telegram_user_id": user_id,
    }
    config: dict[str, Any] = {
        "configurable": {
            "thread_id": str(chat_id),
            "juno_trace_id": trace_id,
        },
        "metadata": metadata,
        "tags": ["juno", "telegram"],
        "run_name": "juno_telegram_turn",
    }

    with juno_trace_scope(trace_id):
        try:
            out = await invoke_supervisor(
                application,
                chat_id,
                supervisor,
                inp,
                config,
                use_typing=settings.juno_use_stream,
            )
        except Exception as exc:
            logger.exception(
                "supervisor.invoke failed (chat_id=%s trace_id=%s)",
                chat_id,
                trace_id,
            )
            await send_assistant_reply_html_safe(
                application.bot,
                chat_id=chat_id,
                raw_text=format_agent_error(exc),
                reply_to_message_id=reply_to_message_id,
            )
            return

    if had_approval_merge:
        pop_last_approval_token(application.bot_data, chat_id)

    final_text = final_ai_content(out["messages"])
    blob = messages_blob_for_approval(out["messages"])
    names = application.bot_data.get("wallet_approval_supervisor_tools") or frozenset()
    if should_show_wallet_approval_keyboard(blob, final_text, names):
        token = extract_approval_correlation_id(f"{blob}\n{final_text}")
        set_last_approval_token(application.bot_data, chat_id, token)
        keyboard = mercury_approval_inline_keyboard()
        body = final_text if final_text.strip() else "Wallet approval required."
        await send_assistant_reply_html_safe(
            application.bot,
            chat_id=chat_id,
            raw_text=body,
            reply_markup=keyboard,
            reply_to_message_id=reply_to_message_id,
        )
        return

    await send_assistant_reply_html_safe(
        application.bot,
        chat_id=chat_id,
        raw_text=final_text if final_text.strip() else "(no reply)",
        reply_to_message_id=reply_to_message_id,
    )


__all__ = [
    "execute_supervisor_turn",
    "invoke_supervisor",
    "typing_while",
]
