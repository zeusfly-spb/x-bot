from __future__ import annotations

import logging
import uuid

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import ContextTypes

from app.billing import calculate_charge, fallback_charge
from app.config import Settings
from app.grok_client import GrokClient
from app.memory import ConversationMemory
from app.models import Charge, Usage
from app.rate_limit import UserGuard
from app.repository import Repository
from app.telegram_stream import stream_to_message

logger = logging.getLogger(__name__)

START_TEXT = (
    "Привет. Это Бот Портал Grok (xAI).\n\n"
    "Просто напишите сообщение — ответ появится по мере генерации.\n\n"
    "Команды:\n"
    "/start — это сообщение\n"
    "/help — кратко как пользоваться\n"
    "/reset — очистить контекст модели (логи сохраняются)\n"
    "/model — какая модель сейчас используется\n"
    "/balance — баланс кредитов\n"
    "/usage — последние запросы к модели"
)

HELP_TEXT = (
    "Отправьте текст. Бот держит короткий контекст последних реплик "
    "и стримит ответ Grok в одно сообщение. Полная история пишется в базу.\n\n"
    "/reset — начать диалог заново (контекст модели).\n"
    "/balance — кредиты. /usage — последние списания.\n"
    "Картинки, голос и инструменты пока не подключены."
)

INSUFFICIENT_FUNDS = "Недостаточно кредитов"


