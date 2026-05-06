"""Pydantic model for persisted user-scoped long-term memory."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class UserMemoryProfile(BaseModel):
    """Fixed-field profile stored as one JSON file per Telegram user."""

    model_config = ConfigDict(extra="ignore")

    user_name: str | None = Field(default=None, description="How to address the user.")
    agent_name: str | None = Field(default=None, description="Preferred agent / assistant name.")
    wallet_address: str | None = Field(default=None, description="Optional on-chain address.")
    mission: str | None = Field(default=None, description="Standing goals or mission text.")
    tone: str = Field(default="concise", description="Style hint for replies (default concise).")
