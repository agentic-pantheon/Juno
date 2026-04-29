"""Tests for Telegram error formatting."""

from juno.telegram.errors import format_agent_error


def test_format_agent_error_basic() -> None:
    msg = format_agent_error(ValueError("bad input"))
    assert "ValueError" in msg
    assert "bad input" in msg


def test_format_agent_error_redacts_groq_key() -> None:
    msg = format_agent_error(RuntimeError("failed gsk_abc123xyz secret"))
    assert "gsk_" not in msg
    assert "[redacted]" in msg
