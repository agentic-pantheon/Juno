"""Lightweight tests for Telegram helpers (no live Telegram API)."""

from __future__ import annotations

from juno.telegram.approval_ui import (
    assistant_promises_inline_approval_ui,
    conversation_needs_approval_ui,
    should_show_wallet_approval_keyboard,
)
from juno.telegram.parsing import (
    extract_approval_correlation_id,
    extract_approval_token,
    extract_idempotency_key,
)


def test_extract_approval_token_single_quoted() -> None:
    text = (
        "Wallet approval required.\n"
        "approval_token='tok_abc'\n"
        "approval_id='id1'\n"
    )
    assert extract_approval_token(text) == "tok_abc"


def test_extract_approval_token_double_quoted() -> None:
    text = 'approval_token="tok_xyz"'
    assert extract_approval_token(text) == "tok_xyz"


def test_extract_approval_token_missing() -> None:
    assert extract_approval_token("no token here") is None
    assert extract_approval_token("") is None


def test_extract_idempotency_key_json() -> None:
    text = '{"status": "approval_required", "idempotency_key": "transfer-20230428-001"}'
    assert extract_idempotency_key(text) == "transfer-20230428-001"


def test_extract_approval_correlation_id_prefers_idem() -> None:
    text = (
        'idempotency_key="swap-1"\n'
        "approval_token='tok_legacy'\n"
    )
    assert extract_approval_correlation_id(text) == "swap-1"


def test_conversation_needs_approval_mercury_phrases() -> None:
    assert conversation_needs_approval_ui("Human approval is required for ERC20 transfers.")
    assert conversation_needs_approval_ui('{"status": "approval_required"}')
    assert not conversation_needs_approval_ui("Transfer complete.")


def test_assistant_promises_inline_approval_ui() -> None:
    assert assistant_promises_inline_approval_ui(
        "Please tap the **Approve** button in the approval prompt that appeared in this chat.",
    )
    assert not assistant_promises_inline_approval_ui("No approval needed for this read.")


def test_should_show_mercury_approval_keyboard_heuristic() -> None:
    names = frozenset({"mercury"})
    assert should_show_wallet_approval_keyboard("", "Tap the Approve button in this chat.", names)
    assert not should_show_wallet_approval_keyboard("", "Here is your balance: 1 USDC.", names)
    assert not should_show_wallet_approval_keyboard(
        "Wallet approval required.",
        "",
        frozenset(),
    )


def test_should_show_wallet_approval_keyboard_structured_marker() -> None:
    from juno.approval_markers import JUNO_WALLET_APPROVAL_UI_MARKER

    names = frozenset({"mercury"})
    assert should_show_wallet_approval_keyboard(f"{JUNO_WALLET_APPROVAL_UI_MARKER}\n", "", names)
    assert should_show_wallet_approval_keyboard("", "", frozenset()) is False
