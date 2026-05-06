"""Tests for file-backed long-term memory (profile, store, supervisor tool, middleware)."""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path

import httpx
import pytest
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from juno.agents import build_mercury_subagent, build_supervisor, default_mercury_subagent_spec
from juno.assistants.loader import AssistantManifest
from juno.assistants.mercury_runner import MercuryAssistantRunner
from juno.memory import UserMemoryProfile, format_user_memory_for_prompt, load_user_memory, merge_user_memory, save_user_memory
from juno.memory.store import memory_file_path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SUPERVISOR_PROMPT_PATH = _REPO_ROOT / "config" / "juno.supervisor.md"


class FakeMessagesListChatModelWithTools(FakeMessagesListChatModel):
    """:class:`FakeMessagesListChatModel` does not implement ``bind_tools``; agents require it."""

    def bind_tools(self, tools, *, tool_choice=None, **kwargs):  # type: ignore[no-untyped-def]
        return self


def _thread_config() -> dict:
    return {"configurable": {"thread_id": f"test-{uuid.uuid4()}"}}


def _hex_stem_json_files(directory: Path) -> list[Path]:
    return [p for p in directory.glob("*.json") if re.fullmatch(r"[0-9a-f]{64}\.json", p.name)]


def test_load_user_memory_missing_file_default_tone_concise(tmp_path: Path) -> None:
    profile = load_user_memory(tmp_path, "any-user-id")
    assert profile.tone == "concise"
    assert profile.user_name is None


def test_load_user_memory_empty_json_object_default_tone_concise(tmp_path: Path) -> None:
    uid = "u-empty-json"
    path = memory_file_path(tmp_path, uid)
    tmp_path.mkdir(parents=True, exist_ok=True)
    path.write_text("{}", encoding="utf-8")
    profile = load_user_memory(tmp_path, uid)
    assert profile.tone == "concise"


def test_load_user_memory_invalid_json_falls_back_to_default(tmp_path: Path) -> None:
    uid = "u-invalid-json"
    path = memory_file_path(tmp_path, uid)
    tmp_path.mkdir(parents=True, exist_ok=True)
    path.write_text('{"tone": null', encoding="utf-8")

    profile = load_user_memory(tmp_path, uid)

    assert profile.tone == "concise"
    assert profile.user_name is None


def test_save_merge_round_trip_persist_fields_and_safe_filename(tmp_path: Path) -> None:
    uid = "telegram|12345"
    original = UserMemoryProfile(
        user_name="Ada",
        agent_name="Nova",
        wallet_address="0xdeadbeef",
        mission="Study agents.",
        tone="friendly",
    )
    save_user_memory(tmp_path, uid, original)

    hashed = _hex_stem_json_files(tmp_path)
    assert len(hashed) == 1
    stem = hashed[0].stem
    assert len(stem) == 64
    assert re.fullmatch(r"[0-9a-f]{64}", stem)

    merged = merge_user_memory(
        tmp_path,
        uid,
        mission="Updated mission text.",
        user_name=None,
    )
    assert merged.user_name == "Ada"
    assert merged.agent_name == "Nova"
    assert merged.wallet_address == "0xdeadbeef"
    assert merged.tone == "friendly"
    assert merged.mission == "Updated mission text."

    loaded = load_user_memory(tmp_path, uid)
    assert loaded == merged

    assert memory_file_path(tmp_path, uid) == hashed[0]


def test_merge_ignores_none_and_rejects_unknown_fields(tmp_path: Path) -> None:
    uid = "merge-user"
    save_user_memory(
        tmp_path,
        uid,
        UserMemoryProfile(user_name="First", tone="friendly", mission="stay"),
    )
    merged = merge_user_memory(
        tmp_path,
        uid,
        agent_name=None,
        user_name="Second",
        mission=None,
        tone=None,
        wallet_address=None,
    )
    assert merged.user_name == "Second"
    assert merged.mission == "stay"
    assert merged.agent_name is None
    assert merged.tone == "friendly"

    with pytest.raises(ValueError, match="Unknown UserMemoryProfile field"):
        merge_user_memory(tmp_path, uid, not_a_real_field="nope")


@pytest.mark.parametrize(
    ("profile", "must_contain", "must_not_contain"),
    [
        (
            UserMemoryProfile(),
            ("### User memory", "**Tone:** concise"),
            ("**User name:**", "**Agent name:**", "**Mission:**"),
        ),
        (
            UserMemoryProfile(user_name="", mission="   ", tone="witty"),
            ("### User memory", "**Tone:** witty"),
            ("**User name:**", "**Mission:**"),
        ),
        (
            UserMemoryProfile(
                user_name="Pat",
                agent_name="Juno",
                wallet_address="0xw",
                mission="Ship",
                tone="professional",
            ),
            (
                "**Tone:** professional",
                "**User name:** Pat",
                "**Agent name:** Juno",
                "**Wallet address:** 0xw",
                "**Mission:** Ship",
            ),
            (),
        ),
    ],
)
def test_format_user_memory_for_prompt_tone_and_nonempty_fields_only(
    profile: UserMemoryProfile,
    must_contain: tuple[str, ...],
    must_not_contain: tuple[str, ...],
) -> None:
    text = format_user_memory_for_prompt(profile)
    for needle in must_contain:
        assert needle in text, text
    for needle in must_not_contain:
        assert needle not in text, text


