"""Business connection lifecycle: register, rights tracking, restore after restart, isolation."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from ..database.db import Database, dumps, loads
from .rights import RIGHT_FLAGS, connection_status, rights_from_obj

log = logging.getLogger(__name__)


@dataclass
class Conn:
    id: str
    user_id: int
    user_chat_id: int
    is_enabled: bool
    paused: bool
    status: str
    rights: dict[str, bool] = field(default_factory=dict)
    connected_at: int = 0
    last_event_at: int | None = None

    def can(self, right: str) -> bool:
        return bool(self.rights.get(right))

    @property
    def active(self) -> bool:
        return self.is_enabled and not self.paused

    def as_dict(self) -> dict[str, Any]:
        return {"id": self.id, "user_id": self.user_id, "user_chat_id": self.user_chat_id,
                "is_enabled": self.is_enabled, "paused": self.paused, "status": self.status,
                "rights": self.rights, "connected_at": self.connected_at, "last_event_at": self.last_event_at}


@dataclass
class ConnChange:
    conn: Conn
    kind: str  # new | enabled | disabled | rights_changed | unchanged
    added_rights: list[str] = field(default_factory=list)
    removed_rights: list[str] = field(default_factory=list)


class ConnectionService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self._cache: dict[str, Conn] = {}

    @staticmethod
    def _row_to_conn(row: dict[str, Any]) -> Conn:
        rights = loads(row.get("rights_json"), {}) or {}
        rights = {k: bool(rights.get(k)) for k in RIGHT_FLAGS}
        return Conn(id=row["id"], user_id=row["user_id"], user_chat_id=row["user_chat_id"],
                    is_enabled=bool(row["is_enabled"]), paused=bool(row["paused"]), status=row["status"],
                    rights=rights, connected_at=row["connected_at"], last_event_at=row.get("last_event_at"))

    async def get(self, connection_id: str) -> Conn | None:
        if connection_id in self._cache:
            return self._cache[connection_id]
        row = await self.db.fetchone(
            "SELECT bc.*, br.rights_json FROM business_connections bc LEFT JOIN business_rights br "
            "ON br.connection_id = bc.id WHERE bc.id=?", (connection_id,))
        if not row:
            return None
        conn = self._row_to_conn(row)
        self._cache[connection_id] = conn
        return conn

    async def for_user(self, user_id: int) -> list[Conn]:
        rows = await self.db.fetchall(
            "SELECT bc.*, br.rights_json FROM business_connections bc LEFT JOIN business_rights br "
            "ON br.connection_id = bc.id WHERE bc.user_id=? ORDER BY bc.is_enabled DESC, bc.updated_at DESC", (user_id,))
        return [self._row_to_conn(r) for r in rows]

    async def primary_for_user(self, user_id: int) -> Conn | None:
        conns = await self.for_user(user_id)
        for c in conns:
            if c.is_enabled:
                return c
        return conns[0] if conns else None

    async def all(self, enabled_only: bool = False) -> list[Conn]:
        sql = ("SELECT bc.*, br.rights_json FROM business_connections bc LEFT JOIN business_rights br "
               "ON br.connection_id = bc.id")
        if enabled_only:
            sql += " WHERE bc.is_enabled=1"
        return [self._row_to_conn(r) for r in await self.db.fetchall(sql + " ORDER BY bc.updated_at DESC")]

    async def upsert(self, connection_id: str, user_id: int, user_chat_id: int, is_enabled: bool,
                     rights_obj: Any, date: int | None = None) -> ConnChange:
        rights = rights_from_obj(rights_obj)
        old = await self.get(connection_id)
        now = int(time.time())
        paused = old.paused if old else False
        status = connection_status(is_enabled, rights, paused)
        async with self.db.transaction() as tx:
            await tx.execute("INSERT OR IGNORE INTO users(id, created_at) VALUES (?,?)", (user_id, now))
            await tx.execute(
                "INSERT INTO business_connections(id, user_id, user_chat_id, is_enabled, status, paused, connected_at, updated_at, "
                "last_event_at, disconnected_at) VALUES (?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET "
                "user_chat_id=excluded.user_chat_id, is_enabled=excluded.is_enabled, status=excluded.status, "
                "updated_at=excluded.updated_at, last_event_at=excluded.last_event_at, "
                "disconnected_at=CASE WHEN excluded.is_enabled=0 THEN excluded.updated_at ELSE NULL END",
                (connection_id, user_id, user_chat_id, 1 if is_enabled else 0, status, 1 if paused else 0,
                 int(date or now), now, now, None if is_enabled else now))
            await tx.execute(
                "INSERT INTO business_rights(connection_id, rights_json, updated_at) VALUES (?,?,?) "
                "ON CONFLICT(connection_id) DO UPDATE SET rights_json=excluded.rights_json, updated_at=excluded.updated_at",
                (connection_id, dumps(rights), now))
        self._cache.pop(connection_id, None)
        conn = await self.get(connection_id)
        assert conn is not None
        if old is None:
            kind = "new"
        elif old.is_enabled and not is_enabled:
            kind = "disabled"
        elif not old.is_enabled and is_enabled:
            kind = "enabled"
        elif old.rights != rights:
            kind = "rights_changed"
        else:
            kind = "unchanged"
        added = [r for r in RIGHT_FLAGS if rights.get(r) and not (old.rights.get(r) if old else False)]
        removed = [r for r in RIGHT_FLAGS if not rights.get(r) and (old.rights.get(r) if old else False)]
        return ConnChange(conn=conn, kind=kind, added_rights=added, removed_rights=removed)

    async def touch(self, connection_id: str, incoming: bool) -> None:
        col = "messages_in" if incoming else "messages_out"
        await self.db.execute(f"UPDATE business_connections SET last_event_at=?, {col}={col}+1 WHERE id=?",
                              (int(time.time()), connection_id))
        c = self._cache.get(connection_id)
        if c:
            c.last_event_at = int(time.time())

    async def set_paused(self, connection_id: str, user_id: int, paused: bool) -> Conn | None:
        conn = await self.get(connection_id)
        if conn is None or conn.user_id != user_id:
            return None
        status = connection_status(conn.is_enabled, conn.rights, paused)
        await self.db.execute("UPDATE business_connections SET paused=?, status=?, updated_at=? WHERE id=?",
                              (1 if paused else 0, status, int(time.time()), connection_id))
        self._cache.pop(connection_id, None)
        return await self.get(connection_id)

    async def mark_status(self, connection_id: str, status: str) -> None:
        await self.db.execute("UPDATE business_connections SET status=?, updated_at=? WHERE id=?",
                              (status, int(time.time()), connection_id))
        self._cache.pop(connection_id, None)

    async def restore(self, bot: Any) -> dict[str, int]:
        """Re-sync every known enabled connection with Telegram after a restart."""
        stats = {"checked": 0, "updated": 0, "failed": 0}
        for conn in await self.all(enabled_only=True):
            stats["checked"] += 1
            try:
                bc = await bot.get_business_connection(business_connection_id=conn.id)
                await self.upsert(bc.id, bc.user.id, bc.user_chat_id, bc.is_enabled, bc.rights,
                                  int(bc.date.timestamp()) if hasattr(bc.date, "timestamp") else None)
                stats["updated"] += 1
            except Exception as e:  # network or invalid connection
                stats["failed"] += 1
                msg = str(e).upper()
                if "BUSINESS_CONNECTION" in msg or "NOT FOUND" in msg or "INVALID" in msg:
                    await self.mark_status(conn.id, "reconnection_required")
                log.warning("restore of business connection failed: %s", type(e).__name__)
        return stats

    def invalidate(self, connection_id: str | None = None) -> None:
        if connection_id is None:
            self._cache.clear()
        else:
            self._cache.pop(connection_id, None)

    async def counts(self) -> dict[str, int]:
        rows = await self.db.fetchall("SELECT status, COUNT(*) AS n FROM business_connections GROUP BY status")
        out = {r["status"]: r["n"] for r in rows}
        out["active"] = int(await self.db.fetchval("SELECT COUNT(*) FROM business_connections WHERE is_enabled=1", default=0))
        out["total"] = int(await self.db.fetchval("SELECT COUNT(*) FROM business_connections", default=0))
        return out
