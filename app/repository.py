from __future__ import annotations

from datetime import datetime, timezone

from app.config import Settings
from app.db import Database
from app.models import Charge, Usage, User


def utc_now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _user_from_row(row) -> User:
    return User(
        telegram_id=row["telegram_id"],
        username=row["username"],
        first_name=row["first_name"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        credits=row["credits"],
        is_blocked=row["is_blocked"],
    )


class Repository:
    def __init__(self, db: Database, settings: Settings) -> None:
        self._db = db
        self._settings = settings

    async def upsert_user(
        self,
        telegram_id: int,
        username: str | None,
        first_name: str | None,
    ) -> User:
        now = utc_now_iso()
        async with self._db.transaction() as conn:
            cur = await conn.execute(
                "SELECT * FROM users WHERE telegram_id = ?",
                (telegram_id,),
            )
            row = await cur.fetchone()
            if row is None:
                welcome = self._settings.welcome_credits
                await conn.execute(
                    """
                    INSERT INTO users (
                        telegram_id, username, first_name, created_at, updated_at,
                        credits, is_blocked
                    ) VALUES (?, ?, ?, ?, ?, ?, 0)
                    """,
                    (telegram_id, username, first_name, now, now, welcome),
                )
                if welcome > 0:
                    await conn.execute(
                        """
                        INSERT INTO ledger (
                            telegram_id, request_id, kind, delta, balance_after,
                            reason, created_at
                        ) VALUES (?, NULL, 'grant', ?, ?, 'welcome', ?)
                        """,
                        (telegram_id, welcome, welcome, now),
                    )
            else:
                await conn.execute(
                    """
                    UPDATE users
                    SET username = ?, first_name = ?, updated_at = ?
                    WHERE telegram_id = ?
                    """,
                    (username, first_name, now, telegram_id),
                )
            cur = await conn.execute(
                "SELECT * FROM users WHERE telegram_id = ?",
                (telegram_id,),
            )
            row = await cur.fetchone()
            assert row is not None
            return _user_from_row(row)

    async def get_user(self, telegram_id: int) -> User | None:
        cur = await self._db.conn.execute(
            "SELECT * FROM users WHERE telegram_id = ?",
            (telegram_id,),
        )
        row = await cur.fetchone()
        return _user_from_row(row) if row else None

    async def get_or_create_active_conversation(self, telegram_id: int) -> int:
        now = utc_now_iso()
        async with self._db.transaction() as conn:
            cur = await conn.execute(
                """
                SELECT id FROM conversations
                WHERE telegram_id = ? AND is_active = 1
                ORDER BY id DESC LIMIT 1
                """,
                (telegram_id,),
            )
            row = await cur.fetchone()
            if row is not None:
                return int(row["id"])
            cur = await conn.execute(
                """
                INSERT INTO conversations (telegram_id, started_at, ended_at, is_active)
                VALUES (?, ?, NULL, 1)
                """,
                (telegram_id, now),
            )
            return int(cur.lastrowid)

    async def reset_conversation(self, telegram_id: int) -> int:
        now = utc_now_iso()
        async with self._db.transaction() as conn:
            await conn.execute(
                """
                UPDATE conversations
                SET is_active = 0, ended_at = ?
                WHERE telegram_id = ? AND is_active = 1
                """,
                (now, telegram_id),
            )
            cur = await conn.execute(
                """
                INSERT INTO conversations (telegram_id, started_at, ended_at, is_active)
                VALUES (?, ?, NULL, 1)
                """,
                (telegram_id, now),
            )
            return int(cur.lastrowid)

    async def add_message(
        self,
        conversation_id: int,
        telegram_id: int,
        role: str,
        content: str,
        request_id: str | None = None,
    ) -> None:
        now = utc_now_iso()
        async with self._db.transaction() as conn:
            await conn.execute(
                """
                INSERT INTO messages (
                    conversation_id, telegram_id, role, content, created_at, request_id
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (conversation_id, telegram_id, role, content, now, request_id),
            )

    async def get_model_context(
        self,
        telegram_id: int,
        history_limit: int,
    ) -> list[dict]:
        cur = await self._db.conn.execute(
            """
            SELECT id FROM conversations
            WHERE telegram_id = ? AND is_active = 1
            ORDER BY id DESC LIMIT 1
            """,
            (telegram_id,),
        )
        row = await cur.fetchone()
        if row is None:
            return []
        conversation_id = int(row["id"])
        cur = await self._db.conn.execute(
            """
            SELECT role, content FROM messages
            WHERE conversation_id = ? AND role IN ('user', 'assistant')
            ORDER BY id DESC
            LIMIT ?
            """,
            (conversation_id, history_limit),
        )
        rows = await cur.fetchall()
        items = [{"role": r["role"], "content": r["content"]} for r in rows]
        items.reverse()
        return items

    async def apply_debit(
        self,
        telegram_id: int,
        request_id: str | None,
        credits_charged: int,
    ) -> tuple[int, str, int]:
        """Debit without going negative. Returns (delta, reason, balance_after).

        Full debit uses reason ``debit``. If balance is lower than the charge,
        the remaining credits are taken and reason is ``debit_capped``.
        """
        if credits_charged <= 0:
            user = await self.get_user(telegram_id)
            return 0, "debit", user.credits if user else 0

        now = utc_now_iso()
        async with self._db.transaction() as conn:
            cur = await conn.execute(
                "SELECT credits FROM users WHERE telegram_id = ?",
                (telegram_id,),
            )
            row = await cur.fetchone()
            if row is None:
                raise RuntimeError(f"user {telegram_id} not found")
            balance = int(row["credits"])
            if balance >= credits_charged:
                delta = -credits_charged
                reason = "debit"
            elif balance > 0:
                delta = -balance
                reason = "debit_capped"
            else:
                return 0, "debit_capped", 0
            new_balance = balance + delta
            await conn.execute(
                "UPDATE users SET credits = ?, updated_at = ? WHERE telegram_id = ?",
                (new_balance, now, telegram_id),
            )
            await conn.execute(
                """
                INSERT INTO ledger (
                    telegram_id, request_id, kind, delta, balance_after,
                    reason, created_at
                ) VALUES (?, ?, 'debit', ?, ?, ?, ?)
                """,
                (telegram_id, request_id, delta, new_balance, reason, now),
            )
            return delta, reason, new_balance

    async def grant_credits(
        self,
        telegram_id: int,
        amount: int,
        reason: str,
        request_id: str | None = None,
    ) -> int:
        if amount <= 0:
            raise ValueError("grant amount must be positive")
        now = utc_now_iso()
        async with self._db.transaction() as conn:
            cur = await conn.execute(
                "SELECT credits FROM users WHERE telegram_id = ?",
                (telegram_id,),
            )
            row = await cur.fetchone()
            if row is None:
                raise RuntimeError(f"user {telegram_id} not found")
            new_balance = int(row["credits"]) + amount
            await conn.execute(
                "UPDATE users SET credits = ?, updated_at = ? WHERE telegram_id = ?",
                (new_balance, now, telegram_id),
            )
            await conn.execute(
                """
                INSERT INTO ledger (
                    telegram_id, request_id, kind, delta, balance_after,
                    reason, created_at
                ) VALUES (?, ?, 'grant', ?, ?, ?, ?)
                """,
                (telegram_id, request_id, amount, new_balance, reason, now),
            )
            return new_balance

    async def insert_usage_event(
        self,
        *,
        request_id: str,
        telegram_id: int,
        conversation_id: int,
        model: str,
        usage: Usage | None,
        charge: Charge | None,
        status: str,
        error_text: str | None = None,
        credits_charged: int | None = None,
    ) -> None:
        now = utc_now_iso()
        u = usage or Usage()
        zero = "0.00000000"
        provider = charge.provider_cost_usd if charge else zero
        markup = charge.markup_usd if charge else zero
        billed = charge.billed_usd if charge else zero
        charged = (
            credits_charged
            if credits_charged is not None
            else (charge.credits_charged if charge else 0)
        )
        async with self._db.transaction() as conn:
            await conn.execute(
                """
                INSERT INTO usage_events (
                    request_id, telegram_id, conversation_id, model,
                    prompt_tokens, completion_tokens, reasoning_tokens, total_tokens,
                    provider_cost_usd, markup_usd, billed_usd, credits_charged,
                    status, error_text, raw_usage_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    request_id,
                    telegram_id,
                    conversation_id,
                    model,
                    u.prompt_tokens,
                    u.completion_tokens,
                    u.reasoning_tokens,
                    u.total_tokens,
                    provider,
                    markup,
                    billed,
                    charged,
                    status,
                    error_text,
                    u.raw_json,
                    now,
                ),
            )


    async def list_usage_events(self, telegram_id: int, limit: int = 5) -> list:
        cur = await self._db.conn.execute(
            """
            SELECT created_at, model, prompt_tokens, completion_tokens,
                   reasoning_tokens, total_tokens, credits_charged, status
            FROM usage_events
            WHERE telegram_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (telegram_id, limit),
        )
        return await cur.fetchall()
