import time
from collections import defaultdict


class UserGuard:
    """Simple public-bot protection: cooldown + one in-flight request per user."""

    def __init__(self, cooldown_seconds: float, max_concurrent: int) -> None:
        self._cooldown = cooldown_seconds
        self._max_concurrent = max_concurrent
        self._last_start: dict[int, float] = {}
        self._inflight: dict[int, int] = defaultdict(int)

    def acquire(self, user_id: int) -> str | None:
        now = time.monotonic()
        last = self._last_start.get(user_id, 0.0)
        if now - last < self._cooldown:
            wait = self._cooldown - (now - last)
            return f"Подождите {wait:.1f} с перед следующим сообщением."
        if self._inflight[user_id] >= self._max_concurrent:
            return "Дождитесь окончания текущего ответа."
        self._last_start[user_id] = now
        self._inflight[user_id] += 1
        return None

    def release(self, user_id: int) -> None:
        if self._inflight[user_id] > 0:
            self._inflight[user_id] -= 1
