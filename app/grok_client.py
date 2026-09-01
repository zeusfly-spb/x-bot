from collections.abc import AsyncIterator, Iterable
from typing import Any

import httpx
from openai import APIError, AsyncOpenAI, AuthenticationError, RateLimitError

from app.config import Settings
from app.models import StreamResult, Usage


def parse_usage(raw: Any) -> Usage:
    prompt = int(getattr(raw, "prompt_tokens", 0) or 0)
    completion = int(getattr(raw, "completion_tokens", 0) or 0)
    total = int(getattr(raw, "total_tokens", 0) or 0)
    reasoning = int(getattr(raw, "reasoning_tokens", 0) or 0)
    details = getattr(raw, "completion_tokens_details", None)
    if details is not None:
        reasoning = int(getattr(details, "reasoning_tokens", reasoning) or reasoning)
    output_details = getattr(raw, "output_tokens_details", None)
    if output_details is not None and reasoning == 0:
        reasoning = int(getattr(output_details, "reasoning_tokens", 0) or 0)
    raw_json = None
    dump = getattr(raw, "model_dump", None)
    if callable(dump):
        try:
            import json

            raw_json = json.dumps(dump(), default=str)
        except Exception:
            raw_json = str(raw)
    else:
        raw_json = str(raw)
    if total <= 0:
        total = prompt + completion
    return Usage(
        prompt_tokens=prompt,
        completion_tokens=completion,
        reasoning_tokens=reasoning,
        total_tokens=total,
        raw_json=raw_json,
    )


class GrokStream:
    """Async iterator of text deltas. After iteration, ``result()`` has usage."""

    def __init__(self, client: AsyncOpenAI, model: str, messages: list[dict]) -> None:
        self._client = client
        self._model = model
        self._messages = messages
        self.text = ""
        self.usage: Usage | None = None
        self._started = False

    def __aiter__(self) -> AsyncIterator[str]:
        return self._iterate()

    async def _iterate(self) -> AsyncIterator[str]:
        if self._started:
            raise RuntimeError("GrokStream can be iterated only once")
        self._started = True
        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": self._messages,
            "stream": True,
        }
        try:
            stream = await self._client.chat.completions.create(
                **kwargs,
                stream_options={"include_usage": True},
            )
        except TypeError:
            stream = await self._client.chat.completions.create(**kwargs)
        async for chunk in stream:
            usage_obj = getattr(chunk, "usage", None)
            if usage_obj:
                self.usage = parse_usage(usage_obj)
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            text = getattr(delta, "content", None) or ""
            if text:
                self.text += text
                yield text

    def result(self) -> StreamResult:
        return StreamResult(text=self.text, usage=self.usage)


class GrokClient:
    def __init__(self, settings: Settings) -> None:
        timeout = httpx.Timeout(settings.request_timeout_seconds)
        self._model = settings.xai_model
        self._client = AsyncOpenAI(
            api_key=settings.xai_api_key,
            base_url=settings.xai_base_url,
            timeout=timeout,
        )

    def stream_chat(self, messages: Iterable[dict]) -> GrokStream:
        return GrokStream(self._client, self._model, list(messages))

    @staticmethod
    def friendly_error(exc: Exception) -> str:
        if isinstance(exc, AuthenticationError):
            return "Ошибка авторизации xAI API. Проверьте XAI_API_KEY."
        if isinstance(exc, RateLimitError):
            return "xAI временно ограничил частоту запросов. Попробуйте позже."
        if isinstance(exc, APIError):
            return f"Ошибка xAI API: {exc.message or exc}"
        return f"Не удалось получить ответ Grok: {exc}"
