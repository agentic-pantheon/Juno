"""Heuristics and helpers for Mercury wallet approval inline keyboard in Telegram."""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from juno.approval_markers import JUNO_WALLET_APPROVAL_UI_MARKER

TELEGRAM_AFTER_APPROVE_SYSTEM = (
    "The user tapped Approve in Telegram and `approval_response` is now in session. "
    "You MUST call the `mercury` tool immediately: ask the specialist to repeat the exact "
    "same mercury_invoke intent (including idempotency_key) with no MetaMask/in-wallet "
    "instructions unless this deployment explicitly uses them."
)

MERCURY_INLINE_CONTINUE_TEXT = (
    "(Inline) User submitted Approve or Decline — continue the pending Mercury operation."
)


def conversation_needs_approval_ui(blob: str) -> bool:
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


def assistant_promises_inline_approval_ui(text: str) -> bool:
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


def approval_state_value(decision: str, token: str | None) -> str:
    if token:
        return f"{decision}:{token}"
    return decision


def has_structured_wallet_approval_marker(blob: str, final_assistant_text: str) -> bool:
    combined = f"{blob}\n{final_assistant_text}"
    return JUNO_WALLET_APPROVAL_UI_MARKER in combined


def should_show_wallet_approval_keyboard(
    blob: str,
    final_assistant_text: str,
    wallet_approval_supervisor_tools: frozenset[str],
) -> bool:
    """Show Approve/Decline when tool output requests it (marker or legacy heuristics)."""
    if not wallet_approval_supervisor_tools:
        return False
    if has_structured_wallet_approval_marker(blob, final_assistant_text):
        return True
    if conversation_needs_approval_ui(blob):
        return True
    if assistant_promises_inline_approval_ui(final_assistant_text):
        return True
    combined = f"{blob}\n{final_assistant_text}"
    return conversation_needs_approval_ui(combined)


def mercury_approval_inline_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Approve", callback_data="apr:yes"),
                InlineKeyboardButton("Decline", callback_data="apr:no"),
            ],
        ],
    )


__all__ = [
    "TELEGRAM_AFTER_APPROVE_SYSTEM",
    "MERCURY_INLINE_CONTINUE_TEXT",
    "approval_state_value",
    "assistant_promises_inline_approval_ui",
    "conversation_needs_approval_ui",
    "has_structured_wallet_approval_marker",
    "mercury_approval_inline_keyboard",
    "should_show_wallet_approval_keyboard",
]
