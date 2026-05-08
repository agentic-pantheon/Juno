"""Juno Settings: Mercury-oriented env aliases (passed through to Mercury's Juno plugin)."""

import pytest

from juno.settings import Settings


def test_settings_mercury_runner_mode_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MERCURY_RUNNER_MODE", "local")
    s = Settings()
    assert s.mercury_runner_mode == "local"


def test_settings_mercury_runner_mode_juno_alias(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MERCURY_RUNNER_MODE", raising=False)
    monkeypatch.setenv("JUNO_MERCURY_RUNNER_MODE", "local")
    s = Settings()
    assert s.mercury_runner_mode == "local"
