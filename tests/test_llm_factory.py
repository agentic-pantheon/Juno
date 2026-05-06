"""Tests for :mod:`juno.llm.factory`."""

from __future__ import annotations

import pytest
from langchain_openai import ChatOpenAI

from juno.llm.factory import build_agent_chat_model
from juno.settings import Settings


def test_standard_mode_returns_model_string() -> None:
    s = Settings.model_construct(
        juno_use_shroud=False,
        openai_model="openai:gpt-4o-mini",
    )
    assert build_agent_chat_model(s) == "openai:gpt-4o-mini"


def test_shroud_mode_builds_chat_openai_with_headers(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("TEST_SHROUD_AGENT_KEY", "agent:stub")

    s = Settings.model_construct(
        juno_use_shroud=True,
        juno_llm_base_url="https://shroud.example/v1",
        juno_shroud_provider="openai",
        juno_shroud_agent_key_env="TEST_SHROUD_AGENT_KEY",
        juno_shroud_model_header=True,
        openai_model="openai:gpt-4o-mini",
    )
    model = build_agent_chat_model(s)
    assert isinstance(model, ChatOpenAI)
    assert model.openai_api_base == "https://shroud.example/v1"
    assert model.model_name == "gpt-4o-mini"
    assert model.default_headers["X-Shroud-Agent-Key"] == "agent:stub"
    assert model.default_headers["X-Shroud-Provider"] == "openai"
    assert model.default_headers["X-Shroud-Model"] == "gpt-4o-mini"


def test_shroud_mode_omits_model_header_when_disabled(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("TEST_SHROUD_AGENT_KEY", "k")

    s = Settings.model_construct(
        juno_use_shroud=True,
        juno_shroud_model_header=False,
        juno_shroud_agent_key_env="TEST_SHROUD_AGENT_KEY",
        openai_model="gpt-5",
    )
    model = build_agent_chat_model(s)
    assert isinstance(model, ChatOpenAI)
    assert "X-Shroud-Model" not in model.default_headers


def test_shroud_mode_raises_when_agent_key_missing(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.delenv("MISSING_SHROUD_KEY", raising=False)

    s = Settings.model_construct(
        juno_use_shroud=True,
        juno_shroud_agent_key_env="MISSING_SHROUD_KEY",
        openai_model="openai:gpt-4o-mini",
    )
    with pytest.raises(ValueError, match="MISSING_SHROUD_KEY") as excinfo:
        build_agent_chat_model(s)
    assert "ocv_" not in str(excinfo.value)
