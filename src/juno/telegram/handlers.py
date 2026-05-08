"""python-telegram-bot command and message handlers."""

from __future__ import annotations

import logging
from telegram import Update
from telegram.ext import ContextTypes

from juno.telegram.approval_state import get_last_approval_token, set_pending_approval
from juno.telegram.approval_ui import MERCURY_INLINE_CONTINUE_TEXT, approval_state_value
from juno.telegram.formatting import (
    escape_md_v2,
    inline_code_md_v2,
    reply_text_markdown_v2,
    reply_user_text_markdown_v2_safe,
)
from juno.telegram.session import clear_chat_session, get_chat_session
from juno.telegram.turn import execute_supervisor_turn

logger = logging.getLogger(__name__)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message:
        await reply_user_text_markdown_v2_safe(
            update.message,
            raw_text=(
                "Juno routes on-chain and account questions through Mercury (real backend data).\n\n"
                "• Send any message to chat.\n"
                "• Optional: /chain base (or ethereum, …) and /wallet 0x… so Mercury gets context.\n"
                "• /session shows saved chain/wallet; /session_clear resets them.\n"
                "• If wallet approval is required, tap Approve or Decline — Juno continues automatically."
            ),
        )


async def cmd_chain(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_chat:
        return
    chat_id = update.effective_chat.id
    args = context.args or []
    sess = get_chat_session(context.application.bot_data, chat_id)
    if not args:
        cur = sess["chain"] or "not set"
        await reply_text_markdown_v2(
            update.message,
            escape_md_v2("Current chain: ")
            + inline_code_md_v2(cur)
            + escape_md_v2("\nUsage: /chain base (or another network name)."),
        )
        return
    sess["chain"] = " ".join(args).strip().lower()
    await reply_text_markdown_v2(
        update.message,
        escape_md_v2("Chain set to ")
        + inline_code_md_v2(sess["chain"])
        + escape_md_v2(". Mercury will see it on the next message."),
    )


async def cmd_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_chat:
        return
    chat_id = update.effective_chat.id
    args = context.args or []
    sess = get_chat_session(context.application.bot_data, chat_id)
    if not args:
        cur = sess["wallet_id"] or "not set"
        await reply_text_markdown_v2(
            update.message,
            escape_md_v2("Current wallet: ")
            + inline_code_md_v2(cur)
            + escape_md_v2("\nUsage: /wallet 0x…"),
        )
        return
    sess["wallet_id"] = args[0].strip()
    await reply_user_text_markdown_v2_safe(
        update.message,
        raw_text="Wallet saved. Mercury will see it on the next message.",
    )


async def cmd_session(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_chat:
        return
    chat_id = update.effective_chat.id
    sess = get_chat_session(context.application.bot_data, chat_id)
    await reply_text_markdown_v2(
        update.message,
        escape_md_v2("Session for this chat:\n")
        + escape_md_v2("• chain: ")
        + inline_code_md_v2(sess["chain"] or "—")
        + escape_md_v2("\n• wallet_id: ")
        + inline_code_md_v2(sess["wallet_id"] or "—"),
    )


async def cmd_session_clear(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_chat:
        return
    chat_id = update.effective_chat.id
    clear_chat_session(context.application.bot_data, chat_id)
    await reply_user_text_markdown_v2_safe(
        update.message,
        raw_text="Session cleared (chain and wallet).",
    )


async def handle_approval_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    if not q or not update.effective_chat:
        return
    await q.answer()
    chat_id = update.effective_chat.id
    data = q.data or ""
    token = get_last_approval_token(context.application.bot_data, chat_id)
    if data == "apr:yes":
        set_pending_approval(context.application.bot_data, chat_id, approval_state_value("approved", token))
    elif data == "apr:no":
        set_pending_approval(context.application.bot_data, chat_id, approval_state_value("denied", token))
    else:
        return
    try:
        await q.edit_message_reply_markup(reply_markup=None)
    except Exception:
        logger.debug("edit_message_reply_markup failed", exc_info=True)
    reply_to = q.message.message_id if q.message else None
    await execute_supervisor_turn(
        context.application,
        chat_id=chat_id,
        user=update.effective_user,
        user_text=MERCURY_INLINE_CONTINUE_TEXT,
        reply_to_message_id=reply_to,
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_chat or not update.message or not update.message.text:
        return
    chat_id = update.effective_chat.id
    user = update.effective_user
    text = update.message.text.strip()
    await execute_supervisor_turn(
        context.application,
        chat_id=chat_id,
        user=user,
        user_text=text,
        reply_to_message_id=update.message.message_id,
    )


__all__ = [
    "cmd_chain",
    "cmd_session",
    "cmd_session_clear",
    "cmd_start",
    "cmd_wallet",
    "handle_approval_callback",
    "handle_message",
]
