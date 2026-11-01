"""Async SQLite access layer (aiosqlite, WAL, FK, serialized writes, explicit transactions)."""
from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import shutil
import sqlite3
import time
from pathlib import Path
from typing import Any, AsyncIterator, Iterable, Sequence

import aiosqlite

log = logging.getLogger(__name__)


def dumps(v: Any) -> str:
    return json.dumps(v, ensure_ascii=False, separators=(",", ":"))


def loads(v: str | bytes | None, default: Any = None) -> Any:
    if v is None or v == "":
        return default
    try:
        return json.loads(v)
    except (ValueError, TypeError):
        return default


class Tx:
    """Statements executed inside an open transaction (lock already held)."""

    def __init__(self, conn: aiosqlite.Connection) -> None:
        self.conn = conn

    async def execute(self, sql: str, params: Sequence[Any] | dict[str, Any] = ()) -> int:
        cur = await self.conn.execute(sql, params)
        rid = cur.lastrowid or 0
        await cur.close()
        return rid

    async def executemany(self, sql: str, seq: Iterable[Sequence[Any]]) -> None:
        await self.conn.executemany(sql, seq)

    async def fetchone(self, sql: str, params: Sequence[Any] = ()) -> dict[str, Any] | None:
        async with self.conn.execute(sql, params) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None

    async def fetchall(self, sql: str, params: Sequence[Any] = ()) -> list[dict[str, Any]]:
        async with self.conn.execute(sql, params) as cur:
            return [dict(r) for r in await cur.fetchall()]

    async def fetchval(self, sql: str, params: Sequence[Any] = (), default: Any = None) -> Any:
        async with self.conn.execute(sql, params) as cur:
            row = await cur.fetchone()
            return row[0] if row and row[0] is not None else default

    async def rowcount(self, sql: str, params: Sequence[Any] = ()) -> int:
        cur = await self.conn.execute(sql, params)
        n = cur.rowcount
        await cur.close()
        return n


class Database:
    def __init__(self, path: Path | str) -> None:
        self.path = str(path)
        self.conn: aiosqlite.Connection | None = None
        self._lock = asyncio.Lock()

    async def connect(self) -> None:
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = await aiosqlite.connect(self.path, isolation_level=None)
        self.conn.row_factory = aiosqlite.Row
        await self.conn.execute("PRAGMA journal_mode=WAL")
        await self.conn.execute("PRAGMA foreign_keys=ON")
        await self.conn.execute("PRAGMA synchronous=NORMAL")
        await self.conn.execute("PRAGMA busy_timeout=5000")
        await self.conn.execute("PRAGMA temp_store=MEMORY")

    async def close(self) -> None:
        if self.conn is not None:
            with contextlib.suppress(Exception):
                await self.conn.execute("PRAGMA optimize")
            await self.conn.close()
            self.conn = None

    @property
    def c(self) -> aiosqlite.Connection:
        if self.conn is None:
            raise RuntimeError("database is not connected")
        return self.conn

    # ---- writes (serialized) -------------------------------------------------------
    async def execute(self, sql: str, params: Sequence[Any] | dict[str, Any] = ()) -> int:
        async with self._lock:
            cur = await self.c.execute(sql, params)
            rid = cur.lastrowid or 0
            await cur.close()
            return rid

    async def rowcount(self, sql: str, params: Sequence[Any] = ()) -> int:
        async with self._lock:
            cur = await self.c.execute(sql, params)
            n = cur.rowcount
            await cur.close()
            return n

    async def executemany(self, sql: str, seq: Iterable[Sequence[Any]]) -> None:
        async with self.transaction() as tx:
            await tx.executemany(sql, seq)

    @contextlib.asynccontextmanager
    async def transaction(self) -> AsyncIterator[Tx]:
        async with self._lock:
            await self.c.execute("BEGIN IMMEDIATE")
            try:
                yield Tx(self.c)
            except BaseException:
                await self.c.execute("ROLLBACK")
                raise
            else:
                await self.c.execute("COMMIT")

    # ---- reads -------------------------------------------------------------------
    async def fetchone(self, sql: str, params: Sequence[Any] = ()) -> dict[str, Any] | None:
        async with self.c.execute(sql, params) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None

    async def fetchall(self, sql: str, params: Sequence[Any] = ()) -> list[dict[str, Any]]:
        async with self.c.execute(sql, params) as cur:
            return [dict(r) for r in await cur.fetchall()]

    async def fetchval(self, sql: str, params: Sequence[Any] = (), default: Any = None) -> Any:
        async with self.c.execute(sql, params) as cur:
            row = await cur.fetchone()
            return row[0] if row and row[0] is not None else default

    # ---- maintenance -------------------------------------------------------------
    async def integrity_check(self) -> dict[str, Any]:
        res = await self.fetchall("PRAGMA integrity_check")
        fk = await self.fetchall("PRAGMA foreign_key_check")
        ok = len(res) == 1 and list(res[0].values())[0] == "ok" and not fk
        return {"ok": ok, "integrity": [list(r.values())[0] for r in res][:20], "foreign_key_errors": len(fk)}

    async def backup_to(self, target: Path) -> Path:
        """Consistent online backup using SQLite backup API (safe during WAL writes)."""
        target.parent.mkdir(parents=True, exist_ok=True)
        async with self._lock:
            dst = await aiosqlite.connect(str(target))
            try:
                await self.c.backup(dst)
            finally:
                await dst.close()
        return target

    @staticmethod
    def restore_from(backup: Path, db_path: Path) -> None:
        """Offline restore (bot must be stopped). Validates the backup first."""
        con = sqlite3.connect(str(backup))
        try:
            r = con.execute("PRAGMA integrity_check").fetchone()
            if not r or r[0] != "ok":
                raise ValueError("backup integrity check failed")
        finally:
            con.close()
        for suffix in ("-wal", "-shm"):
            p = Path(str(db_path) + suffix)
            if p.exists():
                p.unlink()
        shutil.copy2(backup, db_path)

    async def size_info(self) -> dict[str, Any]:
        page_count = await self.fetchval("PRAGMA page_count", default=0)
        page_size = await self.fetchval("PRAGMA page_size", default=4096)
        free = await self.fetchval("PRAGMA freelist_count", default=0)
        return {"bytes": page_count * page_size, "free_pages": free, "path": self.path}

    async def vacuum(self) -> None:
        async with self._lock:
            await self.c.execute("VACUUM")


def ts() -> int:
    return int(time.time())
