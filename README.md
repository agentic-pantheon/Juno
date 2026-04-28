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
   - Set environment variables (see below), including `MERCURY_BASE_URL` pointing at Mercury

## Environment variables

| Variable | Purpose |
|----------|---------|
| `TELEGRAM_BOT_TOKEN` | Telegram Bot API token |
| `MERCURY_BASE_URL` | Mercury HTTP API base URL (required for Mercury-backed runs) |
| `OPENAI_API_KEY` | API key for the chat model; `config/juno.identity.yaml` references the env name via `secrets.openai_api_key_env` (default name `OPENAI_API_KEY`) |
| `JUNO_MODEL` or `OPENAI_MODEL` | LangChain chat model id (e.g. `openai:gpt-4o-mini`) |
| `JUNO_IDENTITY_PATH` | Path to identity YAML (optional; defaults apply if unset) |
| `JUNO_ASSISTANTS_DIR` | Assistants definitions directory (optional) |
| `JUNO_USE_STREAM` | If set truthy, sends periodic typing while the supervisor runs |

Optional: `.env` in the project root is loaded when present (via pydantic-settings).

## Run

```bash
uv run juno-telegram
```

Module entrypoint (avoids importing the bot twice):

```bash
uv run python -m juno.telegram
```

## Tests

```bash
uv run pytest
```
