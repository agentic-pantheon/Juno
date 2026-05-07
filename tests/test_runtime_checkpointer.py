"""Supervisor checkpointer: in-memory fallback and Postgres saver lifecycle."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from langgraph.checkpoint.memory import InMemorySaver

from juno.runtime.checkpointer import supervisor_checkpointer
from juno.settings import Settings


def test_supervisor_checkpointer_empty_url_yields_in_memory() -> None:
    s = Settings(juno_checkpointer_database_url="")
    with supervisor_checkpointer(s) as cp:
        assert isinstance(cp, InMemorySaver)


def test_supervisor_checkpointer_whitespace_only_yields_in_memory() -> None:
    s = Settings(juno_checkpointer_database_url="   \t  ")
    with supervisor_checkpointer(s) as cp:
        assert isinstance(cp, InMemorySaver)


def test_supervisor_checkpointer_postgres_opens_setup_and_closes() -> None:
    raw = "  postgresql://u:p@db.example:5432/app  "
    stripped = raw.strip()
    mock_saver = MagicMock()
    mock_ctx = MagicMock()
    mock_ctx.__enter__.return_value = mock_saver
    mock_ctx.__exit__.return_value = None

    with patch("juno.runtime.checkpointer.PostgresSaver") as MockPG:
        MockPG.from_conn_string.return_value = mock_ctx
        s = Settings(juno_checkpointer_database_url=raw)
        with supervisor_checkpointer(s) as cp:
            assert cp is mock_saver
            mock_saver.setup.assert_called_once()

        MockPG.from_conn_string.assert_called_once_with(stripped)
        mock_ctx.__enter__.assert_called_once()
        mock_ctx.__exit__.assert_called_once()
