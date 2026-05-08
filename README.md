# Juno

Telegram bot service that runs a **LangChain** supervisor and loads **specialist assistants** from installed Python packages via **`juno.assistants`** setuptools entry points. Deployments typically install **`mercury`** for the wallet specialist; **Mercury** chooses **HTTP** vs **in-process** invocation using **`MERCURY_RUNNER_MODE`** (read by the Mercury plugin). Configure identity via YAML.

**Dependencies:** Juno pins **Python 3.12** (`requires-python` in [`pyproject.toml`](pyproject.toml)). **Core Juno does not list Mercury** as a dependency. For local monorepo development, **`uv sync --group dev`** installs **Mercury** from the sibling checkout at [`../mercury-agentic-wallet`](../mercury-agentic-wallet) (`[tool.uv.sources]`). In production, **`pip install juno mercury`** (or your lockfile equivalent) is enough when you want Mercury.

## Architecture

- **Plugins** — Packages register callables under setuptools group **`juno.assistants`**; [`juno.plugins.load_assistant_specs`](src/juno/plugins.py) discovers them. By default **all** installed plugins load; set **`JUNO_DISABLED_ASSISTANTS`** to skip by entry-point name (e.g. `mercury`).
- **Supervisor** — [`juno.agents.build_supervisor`](src/juno/agents/build_supervisor.py) registers one tool per [`SubagentSpec`](src/juno/agents/registry.py) (stable names such as `mercury`).
- **Runtime factory** — [`juno.runtime.factory.build_supervisor_bundle`](src/juno/runtime/factory.py) loads plugins, builds sub-agents, and exposes `wallet_approval_supervisor_tool_names` for Telegram.
- **Optional YAML manifests** — [`juno.assistants.loader.discover_assistants`](src/juno/assistants/loader.py) can still load **`assistants/*.yaml`** for tooling or future host features; **assistant registration is not driven from these files** anymore.
- **Telegram** — Thin `juno.telegram.bot` composes the app; handlers, turns, approval UI, and message helpers live under `juno.telegram.*`.
- **Docs** — More detail: [docs/subagents.md](docs/subagents.md).

## Adding another assistant package

1. In your package, implement a factory `create_plugin(ctx: JunoPluginContext) -> Sequence[SubagentSpec]` (or a single `SubagentSpec`). Use host-only context from [`JunoPluginContext`](src/juno/plugins.py); keep transport and specialist prompts inside your package.
2. Register it in **`pyproject.toml`**:

   ```toml
   [project.entry-points."juno.assistants"]
   my_assistant = "my_package.juno_plugin:create_plugin"
   ```

3. Ensure tool names in [`SubagentSpec`](src/juno/agents/registry.py) are **unique** across enabled plugins.
4. **Remote invoke guide (optional)** — Specialists can use LangChain middleware from **`juno.agents.build_remote_invoke_guide_middleware`** so the model receives Markdown before the first LLM call (same pattern as Mercury's invoke guide).
5. Add tests in your package for HTTP/local runners and `SubagentSpec` metadata; Juno’s tests cover discovery, disable list, and duplicates ([`tests/test_plugins.py`](tests/test_plugins.py)).

See the **mercury-agentic-wallet** repository for the reference **`mercury`** plugin implementation.

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

- `uv sync --group dev` (installs **`mercury`** from the editable path in **`pyproject.toml`** for pytest and local integration)
- Copy `config/juno.identity.yaml.example` to `config/juno.identity.yaml` and edit as needed
- Set **`MERCURY_RUNNER_MODE=local`** (or **`JUNO_MERCURY_RUNNER_MODE=local`**). You do **not** need **`MERCURY_BASE_URL`**.
- You **still** need whatever **Mercury** expects for live chain work: wallet / **1Claw** (or equivalent) secrets, RPC or provider keys, and any other env vars documented for the **`mercury-agentic-wallet`** deployment you are exercising. Juno does not bypass those requirements.
- Optional: `JUNO_CHECKPOINTER_DATABASE_URL` for persistent supervisor checkpoints (see below)

### Option B - Two services (`MERCURY_RUNNER_MODE=http`, default)

1. **Mercury** — run it from its own repository or service. Note its HTTP base URL (no trailing path segment).
2. **Juno** — from this repo:
   - `uv sync --group dev`
   - Copy `config/juno.identity.yaml.example` to `config/juno.identity.yaml` and edit as needed
   - Optionally edit `config/juno.supervisor.md` (general supervisor behavior; concrete tool names and descriptions are appended automatically at startup)
   - Set **`MERCURY_BASE_URL`** (or the URL via the manifest’s `base_url_env`) to point at Mercury
   - Optional: set `JUNO_CHECKPOINTER_DATABASE_URL` for Postgres-backed supervisor checkpoints (see below); if unset, the supervisor uses an in-memory saver (fine for dev; state is lost on restart)

## Environment variables

| Variable | Purpose |
|----------|---------|
| `TELEGRAM_BOT_TOKEN` | Telegram Bot API token |
| `JUNO_DISABLED_ASSISTANTS` | Comma-separated setuptools entry-point **names** under `juno.assistants` to skip (e.g. `mercury`) |
| `MERCURY_RUNNER_MODE` or `JUNO_MERCURY_RUNNER_MODE` | Mercury plugin: **`http`** (default) calls a Mercury HTTP API; **`local`** runs the Mercury graph **in-process** (no **`MERCURY_BASE_URL`**). Ignored when Mercury plugin is disabled. |
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
uv sync --group dev
uv run pytest
```
