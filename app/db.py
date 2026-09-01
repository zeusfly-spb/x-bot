from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    telegram_id INTEGER PRIMARY KEY,
    username TEXT NULL,
    first_name TEXT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    credits INTEGER NOT NULL DEFAULT 0,
    is_blocked INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER NOT NULL REFERENCES users(telegram_id),
    started_at TEXT NOT NULL,
    ended_at TEXT NULL,
    is_active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL REFERENCES conversations(id),
    telegram_id INTEGER NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL,
    request_id TEXT NULL
);

CREATE TABLE IF NOT EXISTS usage_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id TEXT NOT NULL UNIQUE,
    telegram_id INTEGER NOT NULL,
    conversation_id INTEGER NOT NULL,
    model TEXT NOT NULL,
    prompt_tokens INTEGER NOT NULL DEFAULT 0,
    completion_tokens INTEGER NOT NULL DEFAULT 0,
    reasoning_tokens INTEGER NOT NULL DEFAULT 0,
    total_tokens INTEGER NOT NULL DEFAULT 0,
    provider_cost_usd TEXT NOT NULL,
    markup_usd TEXT NOT NULL,
    billed_usd TEXT NOT NULL,
    credits_charged INTEGER NOT NULL,
    status TEXT NOT NULL,
    error_text TEXT NULL,
    raw_usage_json TEXT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ledger (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER NOT NULL,
    request_id TEXT NULL,
    kind TEXT NOT NULL,
    delta INTEGER NOT NULL,
    balance_after INTEGER NOT NULL,
    reason TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_messages_telegram_created
    ON messages(telegram_id, created_at);
CREATE INDEX IF NOT EXISTS idx_messages_conversation
    ON messages(conversation_id);
CREATE INDEX IF NOT EXISTS idx_messages_request
    ON messages(request_id);
CREATE INDEX IF NOT EXISTS idx_ledger_telegram_created
    ON ledger(telegram_id, created_at);
CREATE INDEX IF NOT EXISTS idx_conversations_user_active
    ON conversations(telegram_id, is_active);
CREATE INDEX IF NOT EXISTS idx_usage_telegram_created
    ON usage_events(telegram_id, created_at);
"""


class Database:
    def __init__(self, path: str) -> None:
        self._path = path
        self._conn: aiosqlite.Connection | None = None
        self.write_lock = asyncio.Lock()

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("Database is not connected")
        return self._conn

    async def connect(self) -> None:
        db_path = Path(self._path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self._path, isolation_level=None)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA foreign_keys = ON")
        await self._conn.execute("PRAGMA journal_mode = WAL")
        await self._conn.executescript(SCHEMA)

    @asynccontextmanager
    async def transaction(self):
        async with self.write_lock:
            await self.conn.execute("BEGIN IMMEDIATE")
            try:
                yield self.conn
                await self.conn.commit()
            except Exception:
                await self.conn.rollback()
                raise

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None
