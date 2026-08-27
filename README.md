# Grok Telegram Bot

Публичный Telegram-бот для общения с Grok через xAI API. Ответ стримится правками одного сообщения.

## Что умеет

- текстовый диалог с историей (последние 20 реплик)
- streaming через `edit_text`
- `/start` `/help` `/reset` `/model`
- антиабьюз: пауза между запросами и один активный ответ на пользователя
- без whitelist — бот публичный

## Подготовка

1. Создайте бота у [@BotFather](https://t.me/BotFather) и скопируйте токен.
2. Ключ xAI: [console.x.ai](https://console.x.ai) → API Keys. Нужны кредиты на аккаунте.
3. Python 3.11+.

```bash
cd grok-telegram-bot
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# заполните TELEGRAM_BOT_TOKEN и XAI_API_KEY в .env
python -m app.main
```

Запускайте из корня проекта, чтобы импорт `app` работал.

## Переменные

См. `.env.example`. Основные: `TELEGRAM_BOT_TOKEN`, `XAI_API_KEY`, `XAI_MODEL` (по умолчанию `grok-4.6`).

История хранится в памяти процесса и сбрасывается при рестарте.
