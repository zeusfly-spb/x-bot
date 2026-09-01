import os
from dataclasses import dataclass
from decimal import Decimal

from dotenv import load_dotenv

load_dotenv()


def _require(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _int(name: str, default: int) -> int:
    raw = os.getenv(name)
    return default if raw is None or raw == "" else int(raw)


def _decimal(name: str, default: str) -> Decimal:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return Decimal(default)
    return Decimal(raw.strip())


def _flag(name: str, default: str = "0") -> bool:
    raw = (os.getenv(name, default) or default).strip().lower()
    return raw in ("1", "true", "yes", "on")


def _id_set(name: str) -> frozenset[int]:
    raw = os.getenv(name, "").strip()
    if not raw:
        return frozenset()
    return frozenset(int(part.strip()) for part in raw.split(",") if part.strip())


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    xai_api_key: str
    xai_model: str
    xai_base_url: str
    system_prompt: str
    history_limit: int
    edit_interval_ms: int
    max_message_chars: int
    user_cooldown_seconds: float
    max_concurrent_per_user: int
    request_timeout_seconds: float
    database_path: str
    credits_per_usd: int
    price_input_per_million_usd: Decimal
    price_output_per_million_usd: Decimal
    commission_percent: Decimal
    commission_flat_usd: Decimal
    min_charge_credits: int
    fallback_charge_credits: int
    min_balance_to_talk: int
    welcome_credits: int
    show_charge_notice: bool
    admin_telegram_ids: frozenset[int]


def load_settings() -> Settings:
    return Settings(
        telegram_bot_token=_require("TELEGRAM_BOT_TOKEN"),
        xai_api_key=_require("XAI_API_KEY"),
        xai_model=os.getenv("XAI_MODEL", "grok-4.6").strip(),
        xai_base_url=os.getenv("XAI_BASE_URL", "https://api.x.ai/v1").strip(),
        system_prompt=os.getenv(
            "SYSTEM_PROMPT",
            "You are Grok Portal, a helpful and maximally truthful AI built by xAI powered by Portal"
            "Answer in the user's language.",
        ).strip(),
        history_limit=max(2, _int("HISTORY_LIMIT", 20)),
        edit_interval_ms=max(250, _int("EDIT_INTERVAL_MS", 600)),
        max_message_chars=min(4096, max(500, _int("MAX_MESSAGE_CHARS", 4000))),
        user_cooldown_seconds=float(os.getenv("USER_COOLDOWN_SECONDS", "2")),
        max_concurrent_per_user=max(1, _int("MAX_CONCURRENT_PER_USER", 1)),
        request_timeout_seconds=float(os.getenv("REQUEST_TIMEOUT_SECONDS", "180")),
        database_path=os.getenv("DATABASE_PATH", "data/bot.db").strip() or "data/bot.db",
        credits_per_usd=max(1, _int("CREDITS_PER_USD", 10000)),
        price_input_per_million_usd=_decimal("PRICE_INPUT_PER_MILLION_USD", "2.00"),
        price_output_per_million_usd=_decimal("PRICE_OUTPUT_PER_MILLION_USD", "6.00"),
        commission_percent=_decimal("COMMISSION_PERCENT", "30"),
        commission_flat_usd=_decimal("COMMISSION_FLAT_USD", "0"),
        min_charge_credits=max(0, _int("MIN_CHARGE_CREDITS", 1)),
        fallback_charge_credits=max(0, _int("FALLBACK_CHARGE_CREDITS", 10)),
        min_balance_to_talk=max(0, _int("MIN_BALANCE_TO_TALK", 1)),
        welcome_credits=max(0, _int("WELCOME_CREDITS", 0)),
        show_charge_notice=_flag("SHOW_CHARGE_NOTICE", "0"),
        admin_telegram_ids=_id_set("ADMIN_TELEGRAM_IDS"),
    )