class BotHandlers:
    def __init__(
        self,
        settings: Settings,
        grok: GrokClient,
        memory: ConversationMemory,
        guard: UserGuard,
        repo: Repository,
    ) -> None:
        self.settings = settings
        self.grok = grok
        self.memory = memory
        self.guard = guard
        self.repo = repo

    async def _touch_user(self, update: Update):
        user = update.effective_user
        if not user:
            return None
        return await self.repo.upsert_user(
            user.id,
            user.username,
            user.first_name,
        )

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._touch_user(update)
        if update.message:
            await update.message.reply_text(START_TEXT)

    async def help_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._touch_user(update)
        if update.message:
            await update.message.reply_text(HELP_TEXT)

    async def reset(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user
        if not user or not update.message:
            return
        await self.repo.upsert_user(user.id, user.username, user.first_name)
        await self.memory.reset(user.id)
        await update.message.reply_text("История диалога очищена.")

    async def model_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._touch_user(update)
        if update.message:
            await update.message.reply_text(f"Модель: {self.settings.xai_model}")

    async def balance_cmd(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        if not update.message:
            return
        row = await self._touch_user(update)
        if not row:
            return
        await update.message.reply_text(
            f"Баланс: {row.credits} кр.\nРегистрация: {row.created_at}"
        )

    async def usage_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user
        if not user or not update.message:
            return
        await self.repo.upsert_user(user.id, user.username, user.first_name)
        events = await self.repo.list_usage_events(user.id, 5)
        if not events:
            await update.message.reply_text("Пока нет запросов к модели.")
            return
        lines = ["Последние запросы:"]
        for ev in events:
            tokens = ev["total_tokens"] or (
                ev["prompt_tokens"] + ev["completion_tokens"]
            )
            lines.append(
                f"{ev['created_at']} · {ev['model']} · {tokens} ток. · "
                f"{ev['credits_charged']} кр. · {ev['status']}"
            )
        await update.message.reply_text("\n".join(lines))

    async def grant_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        admin = update.effective_user
        message = update.message
        if not admin or not message:
            return
        if admin.id not in self.settings.admin_telegram_ids:
            return
        args = list(context.args or [])
        target_id: int | None = None
        amount: int | None = None
        reply = message.reply_to_message
        try:
            if reply and reply.from_user and args:
                target_id = reply.from_user.id
                amount = int(args[0])
            elif len(args) >= 2:
                target_id = int(args[0])
                amount = int(args[1])
        except ValueError:
            target_id = None
            amount = None
        if target_id is None or amount is None or amount <= 0:
            await message.reply_text(
                "Использование: /grant <telegram_id> <credits>\n"
                "или ответом на сообщение пользователя: /grant <credits>"
            )
            return
        await self.repo.upsert_user(target_id, None, None)
        balance = await self.repo.grant_credits(target_id, amount, reason="admin_grant")
        await message.reply_text(
            f"Начислено {amount} кр. пользователю {target_id}. Остаток: {balance}"
        )

    async def on_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message = update.message
        user = update.effective_user
        if not message or not user or not message.text:
            return

        text = message.text.strip()
        if not text:
            return

        await self.repo.upsert_user(user.id, user.username, user.first_name)

        blocked = self.guard.acquire(user.id)
        if blocked:
            await message.reply_text(blocked)
            return

        request_id = str(uuid.uuid4())
        try:
            conv_id = await self.repo.get_or_create_active_conversation(user.id)
            current = await self.repo.get_user(user.id)
            if current is None or current.credits < self.settings.min_balance_to_talk:
                await self.repo.insert_usage_event(
                    request_id=request_id,
                    telegram_id=user.id,
                    conversation_id=conv_id,
                    model=self.settings.xai_model,
                    usage=None,
                    charge=None,
                    status="insufficient_funds",
                    error_text="balance below MIN_BALANCE_TO_TALK",
                    credits_charged=0,
                )
                await message.reply_text(INSUFFICIENT_FUNDS)
                return

            placeholder = await message.reply_text("Думаю…")
            await context.bot.send_chat_action(
                chat_id=message.chat_id,
                action=ChatAction.TYPING,
            )
            await self.memory.append(
                user.id, "user", text, request_id=request_id, conversation_id=conv_id
            )
            messages = [
                {"role": "system", "content": self.settings.system_prompt},
                *await self.memory.get(user.id),
            ]
            stream = self.grok.stream_chat(messages)
            try:
                full = await stream_to_message(
                    placeholder,
                    stream,
                    edit_interval_ms=self.settings.edit_interval_ms,
                    max_chars=self.settings.max_message_chars,
                )
                usage = stream.usage
            except Exception as exc:
                await self._record_api_failure(
                    user_id=user.id,
                    conv_id=conv_id,
                    request_id=request_id,
                    usage=getattr(stream, "usage", None),
                    error_text=str(exc),
                    placeholder_text=self.grok.friendly_error(exc),
                    placeholder=placeholder,
                )
                return

            if not full.strip():
                await self._record_api_failure(
                    user_id=user.id,
                    conv_id=conv_id,
                    request_id=request_id,
                    usage=usage,
                    error_text="empty model response",
                    placeholder_text="Пустой ответ от модели.",
                    placeholder=placeholder,
                )
                return

            await self.memory.append(
                user.id,
                "assistant",
                full,
                request_id=request_id,
                conversation_id=conv_id,
            )
            if usage is None:
                logger.warning(
                    "No usage in stream for request_id=%s telegram_id=%s; "
                    "applying fallback charge",
                    request_id,
                    user.id,
                )
                charge = fallback_charge(self.settings)
                status = "no_usage"
            else:
                charge = calculate_charge(usage, self.settings)
                status = "ok"

            delta, reason, balance = await self.repo.apply_debit(
                user.id, request_id, charge.credits_charged
            )
            charged = -delta
            if reason == "debit_capped":
                status = "insufficient_funds"
            await self.repo.insert_usage_event(
                request_id=request_id,
                telegram_id=user.id,
                conversation_id=conv_id,
                model=self.settings.xai_model,
                usage=usage,
                charge=charge,
                status=status,
                credits_charged=charged,
            )
            if self.settings.show_charge_notice:
                await message.reply_text(f"−{charged} кр. Остаток: {balance}")
        finally:
            self.guard.release(user.id)

    async def _record_api_failure(
        self,
        *,
        user_id: int,
        conv_id: int,
        request_id: str,
        usage: Usage | None,
        error_text: str,
        placeholder_text: str,
        placeholder,
    ) -> None:
        await self.memory.append(
            user_id,
            "error",
            error_text,
            request_id=request_id,
            conversation_id=conv_id,
        )
        charge: Charge | None = None
        charged = 0
        if usage is not None:
            charge = calculate_charge(usage, self.settings)
            delta, _reason, _balance = await self.repo.apply_debit(
                user_id, request_id, charge.credits_charged
            )
            charged = -delta
        await self.repo.insert_usage_event(
            request_id=request_id,
            telegram_id=user_id,
            conversation_id=conv_id,
            model=self.settings.xai_model,
            usage=usage,
            charge=charge,
            status="error",
            error_text=error_text,
            credits_charged=charged,
        )
        try:
            await placeholder.edit_text(placeholder_text)
        except Exception:
            logger.exception("Failed to edit error placeholder")
