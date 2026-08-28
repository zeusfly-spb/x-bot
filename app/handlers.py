from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import ContextTypes

from app.config import Settings
from app.grok_client import GrokClient
from app.memory import ConversationMemory
from app.rate_limit import UserGuard
from app.telegram_stream import stream_to_message

START_TEXT = (
    "Привет. Это Джамбек-Джамбалек, бот Grok (xAI).\n\n"
    "Просто напишите сообщение — ответ появится по мере генерации.\n\n"
    "Команды:\n"
    "/start — это сообщение\n"
    "/help — кратко как пользоваться\n"
    "/reset — очистить историю диалога\n"
    "/model — какая модель сейчас используется"
)

HELP_TEXT = (
    "Отправьте текст. Бот держит короткий контекст последних реплик "
    "и стримит ответ Grok в одно сообщение.\n\n"
    "/reset — начать диалог заново.\n"
    "Картинки, голос и инструменты пока не подключены."
)


class BotHandlers:
    def __init__(
        self,
        settings: Settings,
        grok: GrokClient,
        memory: ConversationMemory,
        guard: UserGuard,
    ) -> None:
        self.settings = settings
        self.grok = grok
        self.memory = memory
        self.guard = guard

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.message:
            await update.message.reply_text(START_TEXT)

    async def help_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.message:
            await update.message.reply_text(HELP_TEXT)

    async def reset(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user
        if not user or not update.message:
            return
        self.memory.reset(user.id)
        await update.message.reply_text("История диалога очищена.")

    async def model_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.message:
            await update.message.reply_text(f"Модель: {self.settings.xai_model}")

    async def on_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message = update.message
        user = update.effective_user
        if not message or not user or not message.text:
            return

        text = message.text.strip()
        if not text:
            return

        blocked = self.guard.acquire(user.id)
        if blocked:
            await message.reply_text(blocked)
            return

        placeholder = await message.reply_text("Думаю…")
        try:
            await context.bot.send_chat_action(
                chat_id=message.chat_id,
                action=ChatAction.TYPING,
            )
            self.memory.append(user.id, "user", text)
            messages = [
                {"role": "system", "content": self.settings.system_prompt},
                *self.memory.get(user.id),
            ]
            full = await stream_to_message(
                placeholder,
                self.grok.stream_chat(messages),
                edit_interval_ms=self.settings.edit_interval_ms,
                max_chars=self.settings.max_message_chars,
            )
            if full.strip():
                self.memory.append(user.id, "assistant", full)
            else:
                await placeholder.edit_text("Пустой ответ от модели.")
        except Exception as exc:
            await placeholder.edit_text(self.grok.friendly_error(exc))
        finally:
            self.guard.release(user.id)
