# Subagents and runtime wiring

## Overview

- **`juno.runtime.factory`** — Discovers `assistants/*.yaml`, resolves HTTP base URLs (manifest `base_url_env` first, then Mercury-specific `Settings` fallback), builds Mercury sub-graphs, and returns a **`SupervisorBundle`** (compiled supervisor + metadata).
- **`juno.agents.build_supervisor`** — Takes a sequence of **`SubagentSpec`** values. Each spec becomes one top-level supervisor tool with a stable `name` (e.g. `mercury`). Tool descriptions are appended to the supervisor Markdown at startup.
- **`juno.agents.registry.SubagentSpec`** — `name`, `description`, `graph`, optional `state_keys` forwarded into the sub-agent invoke, `resume_instruction` (e.g. after Telegram approve), and **`supports_wallet_approval_ui`** for Telegram gating.

## Adding a new specialist (sketch)

1. Add `assistants/<assistant>.yaml` (+ optional `<assistant>.md`) with a distinct `runner` value.
2. Extend **`build_subagent_specs`** in [`src/juno/runtime/factory.py`](../src/juno/runtime/factory.py): branch on `manifest.runner`, construct the HTTP or other client, call a new `build_<assistant>_subagent(...)`, return a **`SubagentSpec`** with a unique `name` and `description`.
3. Set **`supports_wallet_approval_ui`** to `True` only if the Telegram Approve/Decline flow applies; otherwise the inline keyboard stays off even if unrelated text matches legacy heuristics.
4. Add tests mirroring `tests/test_agents.py` / `tests/test_runtime_factory.py`.

## Wallet approval UI

- Tool text for Mercury wallet-gated turns prefixes **`JUNO_WALLET_APPROVAL_UI:1`** (see [`src/juno/approval_markers.py`](../src/juno/approval_markers.py)) so Telegram can detect approval without relying only on free-form phrases.
- **Legacy phrase heuristics** remain as a fallback when that marker is absent.
- Telegram stores pending approve/deny in **`Application.bot_data`** via [`src/juno/telegram/approval_state.py`](../src/juno/telegram/approval_state.py).

## Telegram layout

- [`src/juno/telegram/bot.py`](../src/juno/telegram/bot.py) — composition: identity, `build_supervisor_bundle`, handler registration, polling.
- [`src/juno/telegram/handlers.py`](../src/juno/telegram/handlers.py) — commands and message/callback handlers.
- [`src/juno/telegram/turn.py`](../src/juno/telegram/turn.py) — one supervisor `invoke` and outbound messages.
- [`src/juno/telegram/approval_ui.py`](../src/juno/telegram/approval_ui.py) — keyboard decision logic.
- [`src/juno/telegram/messages.py`](../src/juno/telegram/messages.py) — LangChain message → text helpers.
