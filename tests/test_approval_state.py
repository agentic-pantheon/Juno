"""Tests for Telegram approval state in ``bot_data``."""

from juno.telegram.approval_state import (
    get_last_approval_token,
    pop_pending_approval,
    set_last_approval_token,
    set_pending_approval,
)


def test_pending_approval_roundtrip() -> None:
    bot_data: dict = {}
    set_pending_approval(bot_data, 42, "approved:tok1")
    assert pop_pending_approval(bot_data, 42) == "approved:tok1"
    assert pop_pending_approval(bot_data, 42) is None


def test_last_approval_token_roundtrip() -> None:
    bot_data: dict = {}
    set_last_approval_token(bot_data, 7, "idem-1")
    assert get_last_approval_token(bot_data, 7) == "idem-1"
    set_last_approval_token(bot_data, 7, None)
    assert get_last_approval_token(bot_data, 7) is None

