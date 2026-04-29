# Juno

Telegram bot service that runs a **LangChain** supervisor and delegates assistant work to **Mercury** over HTTP. Configure identity and assistants via YAML; point `MERCURY_BASE_URL` at a running Mercury API.

## LangChain (Python OSS)

Relevant concepts and APIs:

- [Agents / create_agent](https://docs.langchain.com/oss/python/langchain/agents)
- [Subagents](https://docs.langchain.com/oss/python/langchain/multi-agent/subagents)
- [Subagents personal assistant](https://docs.langchain.com/oss/python/langchain/multi-agent/subagents-personal-assistant)
- [Short-term memory](https://docs.langchain.com/oss/python/langchain/short-term-memory) — persistent conversation state (e.g. Postgres-backed checkpointing) is optional and follows LangGraph migration patterns described there
- [Streaming](https://docs.langchain.com/oss/python/langchain/streaming)
- [Human-in-the-loop](https://docs.langchain.com/oss/python/langchain/human-in-the-loop)

## Local development (two services)

1. **Mercury** — run it from its own repository/service. Note its HTTP base URL (no trailing path segment).
2. **Juno** — from this repo:
   - `uv sync`
   - Copy `config/juno.identity.yaml.example` to `config/juno.identity.yaml` and edit as needed
   - Optionally edit `config/juno.supervisor.md` (general supervisor behavior; concrete tool names and descriptions are appended automatically at startup)
   - Set environment variables (see below), including `MERCURY_BASE_URL` pointing at Mercury

## Environment variables

| Variable | Purpose |
|----------|---------|
| `TELEGRAM_BOT_TOKEN` | Telegram Bot API token |
| `MERCURY_BASE_URL` | Mercury HTTP API base URL (required for Mercury-backed runs) |
| `MERCURY_HTTP_PATH` | Default `/v1/mercury/invoke` (structured `intent` body). Use `/v1/agent` only for pan-agentikit envelopes |
| `MERCURY_REQUEST_BODY_MODE` | Default `flat`. Use `nested_input` only if your server expects `{"input": {...}}` |
| `OPENAI_API_KEY` | API key when using OpenAI-backed models; identity YAML `secrets.openai_api_key_env` names this (default `OPENAI_API_KEY`) |
| `GROQ_API_KEY` | Required when `JUNO_MODEL` / `OPENAI_MODEL` uses the `groq:` provider (e.g. `groq:llama-3.3-70b-versatile`) |
| `JUNO_MODEL` or `OPENAI_MODEL` | LangChain chat model id (e.g. `openai:gpt-4o-mini`, `groq:...`) — use a **colon** (`provider:model`), not a slash |
| `JUNO_IDENTITY_PATH` | Path to identity YAML (optional; defaults apply if unset) |
| `JUNO_ASSISTANTS_DIR` | Assistants definitions directory (optional) |
| `JUNO_SUPERVISOR_PROMPT_PATH` | Override path to the supervisor Markdown prompt (default: `config/juno.supervisor.md` under the working directory) |
| `JUNO_USE_STREAM` | If set truthy, sends periodic typing while the supervisor runs |

Optional: `.env` in the project root is loaded into the process environment at bot startup (`load_dotenv`) so provider SDKs (Groq, OpenAI, etc.) see keys like `GROQ_API_KEY`; Pydantic Settings also reads the same file for app fields.

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
