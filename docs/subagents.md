# Subagents and runtime wiring

## Overview

- **`juno.plugins`** — Discovers setuptools entry points in group **`juno.assistants`**, applies **`JUNO_DISABLED_ASSISTANTS`**, and returns **`SubagentSpec`** instances from each enabled plugin.
- **`juno.runtime.factory`** — Calls **`load_assistant_specs`**, builds the supervisor graph, and returns a **`SupervisorBundle`** (compiled supervisor + **`wallet_approval_supervisor_tool_names`** metadata for Telegram).
- **`juno.agents.build_supervisor`** — Takes a sequence of **`SubagentSpec`** values. Each spec becomes one top-level supervisor tool with a stable `name` (e.g. `mercury`). Tool descriptions are appended to the supervisor Markdown at startup.
- **`juno.agents.registry.SubagentSpec`** — `name`, `description`, `graph`, optional `state_keys` forwarded into the sub-agent invoke, `resume_instruction` (e.g. after Telegram approve), and **`supports_wallet_approval_ui`** for Telegram gating.
- **Optional YAML** — [`juno.assistants.loader.discover_assistants`](../src/juno/assistants/loader.py) can still read **`assistants/*.yaml`** for tooling; **plugins** own registration and prompts (see the **mercury** package for the reference implementation).

## Adding a new specialist (sketch)

1. In your installable package, implement a factory callable (e.g. `create_plugin(ctx: JunoPluginContext) -> Sequence[SubagentSpec]`).
2. Register it under **`[project.entry-points."juno.assistants"]`** in **`pyproject.toml`**.
3. Ensure **`SubagentSpec.name`** values are unique across all enabled plugins.
4. Set **`supports_wallet_approval_ui`** to `True` only if the Telegram Approve/Decline flow applies.
5. Add tests in your package; Juno covers discovery, disable list, and conflicts in **`tests/test_plugins.py`**.

## Wallet approval UI

- Tool text for Mercury wallet-gated turns prefixes **`JUNO_WALLET_APPROVAL_UI:1`** (see [`src/juno/approval_markers.py`](../src/juno/approval_markers.py)) so Telegram can detect approval without relying only on free-form phrases. The Mercury plugin emits this via **`mercury.juno.tool_text`**.
- **Legacy phrase heuristics** remain as a fallback when that marker is absent.
- Telegram stores pending approve/deny in **`Application.bot_data`** via [`src/juno/telegram/approval_state.py`](../src/juno/telegram/approval_state.py).

## Telegram layout

- [`src/juno/telegram/bot.py`](../src/juno/telegram/bot.py) — composition: identity, `build_supervisor_bundle`, handler registration, polling.
- [`src/juno/telegram/handlers.py`](../src/juno/telegram/handlers.py) — commands and message/callback handlers.
- [`src/juno/telegram/turn.py`](../src/juno/telegram/turn.py) — one supervisor `invoke` and outbound messages.
- [`src/juno/telegram/approval_ui.py`](../src/juno/telegram/approval_ui.py) — keyboard decision logic.
- [`src/juno/telegram/messages.py`](../src/juno/telegram/messages.py) — LangChain message → text helpers.
