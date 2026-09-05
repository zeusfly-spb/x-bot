from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup

BTN_BALANCE = "💰 Баланс"
BTN_NEW_CHAT = "✨ Новый чат"
BTN_PACKAGES = "🛒 Пакеты"

REPLY_BUTTON_LABELS = frozenset({BTN_BALANCE, BTN_NEW_CHAT, BTN_PACKAGES})

CB_TOPUP = "ux:topup"
CB_USAGE = "ux:usage"
CB_CLOSE = "ux:close"


def main_reply_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [[BTN_BALANCE, BTN_NEW_CHAT, BTN_PACKAGES]],
        resize_keyboard=True,
        is_persistent=True,
    )


def account_inline_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Пополнить", callback_data=CB_TOPUP),
                InlineKeyboardButton("История", callback_data=CB_USAGE),
                InlineKeyboardButton("Закрыть", callback_data=CB_CLOSE),
            ]
        ]
    )
