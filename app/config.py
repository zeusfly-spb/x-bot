import os
from dataclasses import dataclass

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


def load_settings() -> Settings:
    return Settings(
        telegram_bot_token=_require("TELEGRAM_BOT_TOKEN"),
        xai_api_key=_require("XAI_API_KEY"),
        xai_model=os.getenv("XAI_MODEL", "grok-4.6").strip(),
        xai_base_url=os.getenv("XAI_BASE_URL", "https://api.x.ai/v1").strip(),
        system_prompt=os.getenv(
            "SYSTEM_PROMPT",
            "You are Grok, a helpful and maximally truthful AI built by xAI. "
            "Answer in the user's language.",
        ).strip(),
        history_limit=max(2, _int("HISTORY_LIMIT", 20)),
        edit_interval_ms=max(250, _int("EDIT_INTERVAL_MS", 600)),
        max_message_chars=min(4096, max(500, _int("MAX_MESSAGE_CHARS", 4000))),
        user_cooldown_seconds=float(os.getenv("USER_COOLDOWN_SECONDS", "2")),
        max_concurrent_per_user=max(1, _int("MAX_CONCURRENT_PER_USER", 1)),
        request_timeout_seconds=float(os.getenv("REQUEST_TIMEOUT_SECONDS", "180")),
    )
