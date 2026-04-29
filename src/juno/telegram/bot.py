"""Telegram bot: polling, supervisor composition, handler registration."""

from __future__ import annotations

import asyncio
import logging
import signal

from telegram import Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, MessageHandler, filters

from juno.identity import JunoIdentityNotFoundError, JunoIdentityValidationError, load_identity
from juno.runtime.factory import build_supervisor_bundle
from juno.settings import Settings
from juno.telegram.handlers import (
    cmd_chain,
    cmd_session,
    cmd_session_clear,
    cmd_start,
    cmd_wallet,
    handle_approval_callback,
    handle_message,
)

logger = logging.getLogger(__name__)


async def _wait_for_shutdown() -> None:
    loop = asyncio.get_running_loop()
    stop = asyncio.Event()

    def _on_stop() -> None:
        stop.set()

    try:
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, _on_stop)
    except NotImplementedError:
        await asyncio.Future()
        return
    await stop.wait()


async def run_bot(settings: Settings | None = None) -> None:
    settings = settings or Settings()
    if not settings.telegram_bot_token.strip():
        raise ValueError("TELEGRAM_BOT_TOKEN is missing or empty.")

    try:
        identity = load_identity(settings.juno_identity_path)
    except JunoIdentityNotFoundError as exc:
        logger.error(
            "Identity file is required. Copy config/juno.identity.yaml.example to "
            "config/juno.identity.yaml or set JUNO_IDENTITY_PATH. %s",
            exc,
        )
        raise SystemExit(1) from exc
    except JunoIdentityValidationError as exc:
        logger.error("Invalid identity YAML: %s", exc)
        raise SystemExit(1) from exc

    logger.info("Loaded identity agent_id=%s display_name=%s", identity.agent_id, identity.display_name)

    bundle = build_supervisor_bundle(settings)
    application = Application.builder().token(settings.telegram_bot_token.strip()).build()
    application.bot_data["supervisor"] = bundle.graph
    application.bot_data["wallet_approval_supervisor_tools"] = bundle.wallet_approval_supervisor_tool_names
    application.bot_data["settings"] = settings

    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CommandHandler("chain", cmd_chain))
    application.add_handler(CommandHandler("wallet", cmd_wallet))
    application.add_handler(CommandHandler("session", cmd_session))
    application.add_handler(CommandHandler("session_clear", cmd_session_clear))
    application.add_handler(CallbackQueryHandler(handle_approval_callback, pattern=r"^apr:"))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    async with application:
        await application.start()
        await application.updater.start_polling(allowed_updates=Update.ALL_TYPES)
        try:
            await _wait_for_shutdown()
        finally:
            await application.updater.stop()
            await application.stop()


def main() -> None:
    # Pydantic Settings reads `.env` for its own fields but does not populate
    # ``os.environ``; Groq/OpenAI clients expect API keys in the environment.
    from dotenv import load_dotenv

    load_dotenv()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    asyncio.run(run_bot())


if __name__ == "__main__":
    main()

__all__ = ["main", "run_bot"]
