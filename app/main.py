import logging

from telegram.ext import Application, CommandHandler, MessageHandler, filters

from app.config import load_settings
from app.grok_client import GrokClient
from app.handlers import BotHandlers
from app.memory import ConversationMemory
from app.rate_limit import UserGuard

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def build_application():
    settings = load_settings()
    grok = GrokClient(settings)
    memory = ConversationMemory(settings.history_limit)
    guard = UserGuard(settings.user_cooldown_seconds, settings.max_concurrent_per_user)
    handlers = BotHandlers(settings, grok, memory, guard)

    application = (
        Application.builder()
        .token(settings.telegram_bot_token)
        .concurrent_updates(True)
        .build()
    )
    application.add_handler(CommandHandler("start", handlers.start))
    application.add_handler(CommandHandler("help", handlers.help_cmd))
    application.add_handler(CommandHandler("reset", handlers.reset))
    application.add_handler(CommandHandler("model", handlers.model_cmd))
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.on_text)
    )
    return application


def main() -> None:
    app = build_application()
    logger.info("Starting Grok Telegram bot (polling)")
    app.run_polling(allowed_updates=["message"])


if __name__ == "__main__":
    main()
