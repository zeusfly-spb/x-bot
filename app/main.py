import logging

from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from app.config import load_settings
from app.db import Database
from app.grok_client import GrokClient
from app.handlers import BotHandlers
from app.memory import ConversationMemory
from app.rate_limit import UserGuard
from app.repository import Repository

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def build_application():
    settings = load_settings()
    db = Database(settings.database_path)
    repo = Repository(db, settings)
    grok = GrokClient(settings)
    memory = ConversationMemory(repo, settings.history_limit)
    guard = UserGuard(settings.user_cooldown_seconds, settings.max_concurrent_per_user)
    handlers = BotHandlers(settings, grok, memory, guard, repo)

    async def post_init(application: Application) -> None:
        await db.connect()
        logger.info("SQLite ready at %s", settings.database_path)

    async def post_shutdown(application: Application) -> None:
        await db.close()

    application = (
        Application.builder()
        .token(settings.telegram_bot_token)
        .concurrent_updates(True)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )
    application.add_handler(CommandHandler("start", handlers.start))
    application.add_handler(CommandHandler("help", handlers.help_cmd))
    application.add_handler(CommandHandler("reset", handlers.reset))
    application.add_handler(CommandHandler("model", handlers.model_cmd))
    application.add_handler(CommandHandler("balance", handlers.balance_cmd))
    application.add_handler(CommandHandler("usage", handlers.usage_cmd))
    if settings.admin_telegram_ids:
        application.add_handler(CommandHandler("grant", handlers.grant_cmd))
    application.add_handler(CallbackQueryHandler(handlers.on_callback))
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.on_text)
    )
    return application


def main() -> None:
    app = build_application()
    logger.info("Starting Grok Telegram bot (polling)")
    app.run_polling(allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    main()
