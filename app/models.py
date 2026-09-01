from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    reasoning_tokens: int = 0
    total_tokens: int = 0
    raw_json: str | None = None


@dataclass(frozen=True)
class Charge:
    provider_cost_usd: str
    markup_usd: str
    billed_usd: str
    credits_charged: int


@dataclass
class StreamResult:
    text: str
    usage: Usage | None


@dataclass(frozen=True)
class User:
    telegram_id: int
    username: str | None
    first_name: str | None
    created_at: str
    updated_at: str
    credits: int
    is_blocked: int
