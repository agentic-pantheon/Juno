"""Lightweight tests for Telegram helpers (no live Telegram API)."""

from __future__ import annotations

from juno.telegram.parsing import extract_approval_token


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
