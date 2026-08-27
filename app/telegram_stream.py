import asyncio
import time
from collections.abc import AsyncIterator

from telegram import Message
from telegram.error import BadRequest, RetryAfter, TelegramError

CURSOR = " ▌"


def split_telegram_text(text: str, limit: int) -> list[str]:
    if len(text) <= limit:
        return [text] if text else [""]
    parts: list[str] = []
    rest = text
    while rest:
        if len(rest) <= limit:
            parts.append(rest)
            break
        cut = rest.rfind("\n", 0, limit)
        if cut < limit // 2:
            cut = rest.rfind(" ", 0, limit)
        if cut < limit // 2:
            cut = limit
        parts.append(rest[:cut])
        rest = rest[cut:].lstrip()
    return parts


async def stream_to_message(
    message: Message,
    chunks: AsyncIterator[str],
    *,
    edit_interval_ms: int,
    max_chars: int,
) -> str:
    """Update one Telegram message as tokens arrive. Returns full text."""
    full = ""
    last_sent = ""
    last_edit = 0.0
    interval = edit_interval_ms / 1000.0

    async def publish(text: str, final: bool = False) -> None:
        nonlocal last_sent
        visible = text[:max_chars]
        if not final:
            visible = (visible + CURSOR)[:4096]
        if visible == last_sent:
            return
        try:
            await message.edit_text(visible or "…")
            last_sent = visible
        except RetryAfter as exc:
            await asyncio.sleep(exc.retry_after)
        except BadRequest:
            # not modified / parse issues — ignore mid-stream
            pass
        except TelegramError:
            pass

    async for piece in chunks:
        if not piece:
            continue
        full += piece
        now = time.monotonic()
        if now - last_edit >= interval:
            await publish(full, final=False)
            last_edit = now

    if len(full) <= max_chars:
        await publish(full, final=True)
        return full

    parts = split_telegram_text(full, max_chars)
    await publish(parts[0], final=True)
    chat = message.chat
    for part in parts[1:]:
        await chat.send_message(part)
    return full
