"""Telegram bot: polling, supervisor + Mercury, wallet approval inline keyboard."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import signal
from pathlib import Path
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langgraph.graph.state import CompiledStateGraph
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatAction
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

from juno.agents import build_mercury_subagent, build_supervisor
from juno.identity import JunoIdentityNotFoundError, JunoIdentityValidationError, load_identity
from juno.settings import Settings
from juno.assistants.loader import discover_assistants
from juno.assistants.mercury_runner import MercuryAssistantRunner
from juno.telegram.parsing import extract_approval_token

logger = logging.getLogger(__name__)

# Next user message merges ``approval_response`` from this map (Telegram chat_id -> payload string).
_pending_approval: dict[int, str] = {}
# Last Mercury approval_token seen for this chat (set when inline keyboard is shown).
_last_approval_token: dict[int, str | None] = {}


def _msg_content_str(content: str | list[str | dict[str, Any]]) -> str:
    if isinstance(content, str):
        return content
    return str(content)


def _final_ai_content(messages: list[BaseMessage]) -> str:
    for m in reversed(messages):
        if isinstance(m, AIMessage):
            return _msg_content_str(m.content)
    return ""


def _messages_blob_for_approval(messages: list[BaseMessage]) -> str:
    parts: list[str] = []
    for m in messages:
        if isinstance(m, AIMessage):
            parts.append(_msg_content_str(m.content))
        elif getattr(m, "type", None) == "tool":
            parts.append(str(m.content))
    return "\n".join(parts)


def _approval_state_value(decision: str, token: str | None) -> str:
    if token:
        return f"{decision}:{token}"
    return decision


def _build_supervisor(settings: Settings) -> CompiledStateGraph:
    assistants_root = (
        settings.juno_assistants_dir if settings.juno_assistants_dir is not None else Path("assistants")
    )
    manifests = discover_assistants(assistants_root)
    mercury_manifest = manifests.get("mercury")
    if mercury_manifest is None:
        raise ValueError(
            f"No mercury assistant manifest under {assistants_root.resolve()}. Add assistants/mercury.yaml.",
        )
    base = settings.mercury_base_url.strip()
    if not base:
        raise ValueError(
            "MERCURY_BASE_URL is empty. Set it to your Mercury API base URL (scheme + host, no /v1/agent path).",
        )
    runner = MercuryAssistantRunner(base)
    sub = build_mercury_subagent(
        model=settings.openai_model,
        manifest=mercury_manifest,
        runner=runner,
    )
    return build_supervisor(model=settings.openai_model, mercury_subagent=sub)


async def _typing_while(
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


async def _invoke_supervisor(
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
        return await _typing_while(application.bot, chat_id, fut)
    return await fut


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message:
        await update.message.reply_text(
            "Juno routes your messages through a supervisor and Mercury when needed. "
            "Send text to chat. If wallet approval is required, tap Approve or Decline, "
            "then send any message to continue with that choice.",
        )


async def handle_approval_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    if not q or not update.effective_chat:
        return
    await q.answer()
    chat_id = update.effective_chat.id
    data = q.data or ""
    token = _last_approval_token.get(chat_id)
    if data == "apr:yes":
        _pending_approval[chat_id] = _approval_state_value("approved", token)
    elif data == "apr:no":
        _pending_approval[chat_id] = _approval_state_value("denied", token)
    try:
        await q.edit_message_reply_markup(reply_markup=None)
    except Exception:
        logger.debug("edit_message_reply_markup failed", exc_info=True)
    await context.bot.send_message(
        chat_id=chat_id,
        text="Choice recorded. Send any message to continue.",
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_chat or not update.message or not update.message.text:
        return
    chat_id = update.effective_chat.id
    user = update.effective_user
    text = update.message.text.strip()
    supervisor: CompiledStateGraph = context.application.bot_data["supervisor"]
    settings: Settings = context.application.bot_data["settings"]

    inp: dict[str, Any] = {
        "messages": [HumanMessage(content=text)],
        "user_id": str(user.id) if user else None,
        "wallet_id": None,
        "chain": None,
    }
    if chat_id in _pending_approval:
        inp["approval_response"] = _pending_approval.pop(chat_id)
    had_approval_merge = "approval_response" in inp

    thread_id = str(chat_id)
    config = {"configurable": {"thread_id": thread_id}}

    try:
        out = await _invoke_supervisor(
            context.application,
            chat_id,
            supervisor,
            inp,
            config,
            use_typing=settings.juno_use_stream,
        )
    except Exception:
        logger.exception("supervisor.invoke failed")
        await update.message.reply_text("Something went wrong. Please try again.")
        return

    if had_approval_merge:
        _last_approval_token.pop(chat_id, None)

    final_text = _final_ai_content(out["messages"])
    blob = _messages_blob_for_approval(out["messages"])
    if "Wallet approval required" in blob:
        token = extract_approval_token(blob)
        _last_approval_token[chat_id] = token
        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("Approve", callback_data="apr:yes"),
                    InlineKeyboardButton("Decline", callback_data="apr:no"),
                ],
            ],
        )
        body = final_text if final_text.strip() else "Wallet approval required."
        await update.message.reply_text(body, reply_markup=keyboard)
        return

    await update.message.reply_text(final_text if final_text.strip() else "(no reply)")


async def _wait_for_shutdown() -> None:
    loop = asyncio.get_running_loop()
    stop = asyncio.Event()

    def _on_stop() -> None:
        stop.set()

    try:
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, _on_stop)
    except NotImplementedError:
        await asyncio.Future()
        return
    await stop.wait()


async def run_bot(settings: Settings | None = None) -> None:
    settings = settings or Settings()
    if not settings.telegram_bot_token.strip():
        raise ValueError("TELEGRAM_BOT_TOKEN is missing or empty.")

    try:
        identity = load_identity(settings.juno_identity_path)
    except JunoIdentityNotFoundError as exc:
        logger.error(
            "Identity file is required. Copy config/juno.identity.yaml.example to "
            "config/juno.identity.yaml or set JUNO_IDENTITY_PATH. %s",
            exc,
        )
        raise SystemExit(1) from exc
    except JunoIdentityValidationError as exc:
        logger.error("Invalid identity YAML: %s", exc)
        raise SystemExit(1) from exc

    logger.info("Loaded identity agent_id=%s display_name=%s", identity.agent_id, identity.display_name)

    supervisor = _build_supervisor(settings)
    application = Application.builder().token(settings.telegram_bot_token.strip()).build()
    application.bot_data["supervisor"] = supervisor
    application.bot_data["settings"] = settings

    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CallbackQueryHandler(handle_approval_callback, pattern=r"^apr:"))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    async with application:
        await application.start()
        await application.updater.start_polling(allowed_updates=Update.ALL_TYPES)
        try:
            await _wait_for_shutdown()
        finally:
            await application.updater.stop()
            await application.stop()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    asyncio.run(run_bot())


if __name__ == "__main__":
    main()

__all__ = ["main", "run_bot"]
