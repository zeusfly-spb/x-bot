from collections.abc import AsyncIterator
from typing import Iterable

import httpx
from openai import APIError, AsyncOpenAI, AuthenticationError, RateLimitError

from app.config import Settings


class GrokClient:
    def __init__(self, settings: Settings) -> None:
        timeout = httpx.Timeout(settings.request_timeout_seconds)
        self._model = settings.xai_model
        self._client = AsyncOpenAI(
            api_key=settings.xai_api_key,
            base_url=settings.xai_base_url,
            timeout=timeout,
        )

    async def stream_chat(self, messages: Iterable[dict]) -> AsyncIterator[str]:
        stream = await self._client.chat.completions.create(
            model=self._model,
            messages=list(messages),
            stream=True,
        )
        async for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            text = getattr(delta, "content", None) or ""
            if text:
                yield text

    @staticmethod
    def friendly_error(exc: Exception) -> str:
        if isinstance(exc, AuthenticationError):
            return "Ошибка авторизации xAI API. Проверьте XAI_API_KEY."
        if isinstance(exc, RateLimitError):
            return "xAI временно ограничил частоту запросов. Попробуйте позже."
        if isinstance(exc, APIError):
            return f"Ошибка xAI API: {exc.message or exc}"
        return f"Не удалось получить ответ Grok: {exc}"
