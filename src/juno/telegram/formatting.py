"""Telegram formatting: MarkdownV2 escaping, Markdown-like → HTML for model output, wrappers."""

from __future__ import annotations

import html
import re
import uuid
from typing import Any

from telegram import Bot, Message
from telegram.constants import ParseMode
from telegram.error import BadRequest

# Characters that must be escaped outside of explicit MarkdownV2 spans.
# https://core.telegram.org/bots/api#markdownv2-style
_MD_V2_ESCAPE_CHARS = r"_*[]()~`>#+-=|{}.!"


TELEGRAM_MAX_MESSAGE_LENGTH_CHARS = 4096


def clip_for_telegram(text: str) -> str:
    """Trim to Telegram's max message length; append ellipsis when clipped."""
    if len(text) <= TELEGRAM_MAX_MESSAGE_LENGTH_CHARS:
        return text
    return text[: TELEGRAM_MAX_MESSAGE_LENGTH_CHARS - 1] + "…"


def escape_telegram_html(text: str) -> str:
    """Escape ``&``, ``<``, ``>`` so text is safe inside Telegram HTML parse mode."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


_MODEL_BOLD_PAIR = re.compile(r"\*\*(.+?)\*\*", flags=re.DOTALL)
_ATX_HEADING_LINE = re.compile(r"(?m)^#{1,6}\s+(.*)$")


def _plain_model_segment_to_html(plain: str) -> str:
    """Normalize common Markdown-ish lines → Telegram HTML text (no structural tags).

    Stripped ATX ``# headings``, hyphen bullets become ``•`` for readability; then HTML escapes.
    """
    promoted = plain
    promoted = _ATX_HEADING_LINE.sub(r"\1", promoted)
    promoted = re.sub(r"(^|\n)(\s*)-\s+", r"\1\2• ", promoted)
    return escape_telegram_html(promoted)


def model_markdown_like_to_telegram_html(text: str) -> str:
    """Map subsets of model Markdown-ish output to Telegram HTML.

    Converts ``**bold**``, strips ATX heading markers, swaps ``- `` line bullets for ``•``,
    escapes ``<>&``. Not a full Markdown implementation.
    """
    if not text:
        return ""
    out: list[str] = []
    pos = 0
    for match in _MODEL_BOLD_PAIR.finditer(text):
        out.append(_plain_model_segment_to_html(text[pos : match.start()]))
        out.append(f"<b>{escape_telegram_html(match.group(1))}</b>")
        pos = match.end()
    out.append(_plain_model_segment_to_html(text[pos:]))
    return "".join(out)


def escape_md_v2(text: str) -> str:
    """Escape arbitrary user or model text so it is literal in MarkdownV2."""
    text = text.replace("\\", r"\\")
    for ch in _MD_V2_ESCAPE_CHARS:
        text = text.replace(ch, "\\" + ch)
    return text


def bold_md_v2(text: str) -> str:
    """Bold span: inner text is escaped, then wrapped in *...*."""
    return f"*{escape_md_v2(text)}*"


def italic_md_v2(text: str) -> str:
    """Italic span: inner text is escaped, then wrapped in _..._."""
    return f"_{escape_md_v2(text)}_"


def inline_code_md_v2(text: str) -> str:
    """Single backtick inline code; newlines stripped (inline code cannot span lines)."""
    text = text.replace("\n", " ").replace("\r", "")
    inner = text.replace("\\", r"\\").replace("`", r"\`")
    return f"`{inner}`"


async def reply_text_markdown_v2(message: Message, text: str, **kwargs: Any) -> Message:
    """``message.reply_text`` with :attr:`telegram.constants.ParseMode.MARKDOWN_V2`."""
    kwargs = {**kwargs, "parse_mode": ParseMode.MARKDOWN_V2}
    return await message.reply_text(text, **kwargs)


async def send_message_markdown_v2(
    bot: Bot,
    chat_id: int,
    text: str,
    **kwargs: Any,
) -> Message:
    """``bot.send_message`` with MarkdownV2."""
    kwargs = {**kwargs, "parse_mode": ParseMode.MARKDOWN_V2}
    return await bot.send_message(chat_id=chat_id, text=text, **kwargs)


async def edit_message_text_markdown_v2(message: Message, text: str, **kwargs: Any) -> Message:
    """``message.edit_text`` with MarkdownV2."""
    kwargs = {**kwargs, "parse_mode": ParseMode.MARKDOWN_V2}
    return await message.edit_text(text=text, **kwargs)


async def bot_edit_message_text_markdown_v2(
    bot: Bot,
    chat_id: int,
    message_id: int,
    text: str,
    **kwargs: Any,
) -> Message:
    """``bot.edit_message_text`` with MarkdownV2."""
    kwargs = {**kwargs, "parse_mode": ParseMode.MARKDOWN_V2}
    return await bot.edit_message_text(
        chat_id=chat_id,
        message_id=message_id,
        text=text,
        **kwargs,
    )


async def send_message_html(
    bot: Bot,
    chat_id: int,
    text: str,
    **kwargs: Any,
) -> Message:
    """``bot.send_message`` with Telegram HTML entities."""
    kwargs = {**kwargs, "parse_mode": ParseMode.HTML}
    return await bot.send_message(chat_id=chat_id, text=text, **kwargs)


async def bot_edit_message_text_html(
    bot: Bot,
    chat_id: int,
    message_id: int,
    text: str,
    **kwargs: Any,
) -> Message:
    kwargs = {**kwargs, "parse_mode": ParseMode.HTML}
    return await bot.edit_message_text(
        chat_id=chat_id,
        message_id=message_id,
        text=text,
        **kwargs,
    )


async def reply_text_plain(message: Message, text: str, **kwargs: Any) -> Message:
    """Force plain text (no parse mode), for fallbacks next to MarkdownV2 paths."""
    kwargs = dict(kwargs)
    kwargs["parse_mode"] = None
    return await message.reply_text(text, **kwargs)


async def send_message_plain(
    bot: Bot,
    chat_id: int,
    text: str,
    **kwargs: Any,
) -> Message:
    """``bot.send_message`` without parse mode."""
    kwargs = dict(kwargs)
    kwargs["parse_mode"] = None
    return await bot.send_message(chat_id=chat_id, text=text, **kwargs)


async def edit_message_text_plain(message: Message, text: str, **kwargs: Any) -> Message:
    """``message.edit_text`` without parse mode."""
    kwargs = dict(kwargs)
    kwargs["parse_mode"] = None
    return await message.edit_text(text=text, **kwargs)


async def bot_edit_message_text_plain(
    bot: Bot,
    chat_id: int,
    message_id: int,
    text: str,
    **kwargs: Any,
) -> Message:
    """``bot.edit_message_text`` without parse mode."""
    kwargs = dict(kwargs)
    kwargs["parse_mode"] = None
    return await bot.edit_message_text(
        chat_id=chat_id,
        message_id=message_id,
        text=text,
        **kwargs,
    )


async def reply_user_text_markdown_v2_safe(message: Message, raw_text: str, **kwargs: Any) -> Message:
    """Send ``raw_text`` escaped for MarkdownV2; fallback to plain on entity parse failure."""
    try:
        return await reply_text_markdown_v2(message, escape_md_v2(raw_text), **kwargs)
    except BadRequest:
        return await reply_text_plain(message, raw_text, **kwargs)


async def send_user_text_markdown_v2_safe(
    bot: Bot,
    chat_id: int,
    raw_text: str,
    **kwargs: Any,
) -> Message:
    """Escapes ``raw_text`` for Telegram MarkdownV2, falling back to plain if parsing fails."""
    try:
        return await send_message_markdown_v2(
            bot,
            chat_id,
            escape_md_v2(raw_text),
            **kwargs,
        )
    except BadRequest:
        return await send_message_plain(bot, chat_id, raw_text, **kwargs)


async def send_assistant_reply_html_safe(
    bot: Bot,
    chat_id: int,
    raw_text: str,
    **kwargs: Any,
) -> Message:
    """Assistant / tool model text → Markdown-like subset as HTML; plain fallback."""
    html_body = clip_for_telegram(model_markdown_like_to_telegram_html(raw_text))
    plain_body = clip_for_telegram(raw_text)
    try:
        return await send_message_html(bot, chat_id, html_body, **kwargs)
    except BadRequest:
        return await send_message_plain(bot, chat_id, plain_body, **kwargs)


async def bot_edit_assistant_reply_html_safe(
    bot: Bot,
    chat_id: int,
    message_id: int,
    raw_text: str,
    **kwargs: Any,
) -> Message:
    html_body = clip_for_telegram(model_markdown_like_to_telegram_html(raw_text))
    plain_body = clip_for_telegram(raw_text)
    try:
        return await bot_edit_message_text_html(
            bot,
            chat_id,
            message_id,
            html_body,
            **kwargs,
        )
    except BadRequest:
        return await bot_edit_message_text_plain(
            bot,
            chat_id,
            message_id,
            plain_body,
            **kwargs,
        )


async def bot_edit_user_text_markdown_v2_safe(
    bot: Bot,
    chat_id: int,
    message_id: int,
    raw_text: str,
    **kwargs: Any,
) -> Message:
    """Edit with escaped MarkdownV2; fallback to plain if parsing fails."""
    try:
        return await bot_edit_message_text_markdown_v2(
            bot,
            chat_id,
            message_id,
            escape_md_v2(raw_text),
            **kwargs,
        )
    except BadRequest:
        return await bot_edit_message_text_plain(
            bot,
            chat_id,
            message_id,
            raw_text,
            **kwargs,
        )


# --- Rich Markdown-ish → HTML (tests / callers); broader than model_markdown_like_to_telegram_html ---

_HTML_STASH_RE = re.compile("\u2063([0-9a-f]{32})\u2063")


def _html_stash(stash_map: dict[str, str], content: str) -> str:
    token = f"\u2063{uuid.uuid4().hex}\u2063"
    stash_map[token] = content
    return token


def _tg_is_table_row(line: str) -> bool:
    s = line.strip()
    return s.count("|") >= 2


def _tg_is_separator_row(line: str) -> bool:
    s = line.strip()
    return bool(s) and bool(re.fullmatch(r"[|\s:\-]+", s)) and "-" in s


def _tg_apply_pipe_tables(text: str, stash_map: dict[str, str]) -> str:
    lines = text.split("\n")
    out: list[str] = []
    i = 0
    while i < len(lines):
        if _tg_is_table_row(lines[i]) and (
            (i + 1 < len(lines) and _tg_is_separator_row(lines[i + 1]))
            or (i + 1 < len(lines) and _tg_is_table_row(lines[i + 1]))
        ):
            block: list[str] = []
            while i < len(lines) and _tg_is_table_row(lines[i]):
                block.append(lines[i])
                i += 1
            joined = "\n".join(block)
            out.append(
                _html_stash(
                    stash_map,
                    "<pre>" + html.escape(joined) + "</pre>",
                ),
            )
            continue
        out.append(lines[i])
        i += 1
    return "\n".join(out)


def _tg_apply_code_bold_italic(segment: str, inline_stash: dict[str, str]) -> str:
    def stash(inner: str) -> str:
        return _html_stash(inline_stash, inner)

    s = segment
    s = re.sub(
        r"(?<!`)`([^`\n]+)`(?!`)",
        lambda m: stash("<code>" + html.escape(m.group(1)) + "</code>"),
        s,
    )
    s = re.sub(
        r"\*\*([^*]+)\*\*",
        lambda m: stash("<b>" + html.escape(m.group(1)) + "</b>"),
        s,
    )
    s = re.sub(
        r"__([^_]+)__",
        lambda m: stash("<b>" + html.escape(m.group(1)) + "</b>"),
        s,
    )
    s = re.sub(
        r"(?<!\*)\*([^*\n]+)\*(?!\*)",
        lambda m: stash("<i>" + html.escape(m.group(1)) + "</i>"),
        s,
    )
    return s


def _tg_commit_stashes(s: str, stash_map: dict[str, str]) -> str:
    s = html.escape(s)
    for key, frag in stash_map.items():
        s = s.replace(key, frag)
    return s


def _tg_format_plain_segment(segment: str) -> str:
    if not segment:
        return segment
    inline_stash: dict[str, str] = {}

    def stash(inner: str) -> str:
        return _html_stash(inline_stash, inner)

    def link_repl(m: re.Match[str]) -> str:
        url = m.group(2).strip()
        if not url.startswith(("http://", "https://")):
            return m.group(0)
        lab_stash: dict[str, str] = {}
        labeled = _tg_apply_code_bold_italic(m.group(1), lab_stash)
        labeled = _tg_commit_stashes(labeled, lab_stash)
        safe_url = html.escape(url, quote=True)
        return stash(f'<a href="{safe_url}">{labeled}</a>')

    s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", link_repl, segment)
    s = _tg_apply_code_bold_italic(s, inline_stash)
    return _tg_commit_stashes(s, inline_stash)


def _tg_interleave_stashes(text: str, stash_map: dict[str, str]) -> str:
    parts = _HTML_STASH_RE.split(text)
    out: list[str] = []
    for i, part in enumerate(parts):
        if i % 2 == 0:
            out.append(_tg_format_plain_segment(part))
        else:
            token = f"\u2063{part}\u2063"
            out.append(stash_map.get(token, html.escape(token)))
    return "".join(out)


def to_telegram_html(text: str) -> str:
    """Best-effort GFM-ish Markdown → Telegram HTML. Tables become monospace <pre> blocks."""
    if not text:
        return ""
    stash_map: dict[str, str] = {}
    s = text.replace("\r\n", "\n")
    s = re.sub(
        r"```(?:[\w-]*\n)?(.*?)```",
        lambda m: _html_stash(
            stash_map,
            "<pre>" + html.escape((m.group(1) or "").rstrip("\n")) + "</pre>",
        ),
        s,
        flags=re.DOTALL,
    )
    s = _tg_apply_pipe_tables(s, stash_map)
    return _tg_interleave_stashes(s, stash_map)


__all__ = [
    "TELEGRAM_MAX_MESSAGE_LENGTH_CHARS",
    "bold_md_v2",
    "bot_edit_assistant_reply_html_safe",
    "bot_edit_message_text_html",
    "bot_edit_message_text_markdown_v2",
    "bot_edit_message_text_plain",
    "bot_edit_user_text_markdown_v2_safe",
    "clip_for_telegram",
    "edit_message_text_markdown_v2",
    "edit_message_text_plain",
    "escape_md_v2",
    "inline_code_md_v2",
    "escape_telegram_html",
    "italic_md_v2",
    "model_markdown_like_to_telegram_html",
    "reply_text_markdown_v2",
    "reply_text_plain",
    "reply_user_text_markdown_v2_safe",
    "send_assistant_reply_html_safe",
    "send_message_html",
    "send_message_markdown_v2",
    "send_message_plain",
    "send_user_text_markdown_v2_safe",
    "to_telegram_html",
]
