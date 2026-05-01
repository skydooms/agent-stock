from __future__ import annotations

import asyncio
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiosqlite


class CacheManager:
    """SQLite 缓存层，支持 TTL 和异步锁."""

    def __init__(self, db_path: str | Path = ".cache/agent_stock.db") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = asyncio.Lock()
        self._init_done = False

    async def _init(self) -> None:
        if self._init_done:
            return
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS cache (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    ttl INTEGER NOT NULL
                )
                """
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_cache_created ON cache(created_at)"
            )
            await db.commit()
        self._init_done = True

    async def get(self, key: str) -> Any | None:
        await self._init()
        async with self._lock:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    "SELECT value, created_at, ttl FROM cache WHERE key = ?",
                    (key,),
                ) as cursor:
                    row = await cursor.fetchone()
                    if row is None:
                        return None
                    now = int(datetime.now(timezone.utc).timestamp())
                    if now > row["created_at"] + row["ttl"]:
                        await db.execute("DELETE FROM cache WHERE key = ?", (key,))
                        await db.commit()
                        return None
                    return json.loads(row["value"])

    async def set(self, key: str, value: Any, ttl: int) -> None:
        await self._init()
        now = int(datetime.now(timezone.utc).timestamp())
        payload = json.dumps(value, default=str)
        async with self._lock:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    """
                    INSERT INTO cache (key, value, created_at, ttl)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(key) DO UPDATE SET
                        value=excluded.value,
                        created_at=excluded.created_at,
                        ttl=excluded.ttl
                    """,
                    (key, payload, now, ttl),
                )
                await db.commit()
                await self._prune_expired(db)

    async def _prune_expired(self, db: aiosqlite.Connection) -> None:
        now = int(datetime.now(timezone.utc).timestamp())
        await db.execute("DELETE FROM cache WHERE created_at + ttl < ?", (now,))
        await db.commit()

    async def clear(self) -> None:
        async with self._lock:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("DELETE FROM cache")
                await db.commit()