def test_format_user_memory_for_prompt_fallback_tone_when_blank() -> None:
    text = format_user_memory_for_prompt(UserMemoryProfile.model_validate({"tone": "  "}))
    assert "**Tone:** concise" in text


def test_supervisor_update_user_memory_persists_profile_json(tmp_path: Path) -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        raise AssertionError("Mercury should not be called")

    runner = MercuryAssistantRunner(
        "https://unused.test",
        transport=httpx.MockTransport(boom),
        http_path="/v1/agent",
        request_body_mode="flat",
    )
    manifest = AssistantManifest(runner="mercury", base_url_env="X", system_prompt="Sub")
    sub = build_mercury_subagent(
        model=FakeMessagesListChatModelWithTools(responses=[AIMessage(content="noop")]),
        manifest=manifest,
        runner=runner,
    )

    uid = "ltm-tool-user-1"
    responses = [
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "update_user_memory",
                    "args": {"user_name": "Casey", "tone": "technical"},
                    "id": "mem-1",
                    "type": "tool_call",
                }
            ],
        ),
        AIMessage(content="stored."),
    ]
    model = FakeMessagesListChatModelWithTools(responses=responses)
    sup = build_supervisor(
        model=model,
        subagents=(default_mercury_subagent_spec(sub),),
        supervisor_prompt_path=_SUPERVISOR_PROMPT_PATH,
        long_term_memory_dir=tmp_path,
    )

    out = sup.invoke(
        {"messages": [HumanMessage("save prefs")], "user_id": uid},
        _thread_config(),
    )
    assert out["messages"][-1].content == "stored."

    files = _hex_stem_json_files(tmp_path)
    assert len(files) == 1
    disk = json.loads(files[0].read_text(encoding="utf-8"))
    assert disk.get("user_name") == "Casey"
    assert disk.get("tone") == "technical"
    assert load_user_memory(tmp_path, uid).user_name == "Casey"


def _capturing_fake_with_tools(
    responses: list[AIMessage],
    captures: list[list],
) -> FakeMessagesListChatModelWithTools:
    """Subclass inside factory so pydantic ignores custom capture state."""

    class _Capturing(FakeMessagesListChatModelWithTools):
        def _generate(self, messages: list, stop=None, run_manager=None, **kwargs):  # type: ignore[no-untyped-def]
            captures.append(list(messages))
            return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)

    return _Capturing(responses=responses)


def _first_system_content(messages: list) -> str:
    for msg in messages:
        if isinstance(msg, SystemMessage):
            c = msg.content
            return c if isinstance(c, str) else str(c)
    return ""


def test_long_term_memory_middleware_injects_profile_with_default_and_saved_fields(tmp_path: Path) -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        raise AssertionError("Mercury should not be called")

    runner = MercuryAssistantRunner(
        "https://unused.test",
        transport=httpx.MockTransport(boom),
        http_path="/v1/agent",
        request_body_mode="flat",
    )
    manifest = AssistantManifest(runner="mercury", base_url_env="X", system_prompt="Sub")
    sub = build_mercury_subagent(
        model=FakeMessagesListChatModelWithTools(responses=[AIMessage(content="noop")]),
        manifest=manifest,
        runner=runner,
    )

    uid = uuid.uuid4().hex
    invocations: list[list] = []
    capturing_model = _capturing_fake_with_tools(
        responses=[AIMessage(content="phase-a"), AIMessage(content="phase-b")],
        captures=invocations,
    )
    sup = build_supervisor(
        model=capturing_model,
        subagents=(default_mercury_subagent_spec(sub),),
        supervisor_prompt_path=_SUPERVISOR_PROMPT_PATH,
        long_term_memory_dir=tmp_path,
    )
    cfg = _thread_config()

    sup.invoke({"messages": [HumanMessage("one")], "user_id": uid}, cfg)
    sys_a = _first_system_content(invocations[-1])
    assert "## Long-term profile" in sys_a
    assert "**Tone:** concise" in sys_a

    merge_user_memory(
        tmp_path,
        uid,
        user_name="Ravi",
        mission="Test middleware injection.",
        tone="playful",
    )

    capturing_model.i = 0
    invocations.clear()
    sup.invoke({"messages": [HumanMessage("two")], "user_id": uid}, cfg)

    sys_b = _first_system_content(invocations[-1])
    assert "## Long-term profile" in sys_b
    assert "**Tone:** playful" in sys_b
    assert "**User name:** Ravi" in sys_b
    assert "**Mission:** Test middleware injection." in sys_b
