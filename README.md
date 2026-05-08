# Juno

Telegram bot service that runs a **LangChain** supervisor and delegates assistant work to **Mercury**: either **over HTTP** to a Mercury API (**`MERCURY_RUNNER_MODE=http`**, default) or **in-process** against the **`mercury` Python package** (**`MERCURY_RUNNER_MODE=local`**, single Juno process without a Mercury HTTP server). Configure identity and assistants via YAML.

**Dependencies:** Juno pins **Python 3.12** (`requires-python` in [`pyproject.toml`](pyproject.toml)). The **`mercury`** package is wired as an **editable path dependency** to a sibling checkout at [`../mercury-agentic-wallet`](../mercury-agentic-wallet) (`[tool.uv.sources]`); adjust or replace that if your layout differs.

## Architecture

- **Supervisor** — `juno.agents.build_supervisor` registers one tool per **`SubagentSpec`** (stable names such as `mercury`).
- **Runtime factory** — `juno.runtime.factory.build_supervisor_bundle` loads manifests, builds sub-agents, and exposes `wallet_approval_supervisor_tool_names` for Telegram.
- **Telegram** — Thin `juno.telegram.bot` composes the app; handlers, turns, approval UI, and message helpers live under `juno.telegram.*`.
- **Docs** — More detail: [docs/subagents.md](docs/subagents.md).

## Adding another agent

Juno discovers every `assistants/*.yaml` manifest, but **only Mercury is wired today**. To add a second specialist end-to-end:

1. **Manifest** — Add `assistants/<agent>.yaml` (see `assistants/mercury.yaml`) with at least `runner`, `base_url_env`, `system_prompt`, and optional `prompt_md_path` / sibling `<agent>.md` for instructions. The manifest stem (`<agent>`) is the dict key in `discover_assistants()`.

2. **Sub-agent graph** — Implement something like `build_<agent>_subagent(...)` under `src/juno/agents/` (pattern: `build_mercury_subagent`). It should return a compiled LangGraph agent whose tools talk to your backend.

   **Remote invoke guide (optional)** — If your backend exposes a GET endpoint with markdown or prose the model must read *before* it calls tools (same idea as Mercury’s `/v1/mercury/invoke/guide`):

   - Set **`guide_path`** on the manifest (absolute path on that assistant’s base URL, e.g. `/v1/mercury/invoke/guide`). Omit it to disable the hook.
   - In `build_<agent>_subagent`, after you have an HTTP client scoped to the assistant base URL, pass LangChain middleware from **`juno.agents.build_remote_invoke_guide_middleware`**: give it a zero-argument callable that performs the GET and returns the response body as text (Mercury uses `MercuryAssistantRunner.fetch_get_text(guide_path)`).
   - Pass the returned middleware in **`create_agent(..., middleware=(...))`** alongside your tools. The hook runs **`before_model`**: it prepends one system message (guide first in the transcript) on the first model step in that sub-agent `invoke`, and **skips** further GETs once any `ToolMessage` is in the thread (later steps in the same invoke reuse the injected guide).

3. **Register in the factory** — In [`src/juno/runtime/factory.py`](src/juno/runtime/factory.py), extend `build_subagent_specs` so that for each manifest you care about (or each `runner` value), you build the subgraph and append a [`SubagentSpec`](src/juno/agents/registry.py): a **unique** `name` (supervisor tool name), `description` (what the model sees), `graph`, `state_keys` to forward from session state (e.g. `user_id`, `wallet_id`, `chain`, `approval_response`), optional `resume_instruction` after human-in-the-loop, and `supports_wallet_approval_ui=True` **only** if the Telegram Approve/Decline flow applies.

4. **Base URL** — For **`http`** Mercury runs, prefer `os.environ[manifest.base_url_env]` via `resolve_assistant_base_url`. If you need a Pydantic fallback like Mercury’s `MERCURY_BASE_URL`, extend [`resolve_assistant_base_url`](src/juno/runtime/factory.py) and add fields to [`Settings`](src/juno/settings.py) as needed. **`local`** mode does **not** use a Mercury base URL (see **Environment variables**).

5. **Supervisor prompt** — `config/juno.supervisor.md` should tell the model **when** to call each tool by name; the runtime also appends each tool’s description from the `SubagentSpec` / LangChain tool metadata.

6. **Tests** — Mirror `tests/test_agents.py`, `tests/test_runtime_factory.py`, and any HTTP/tool tests for the new backend.

Mercury remains required for startup until you generalize `build_subagent_specs` (e.g. allow a deployment with only non-Mercury agents and adjust the mercury manifest check).

## LangChain (Python OSS)

Relevant concepts and APIs:

