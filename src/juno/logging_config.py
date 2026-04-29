"""Process-wide logging: Rich colored console, optional plain mode, trace id context."""

from __future__ import annotations

import contextvars
import logging
import os
import sys
from collections.abc import Generator
from contextlib import contextmanager

juno_trace_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("juno_trace_id", default=None)


def get_trace_id() -> str | None:
    return juno_trace_id_var.get()


@contextmanager
def juno_trace_scope(trace_id: str) -> Generator[None, None, None]:
    token = juno_trace_id_var.set(trace_id)
    try:
        yield
    finally:
        juno_trace_id_var.reset(token)


def _stderr_color_enabled() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("JUNO_LOG_COLOR", "").strip().lower() in ("0", "false", "no"):
        return False
    return sys.stderr.isatty()


def configure_logging() -> None:
    """Configure root logging once (Rich when TTY and color allowed, else plain StreamHandler)."""
    level_name = os.environ.get("JUNO_LOG_LEVEL", "INFO").strip().upper() or "INFO"
    level = getattr(logging, level_name, logging.INFO)

    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(level)

    if _stderr_color_enabled():
        from rich.logging import RichHandler

        handler: logging.Handler = RichHandler(
            rich_tracebacks=True,
            show_path=False,
            markup=False,
            show_time=True,
            omit_repeated_times=False,
        )
    else:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))

    handler.setLevel(level)
    root.addHandler(handler)


__all__ = [
    "configure_logging",
    "get_trace_id",
    "juno_trace_id_var",
    "juno_trace_scope",
]
