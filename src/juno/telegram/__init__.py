"""Telegram entrypoints for Juno."""

from __future__ import annotations

from typing import Any

__all__ = ["extract_approval_token", "main", "run_bot"]


def __getattr__(name: str) -> Any:
    if name == "extract_approval_token":
        from juno.telegram.parsing import extract_approval_token as et

        return et
    if name == "main":
        from juno.telegram.bot import main as m

        return m
    if name == "run_bot":
        from juno.telegram.bot import run_bot as r

        return r
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
