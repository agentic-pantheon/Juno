"""Tests for Telegram MarkdownV2 escaping and send/edit wrappers."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, call

import pytest
from telegram.constants import ParseMode
from telegram.error import BadRequest

from juno.telegram.formatting import (
    bold_md_v2,
    bot_edit_message_text_markdown_v2,
    escape_md_v2,
    inline_code_md_v2,
    model_markdown_like_to_telegram_html,
    reply_text_markdown_v2,
    send_assistant_reply_html_safe,
    send_message_markdown_v2,
    send_user_text_markdown_v2_safe,
)
from juno.telegram.formatting import edit_message_text_markdown_v2 as edit_md_v2


def test_escape_md_v2_escapes_specials() -> None:
    assert escape_md_v2("! * _|`") == r"\! \* \_\|\`"


def test_escape_md_v2_period_and_hyphen() -> None:
    assert escape_md_v2("1.0-beta") == r"1\.0\-beta"


def test_bold_md_v2_escapes_inner() -> None:
    assert bold_md_v2("a*b") == r"*a\*b*"


def test_inline_code_md_v2_backtick_and_slash() -> None:
    assert inline_code_md_v2("a`b") == r"`a\`b`"
    assert inline_code_md_v2(r"a\b") == r"`a\\b`"


def test_inline_code_md_v2_strips_newlines() -> None:
    assert inline_code_md_v2("a\nb") == "`a b`"


@pytest.mark.asyncio
async def test_reply_text_markdown_v2_forces_parse_mode() -> None:
    message = MagicMock()
    message.reply_text = AsyncMock(return_value=MagicMock())
    await reply_text_markdown_v2(message, "x")
    message.reply_text.assert_awaited_once_with("x", parse_mode=ParseMode.MARKDOWN_V2)


@pytest.mark.asyncio
async def test_send_message_markdown_v2_forces_parse_mode() -> None:
    bot = MagicMock()
    bot.send_message = AsyncMock(return_value=MagicMock())
    await send_message_markdown_v2(bot, 1, "hi", disable_notification=True)
    bot.send_message.assert_awaited_once_with(
        chat_id=1,
        text="hi",
        disable_notification=True,
        parse_mode=ParseMode.MARKDOWN_V2,
    )


@pytest.mark.asyncio
async def test_edit_message_text_markdown_v2_forces_parse_mode() -> None:
    message = MagicMock()
    message.edit_text = AsyncMock(return_value=MagicMock())
    await edit_md_v2(message, "y")
    message.edit_text.assert_awaited_once_with(text="y", parse_mode=ParseMode.MARKDOWN_V2)


def test_model_markdown_like_bold_and_hyphen_bullet() -> None:
    html = model_markdown_like_to_telegram_html("**Ethereum**\n- 0.1 ETH")
    assert "<b>Ethereum</b>" in html
    assert "• 0.1 ETH" in html
    assert "**" not in html


def test_model_markdown_like_strips_atx_heading() -> None:
    html = model_markdown_like_to_telegram_html("### Section\nbody")
    assert "###" not in html
    assert "Section" in html


def test_model_markdown_escapes_angle_brackets_in_plain_text() -> None:
    html = model_markdown_like_to_telegram_html("a < b & c")
    assert "<" not in html or "&lt;" in html
    assert "&lt;" in html


@pytest.mark.asyncio
async def test_send_assistant_reply_html_safe_sets_html_parse_mode() -> None:
    bot = MagicMock()
    bot.send_message = AsyncMock(return_value=MagicMock())
    await send_assistant_reply_html_safe(bot, 7, "**hi**")
    bot.send_message.assert_awaited_once()
    kwargs = bot.send_message.await_args.kwargs
    assert kwargs["parse_mode"] == ParseMode.HTML
    assert "<b>hi</b>" in kwargs["text"]


@pytest.mark.asyncio
async def test_send_user_text_markdown_v2_safe_falls_back_on_bad_request() -> None:
    bot = MagicMock()
    bot.send_message = AsyncMock(side_effect=[BadRequest("parse"), MagicMock()])
    await send_user_text_markdown_v2_safe(bot, 1, "plain * ok")
    assert bot.send_message.await_count == 2
    first = bot.send_message.await_args_list[0]
    assert first.kwargs["chat_id"] == 1 and first.kwargs["parse_mode"] == ParseMode.MARKDOWN_V2
    second = bot.send_message.await_args_list[1]
    assert second == call(chat_id=1, text="plain * ok", parse_mode=None)


@pytest.mark.asyncio
async def test_bot_edit_message_text_markdown_v2_forces_parse_mode() -> None:
    bot = MagicMock()
    bot.edit_message_text = AsyncMock(return_value=MagicMock())
    await bot_edit_message_text_markdown_v2(bot, 2, 99, "z")
    bot.edit_message_text.assert_awaited_once_with(
        chat_id=2,
        message_id=99,
        text="z",
        parse_mode=ParseMode.MARKDOWN_V2,
    )
