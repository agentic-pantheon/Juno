"""Load, save, merge, and format file-backed user memory profiles."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from juno.memory.profile import UserMemoryProfile

logger = logging.getLogger(__name__)

_MEMORY_FILENAME_SUFFIX = ".json"
_MAX_PROMPT_CHARS = 2048


def _memory_stem_for_user_id(user_id: str) -> str:
    """Deterministic, filesystem-safe stem derived from ``user_id``."""
    digest = hashlib.sha256(user_id.encode("utf-8")).hexdigest()
    return digest


def memory_file_path(memory_dir: Path, user_id: str) -> Path:
    """Resolved JSON path for ``user_id`` under ``memory_dir``."""
    stem = _memory_stem_for_user_id(user_id)
    return memory_dir / f"{stem}{_MEMORY_FILENAME_SUFFIX}"


def load_user_memory(memory_dir: Path, user_id: str) -> UserMemoryProfile:
    """Load profile from disk; if the file is missing, return defaults."""
    path = memory_file_path(memory_dir, user_id)
    if not path.is_file():
        return UserMemoryProfile()
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
        return UserMemoryProfile.model_validate(data)
    except (OSError, json.JSONDecodeError, ValidationError):
        logger.warning("Ignoring unreadable long-term memory profile at %s", path, exc_info=True)
        return UserMemoryProfile()


def save_user_memory(memory_dir: Path, user_id: str, profile: UserMemoryProfile) -> None:
    """Persist ``profile`` with atomic replace (temp file in same directory)."""
    memory_dir.mkdir(parents=True, exist_ok=True)
    path = memory_file_path(memory_dir, user_id)
    payload = profile.model_dump_json(indent=2, exclude_none=True).encode("utf-8")
    fd, tmp = tempfile.mkstemp(
        dir=memory_dir,
        prefix=".tmp_memory_",
        suffix=_MEMORY_FILENAME_SUFFIX,
    )
    try:
        with os.fdopen(fd, "wb") as fp:
            fp.write(payload)
            fp.flush()
            os.fsync(fp.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def merge_user_memory(
    memory_dir: Path,
    user_id: str,
    updates: Mapping[str, Any] | None = None,
    **kwargs: Any,
) -> UserMemoryProfile:
    """Apply partial updates; only non-``None`` values overwrite. Result is persisted."""
    patch: dict[str, Any] = {}
    if updates:
        patch.update(dict(updates))
    patch.update(kwargs)

    current = load_user_memory(memory_dir, user_id)
    allowed = UserMemoryProfile.model_fields
    applied: dict[str, Any] = {}
    for key, value in patch.items():
        if key not in allowed:
            msg = f"Unknown UserMemoryProfile field: {key!r}"
            raise ValueError(msg)
        if value is None:
            continue
        applied[key] = value

    merged = UserMemoryProfile.model_validate({**current.model_dump(), **applied})
    save_user_memory(memory_dir, user_id, merged)
    return merged


def format_user_memory_for_prompt(
    profile: UserMemoryProfile,
    *,
    max_chars: int = _MAX_PROMPT_CHARS,
) -> str:
    """Plain markdown block: always includes effective tone; skips empty fields."""
    raw_tone = (profile.tone or "").strip()
    tone = raw_tone or "concise"
    lines: list[str] = [
        "### User memory",
        "",
        f"- **Tone:** {tone}",
    ]
    fields: tuple[tuple[str, str | None], ...] = (
        ("User name", profile.user_name),
        ("Agent name", profile.agent_name),
        ("Wallet address", profile.wallet_address),
        ("Mission", profile.mission),
    )
    for label, value in fields:
        if value is None:
            continue
        text = str(value).strip()
        if not text:
            continue
        lines.append(f"- **{label}:** {text}")

    out = "\n".join(lines)
    if len(out) <= max_chars:
        return out
    return f"{out[: max_chars - 3].rstrip()}..."
