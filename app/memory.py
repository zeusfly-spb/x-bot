from collections import defaultdict, deque
from typing import Deque, Dict, List


class ConversationMemory:
    """In-memory per-user chat history. Lost on process restart."""

    def __init__(self, history_limit: int) -> None:
        self._history_limit = history_limit
        self._store: Dict[int, Deque[dict]] = defaultdict(deque)

    def get(self, user_id: int) -> List[dict]:
        return list(self._store[user_id])

    def append(self, user_id: int, role: str, content: str) -> None:
        bucket = self._store[user_id]
        bucket.append({"role": role, "content": content})
        while len(bucket) > self._history_limit:
            bucket.popleft()

    def reset(self, user_id: int) -> None:
        self._store.pop(user_id, None)