- [Agents / create_agent](https://docs.langchain.com/oss/python/langchain/agents)
- [Subagents](https://docs.langchain.com/oss/python/langchain/multi-agent/subagents)
- [Subagents personal assistant](https://docs.langchain.com/oss/python/langchain/multi-agent/subagents-personal-assistant)
- [Short-term memory](https://docs.langchain.com/oss/python/langchain/short-term-memory) — persistent conversation state (e.g. Postgres-backed checkpointing) is optional and follows LangGraph migration patterns described there
- [Streaming](https://docs.langchain.com/oss/python/langchain/streaming)
- [Human-in-the-loop](https://docs.langchain.com/oss/python/langchain/human-in-the-loop)

## Local development

### Option A - Single process (`MERCURY_RUNNER_MODE=local`)

Juno loads Mercury as a library and runs the invoke graph in-process (no separate Mercury HTTP service).

- `uv sync` (ensures the editable `mercury` checkout is available at the path in `pyproject.toml`)
- Copy `config/juno.identity.yaml.example` to `config/juno.identity.yaml` and edit as needed
- Set **`MERCURY_RUNNER_MODE=local`** (or **`JUNO_MERCURY_RUNNER_MODE=local`**). You do **not** need **`MERCURY_BASE_URL`**.
- You **still** need whatever **Mercury** expects for live chain work: wallet / **1Claw** (or equivalent) secrets, RPC or provider keys, and any other env vars documented for the **`mercury-agentic-wallet`** deployment you are exercising. Juno does not bypass those requirements.
- Optional: `JUNO_CHECKPOINTER_DATABASE_URL` for persistent supervisor checkpoints (see below)

### Option B - Two services (`MERCURY_RUNNER_MODE=http`, default)

1. **Mercury** — run it from its own repository or service. Note its HTTP base URL (no trailing path segment).
2. **Juno** — from this repo:
   - `uv sync`
   - Copy `config/juno.identity.yaml.example` to `config/juno.identity.yaml` and edit as needed
   - Optionally edit `config/juno.supervisor.md` (general supervisor behavior; concrete tool names and descriptions are appended automatically at startup)
   - Set **`MERCURY_BASE_URL`** (or the URL via the manifest’s `base_url_env`) to point at Mercury
   - Optional: set `JUNO_CHECKPOINTER_DATABASE_URL` for Postgres-backed supervisor checkpoints (see below); if unset, the supervisor uses an in-memory saver (fine for dev; state is lost on restart)

## Environment variables

| Variable | Purpose |
|----------|---------|
| `TELEGRAM_BOT_TOKEN` | Telegram Bot API token |
| `MERCURY_RUNNER_MODE` or `JUNO_MERCURY_RUNNER_MODE` | `http` (default): delegate to Mercury over HTTP. `local`: in-process Mercury graph (no `MERCURY_BASE_URL`) |
| `MERCURY_BASE_URL` | Mercury HTTP API base URL (no trailing path). **Required when `MERCURY_RUNNER_MODE` is `http`**; **not used in `local` mode** |
| `MERCURY_HTTP_PATH` | Default `/v1/mercury/invoke` (structured `intent` body). Use `/v1/agent` only for pan-agentikit envelopes |
| `MERCURY_REQUEST_BODY_MODE` | Default `flat`. Use `nested_input` only if your server expects `{"input": {...}}` |
| `OPENAI_API_KEY` | API key when using OpenAI-backed models; identity YAML `secrets.openai_api_key_env` names this (default `OPENAI_API_KEY`) |
| `GROQ_API_KEY` | Required when `JUNO_MODEL` / `OPENAI_MODEL` uses the `groq:` provider (e.g. `groq:llama-3.3-70b-versatile`) |
| `JUNO_MODEL` or `OPENAI_MODEL` | LangChain chat model id (e.g. `openai:gpt-4o-mini`, `groq:...`) — use a **colon** (`provider:model`), not a slash |
| `JUNO_IDENTITY_PATH` | Path to identity YAML (optional; defaults apply if unset) |
| `JUNO_ASSISTANTS_DIR` | Assistants definitions directory (optional) |
| `JUNO_SUPERVISOR_PROMPT_PATH` | Override path to the supervisor Markdown prompt (default: `config/juno.supervisor.md` under the working directory) |
| `JUNO_USE_STREAM` | If set truthy, sends periodic typing while the supervisor runs |
| `JUNO_LONGTERM_MEMORY_DIR` | Per-user long-term memory JSON directory; defaults to `data/juno_long_term_memory` under the process working directory |
| `JUNO_CHECKPOINTER_DATABASE_URL` | PostgreSQL DSN for LangGraph supervisor checkpoints; empty uses the in-memory fallback (non-persistent). See **Supervisor checkpoints** |

Optional: `.env` in the project root is loaded into the process environment at bot startup (`load_dotenv`) so provider SDKs (Groq, OpenAI, etc.) see keys like `GROQ_API_KEY`; Pydantic Settings also reads the same file for app fields.

### Supervisor checkpoints (optional)

- **DSN** — Standard libpq URI, e.g. `postgresql://USER:PASSWORD@HOST:5432/DBNAME` (query params such as `sslmode=require` are supported).
- **TLS** — For hosted Postgres, prefer `sslmode=require` (or `verify-full` when you have CA material) in the URL rather than plaintext connections.
- **Credentials** — Use a dedicated DB role with minimal privileges (only what LangGraph’s Postgres saver needs for its tables/migrations). Do **not** reuse superuser or application roles that own unrelated data.
- **Secrets** — Treat the DSN like a password: never log it, avoid echoing env in shell history for production values, and do not commit `.env` or URLs containing credentials.
- **Unset** — If `JUNO_CHECKPOINTER_DATABASE_URL` is unset or whitespace-only after trim, Juno uses `InMemorySaver` (no Postgres).

Local Postgres without Compose:

```bash
docker run --rm -e POSTGRES_PASSWORD=postgres -p 5432:5432 postgres:16
```

Then point Juno at `postgresql://postgres:postgres@127.0.0.1:5432/postgres` (create a dedicated database/user for real use).

## Run

```bash
uv run juno-telegram
```

Module entrypoint (avoids importing the bot twice):

```bash
uv run python -m juno.telegram
```

### Telegram session (optional)

Per chat, you can pin defaults for Mercury:

| Command | Meaning |
|---------|---------|
| `/chain base` | Set network hint (e.g. `base`, `ethereum`) |
| `/wallet 0x…` | Set wallet address hint |
| `/session` | Show current chain + wallet |
| `/session_clear` | Clear both |

The supervisor is prompted to call Mercury for balance/on-chain questions; these hints populate graph state (`chain`, `wallet_id`) on each message.

## Tests

```bash
uv run pytest
```
