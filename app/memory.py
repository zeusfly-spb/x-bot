from app.repository import Repository


class ConversationMemory:
    """Persistent chat history via SQLite. Model context is limited; logs are not."""

    def __init__(self, repo: Repository, history_limit: int) -> None:
        self._repo = repo
        self._history_limit = history_limit

    async def get(self, user_id: int) -> list[dict]:
        return await self._repo.get_model_context(user_id, self._history_limit)

    async def append(
        self,
        user_id: int,
        role: str,
        content: str,
        request_id: str | None = None,
        conversation_id: int | None = None,
    ) -> None:
        conv_id = conversation_id
        if conv_id is None:
            conv_id = await self._repo.get_or_create_active_conversation(user_id)
        await self._repo.add_message(conv_id, user_id, role, content, request_id)

    async def reset(self, user_id: int) -> None:
        await self._repo.reset_conversation(user_id)
