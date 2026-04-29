"""Telegram bot: polling, supervisor + Mercury, wallet approval inline keyboard."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import signal
from pathlib import Path
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.graph.state import CompiledStateGraph
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatAction
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

from juno.agents import build_mercury_subagent, build_supervisor
from juno.identity import JunoIdentityNotFoundError, JunoIdentityValidationError, load_identity
from juno.settings import Settings
from juno.assistants.loader import discover_assistants
from juno.assistants.mercury_runner import MercuryAssistantRunner
from juno.telegram.errors import format_agent_error
from juno.telegram.parsing import extract_approval_correlation_id
from juno.telegram.session import clear_chat_session, get_chat_session

logger = logging.getLogger(__name__)

# Next user message merges ``approval_response`` from this map (Telegram chat_id -> payload string).
_pending_approval: dict[int, str] = {}
# Correlation id for Telegram approve/deny (prefer Mercury idempotency_key, else approval_token).
_last_approval_token: dict[int, str | None] = {}

_TELEGRAM_AFTER_APPROVE_SYSTEM = (
    "The user tapped Approve in Telegram and `approval_response` is now in session. "
    "You MUST call the `mercury` tool immediately: ask the specialist to repeat the exact "
    "same mercury_invoke intent (including idempotency_key) with no MetaMask/in-wallet "
    "instructions unless this deployment explicitly uses them."
)


def _msg_content_str(content: str | list[str | dict[str, Any]]) -> str:
    if isinstance(content, str):
        return content
    return str(content)


def _final_ai_content(messages: list[BaseMessage]) -> str:
    for m in reversed(messages):
        if isinstance(m, AIMessage):
            return _msg_content_str(m.content)
    return ""


def _conversation_needs_approval_ui(blob: str) -> bool:
    """True if Mercury/tool output indicates an approval gate (Telegram keyboard)."""
    if not blob:
        return False
    low = blob.lower()
    if any(
        p in low
        for p in (
            "wallet approval required",
            "approval_required",
            '"status": "approval_required"',
            "'status': 'approval_required'",
            "approval_payload",
            "human approval",
            "needs_approval",
            "need approval",
            "needs approval",
            "pending approval",
            "request_approval",
            "approval gate",
            "approval is required",
            "requires approval",
        )
    ):
        return True
    return False


def _assistant_promises_inline_approval_ui(text: str) -> bool:
    """True if the model told the user to use in-chat Approve (but we may not have shown buttons)."""
    if not text or len(text) < 8:
        return False
    low = text.lower()
    if any(
        neg in low
        for neg in (
            "don't tap",
            "do not tap",
            "no approval button",
            "doesn't need approval",
            "does not need approval",
        )
    ):
        return False
    if "approve" not in low and "approval" not in low:
        return False
    return any(
        phrase in low
        for phrase in (
            "tap the",
            "tap approve",
            "approval button",
            "approve button",
            "approval prompt",
            "in this chat",
            "**approve**",
        )
    )


def _should_show_mercury_approval_keyboard(blob: str, final_assistant_text: str) -> bool:
    """Show Approve/Decline when Mercury or tool output says so, or the model promised in-chat buttons."""
    if _conversation_needs_approval_ui(blob):
        return True
    if _assistant_promises_inline_approval_ui(final_assistant_text):
        return True
    combined = f"{blob}\n{final_assistant_text}"
    return _conversation_needs_approval_ui(combined)


def _messages_blob_for_approval(messages: list[BaseMessage]) -> str:
    """All model + tool text turns (Mercury results often only appear on ToolMessage)."""
    parts: list[str] = []
    for m in messages:
        if isinstance(m, AIMessage):
            parts.append(_msg_content_str(m.content))
        elif isinstance(m, ToolMessage):
            parts.append(str(m.content))
        elif getattr(m, "type", None) == "tool":
            parts.append(str(m.content))
    return "\n".join(parts)


def _approval_state_value(decision: str, token: str | None) -> str:
    if token:
        return f"{decision}:{token}"
    return decision


# Short synthetic user line after inline Approve/Decline (checkpoint); system prompts carry real instructions.
_MERCURY_INLINE_CONTINUE_TEXT = "(Inline) User submitted Approve or Decline — continue the pending Mercury operation."


async def _execute_supervisor_turn(
    application: Application,
    *,
    chat_id: int,
    user: Any,
    user_text: str,
    reply_to_message_id: int | None = None,
) -> None:
    """Run one supervisor invoke and send the reply (and optional approval keyboard)."""
    supervisor: CompiledStateGraph = application.bot_data["supervisor"]
    settings: Settings = application.bot_data["settings"]
    sess = get_chat_session(application.bot_data, chat_id)

    had_approval_merge = False
    approval_val: str | None = None
    if chat_id in _pending_approval:
        approval_val = _pending_approval.pop(chat_id)
        had_approval_merge = True

    messages: list[Any] = []
    if had_approval_merge:
        messages.append(SystemMessage(content=_TELEGRAM_AFTER_APPROVE_SYSTEM))
    messages.append(HumanMessage(content=user_text))

    inp: dict[str, Any] = {
        "messages": messages,
        "user_id": str(user.id) if user else None,
        "wallet_id": sess["wallet_id"],
        "chain": sess["chain"],
    }
    if approval_val is not None:
        inp["approval_response"] = approval_val

    config = {"configurable": {"thread_id": str(chat_id)}}

    try:
        out = await _invoke_supervisor(
            application,
            chat_id,
            supervisor,
            inp,
            config,
            use_typing=settings.juno_use_stream,
        )
    except Exception as exc:
        logger.exception("supervisor.invoke failed")
        await application.bot.send_message(
            chat_id=chat_id,
            text=format_agent_error(exc),
            reply_to_message_id=reply_to_message_id,
        )
        return

    if had_approval_merge:
        _last_approval_token.pop(chat_id, None)

    final_text = _final_ai_content(out["messages"])
    blob = _messages_blob_for_approval(out["messages"])
    if _should_show_mercury_approval_keyboard(blob, final_text):
        token = extract_approval_correlation_id(f"{blob}\n{final_text}")
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
        await application.bot.send_message(
            chat_id=chat_id,
            text=body,
            reply_markup=keyboard,
            reply_to_message_id=reply_to_message_id,
        )
        return

    await application.bot.send_message(
        chat_id=chat_id,
        text=final_text if final_text.strip() else "(no reply)",
        reply_to_message_id=reply_to_message_id,
    )


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
            "MERCURY_BASE_URL is empty. Set it to your Mercury API base URL (scheme + host, no path suffix).",
        )
    runner = MercuryAssistantRunner(
        base,
        http_path=settings.mercury_http_path,
        request_body_mode=settings.mercury_request_body_mode,
    )
    sub = build_mercury_subagent(
        model=settings.openai_model,
        manifest=mercury_manifest,
        runner=runner,
    )
    return build_supervisor(
        model=settings.openai_model,
        mercury_subagent=sub,
        supervisor_prompt_path=settings.juno_supervisor_prompt_path,
    )


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
            "Juno routes on-chain and account questions through Mercury (real backend data).\n\n"
            "• Send any message to chat.\n"
            "• Optional: /chain base (or ethereum, …) and /wallet 0x… so Mercury gets context.\n"
            "• /session shows saved chain/wallet; /session_clear resets them.\n"
            "• If wallet approval is required, tap Approve or Decline — Juno continues automatically.",
        )


async def cmd_chain(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_chat:
        return
    chat_id = update.effective_chat.id
    args = context.args or []
    sess = get_chat_session(context.application.bot_data, chat_id)
    if not args:
        cur = sess["chain"] or "not set"
        await update.message.reply_text(
            f"Current chain: `{cur}`.\nUsage: `/chain base` (or another network name).",
        )
        return
    sess["chain"] = " ".join(args).strip().lower()
    await update.message.reply_text(f"Chain set to `{sess['chain']}`. Mercury will see this on the next message.")


async def cmd_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_chat:
        return
    chat_id = update.effective_chat.id
    args = context.args or []
    sess = get_chat_session(context.application.bot_data, chat_id)
    if not args:
        cur = sess["wallet_id"] or "not set"
        await update.message.reply_text(
            f"Current wallet: `{cur}`.\nUsage: `/wallet 0x…`",
        )
        return
    sess["wallet_id"] = args[0].strip()
    await update.message.reply_text("Wallet saved. Mercury will see it on the next message.")


async def cmd_session(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_chat:
        return
    chat_id = update.effective_chat.id
    sess = get_chat_session(context.application.bot_data, chat_id)
    await update.message.reply_text(
        "Session for this chat:\n"
        f"• chain: `{sess['chain'] or '—'}`\n"
        f"• wallet_id: `{sess['wallet_id'] or '—'}`",
    )


async def cmd_session_clear(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_chat:
        return
    chat_id = update.effective_chat.id
    clear_chat_session(context.application.bot_data, chat_id)
    await update.message.reply_text("Session cleared (chain and wallet).")


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
    else:
        return
    try:
        await q.edit_message_reply_markup(reply_markup=None)
    except Exception:
        logger.debug("edit_message_reply_markup failed", exc_info=True)
    reply_to = q.message.message_id if q.message else None
    await _execute_supervisor_turn(
        context.application,
        chat_id=chat_id,
        user=update.effective_user,
        user_text=_MERCURY_INLINE_CONTINUE_TEXT,
        reply_to_message_id=reply_to,
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_chat or not update.message or not update.message.text:
        return
    chat_id = update.effective_chat.id
    user = update.effective_user
    text = update.message.text.strip()
    await _execute_supervisor_turn(
        context.application,
        chat_id=chat_id,
        user=user,
        user_text=text,
        reply_to_message_id=update.message.message_id,
    )


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
    application.add_handler(CommandHandler("chain", cmd_chain))
    application.add_handler(CommandHandler("wallet", cmd_wallet))
    application.add_handler(CommandHandler("session", cmd_session))
    application.add_handler(CommandHandler("session_clear", cmd_session_clear))
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
    # Pydantic Settings reads `.env` for its own fields but does not populate
    # ``os.environ``; Groq/OpenAI clients expect API keys in the environment.
    from dotenv import load_dotenv

    load_dotenv()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    asyncio.run(run_bot())


if __name__ == "__main__":
    main()

__all__ = ["main", "run_bot"]
