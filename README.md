# Grok Telegram Bot

Публичный Telegram-бот для общения с Grok через xAI API. Ответ стримится правками одного сообщения. Пользователи, полная история переписки и биллинг хранятся в SQLite.

## Что умеет

- текстовый диалог; в модель уходят последние `HISTORY_LIMIT` реплик, в БД пишется вся история
- streaming через `edit_text`
- `/start` `/help` `/reset` `/model` `/balance` `/usage`
- `/reset` закрывает активную сессию (контекст модели), логи и ledger не удаляются
- кредиты (внутренняя валюта), append-only ledger
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

## База данных

Файл задаётся `DATABASE_PATH` (по умолчанию `data/bot.db`). Каталог `data/` создаётся при старте. Удаление файла БД **безвозвратно** сбрасывает балансы, историю и ledger.

Баланс — целое число кредитов. 1 USD = `CREDITS_PER_USD` кредитов (по умолчанию 10000, то есть 1 кр. = $0.0001).

После успешного ответа списывается `ceil(billed_usd * CREDITS_PER_USD)`, не меньше `MIN_CHARGE_CREDITS`.  
`billed_usd = provider_cost * (1 + COMMISSION_PERCENT/100) + COMMISSION_FLAT_USD`.  
Себестоимость: input × `PRICE_INPUT_PER_MILLION_USD`, output (и отдельно отданные reasoning tokens) × `PRICE_OUTPUT_PER_MILLION_USD`.

Баланс не уходит в минус: если кредитов меньше начисления, списывается остаток, `ledger.reason = debit_capped`, в `usage_events.status` будет `insufficient_funds`.

Если модель ответила, но usage не пришёл: статус `no_usage`, списывается `FALLBACK_CHARGE_CREDITS` (по умолчанию 10).

Новому пользователю начисляется `WELCOME_CREDITS` (по умолчанию 0) с записью ledger `grant` / `welcome`, если сумма > 0.

## Команды

- `/balance` — баланс и дата регистрации
- `/usage` — последние 5 вызовов модели
- `/grant` — только если в `ADMIN_TELEGRAM_IDS` есть ваш telegram_id: `/grant <telegram_id> <credits>` или ответом на пользователя `/grant <credits>`

`SHOW_CHARGE_NOTICE=1` — после ответа строка «−N кр. Остаток: …».

## Ручное пополнение (SQL)

На сервере, подставьте свой `telegram_id` и сумму. `UPDATE` и `INSERT` в одной транзакции, `balance_after` должен совпасть с новым балансом:

```sql
BEGIN;
UPDATE users
SET credits = credits + 100000,
    updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
WHERE telegram_id = 123456789;

INSERT INTO ledger (
    telegram_id, request_id, kind, delta, balance_after, reason, created_at
)
SELECT
    telegram_id,
    NULL,
    'grant',
    100000,
    credits,
    'manual_sql',
    strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
FROM users
WHERE telegram_id = 123456789;
COMMIT;
```

100000 кредитов при курсе 10000 = $10. Пользователь должен уже существовать (написать боту `/start`).

## Переменные

См. `.env.example`. Обязательные: `TELEGRAM_BOT_TOKEN`, `XAI_API_KEY`. Модель: `XAI_MODEL` (по умолчанию `grok-4.6`).
