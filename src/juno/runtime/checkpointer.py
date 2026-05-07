"""Supervisor checkpointer lifecycle: in-memory fallback or Postgres-backed saver."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.postgres import PostgresSaver

from juno.settings import Settings


@contextmanager
def supervisor_checkpointer(settings: Settings) -> Iterator[BaseCheckpointSaver]:
    """Open the configured checkpointer for the supervisor graph lifetime.

    When ``juno_checkpointer_database_url`` is empty after stripping, yields
    :class:`~langgraph.checkpoint.memory.InMemorySaver`. Otherwise opens
    :class:`~langgraph.checkpoint.postgres.PostgresSaver` from the DSN, runs
    ``setup()`` once, and yields the saver. The connection string is never logged
    or returned from this helper.
    """
    url = settings.juno_checkpointer_database_url.strip()
    if not url:
        yield InMemorySaver()
        return
    with PostgresSaver.from_conn_string(url) as saver:
        saver.setup()
        yield saver
