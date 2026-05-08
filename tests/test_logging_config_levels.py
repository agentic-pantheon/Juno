"""Ensure default process log level favors DEBUG when unset."""

from __future__ import annotations

import logging

import pytest


def test_configure_logging_default_is_debug_when_env_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("JUNO_LOG_LEVEL", raising=False)
    from juno import logging_config

    logging_config.configure_logging()
    root = logging.getLogger()

    assert root.level == logging.DEBUG
