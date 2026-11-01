"""AI memory: per-chat short-term history, consented long-term facts, summaries, retention, export."""
from __future__ import annotations

import time
from typing import Any

from ..database.db import Database

MAX_HISTORY_PER_CHAT = 60


class AIMemory:
    def __init__(self, db: Database) -> None:
        self.db = db

    # ---- short-term history (strictly per owner + chat) ---------------------------
    async def add(self, user_id: int, chat_id: int, role: str, content: str) -> None:
        if not content:
            return
        await self.db.execute("INSERT INTO ai_history(user_id, chat_id, role, content, created_at) VALUES (?,?,?,?,?)",
                              (user_id, chat_id, role, content[:4000], int(time.time())))
        n = await self.db.fetchval("SELECT COUNT(*) FROM ai_history WHERE user_id=? AND chat_id=?", (user_id, chat_id), 0)
        if n > MAX_HISTORY_PER_CHAT:
            await self.db.execute(
                "DELETE FROM ai_history WHERE id IN (SELECT id FROM ai_history WHERE user_id=? AND chat_id=? ORDER BY id ASC LIMIT ?)",
                (user_id, chat_id, n - MAX_HISTORY_PER_CHAT))

    async def history(self, user_id: int, chat_id: int, limit: int = 12) -> list[dict[str, Any]]:
        if limit <= 0:
            return []
        rows = await self.db.fetchall("SELECT role, content, created_at FROM ai_history WHERE user_id=? AND chat_id=? ORDER BY id DESC LIMIT ?",
                                      (user_id, chat_id, limit))
        return list(reversed(rows))

    async def clear_chat(self, user_id: int, chat_id: int) -> int:
        n = await self.db.rowcount("DELETE FROM ai_history WHERE user_id=? AND chat_id=?", (user_id, chat_id))
        n += await self.db.rowcount("DELETE FROM ai_memory WHERE user_id=? AND chat_id=? AND kind='summary'", (user_id, chat_id))
        return n

    async def chat_stats(self, user_id: int, chat_id: int) -> dict[str, Any]:
        row = await self.db.fetchone("SELECT COUNT(*) AS messages, MIN(created_at) AS since, COALESCE(SUM(LENGTH(content)),0) AS chars "
                                     "FROM ai_history WHERE user_id=? AND chat_id=?", (user_id, chat_id))
        facts = await self.db.fetchval("SELECT COUNT(*) FROM ai_memory WHERE user_id=? AND (chat_id=? OR chat_id IS NULL)", (user_id, chat_id), 0)
        return {**(row or {}), "facts": facts}

    # ---- long-term facts (owner-consented) ------------------------------------------
    async def remember(self, user_id: int, content: str, chat_id: int | None = None, kind: str = "fact",
                       source: str = "manual", ttl_days: int | None = None) -> int:
        expires = int(time.time()) + ttl_days * 86400 if ttl_days else None
        return await self.db.execute(
            "INSERT INTO ai_memory(user_id, chat_id, kind, content, source, created_at, expires_at) VALUES (?,?,?,?,?,?,?)",
            (user_id, chat_id, kind, content[:1000], source, int(time.time()), expires))

    async def facts(self, user_id: int, chat_id: int | None = None, kind: str = "fact", limit: int = 30) -> list[str]:
        now = int(time.time())
        if chat_id is None:
            rows = await self.db.fetchall("SELECT content FROM ai_memory WHERE user_id=? AND chat_id IS NULL AND kind=? AND "
                                          "(expires_at IS NULL OR expires_at > ?) ORDER BY id DESC LIMIT ?", (user_id, kind, now, limit))
        else:
            rows = await self.db.fetchall("SELECT content FROM ai_memory WHERE user_id=? AND chat_id=? AND kind=? AND "
                                          "(expires_at IS NULL OR expires_at > ?) ORDER BY id DESC LIMIT ?", (user_id, chat_id, kind, now, limit))
        return [r["content"] for r in rows]

    async def list(self, user_id: int, limit: int = 100) -> list[dict[str, Any]]:
        return await self.db.fetchall("SELECT id, chat_id, kind, content, source, created_at, expires_at FROM ai_memory WHERE user_id=? "
                                      "ORDER BY id DESC LIMIT ?", (user_id, limit))

    async def forget(self, user_id: int, memory_id: int | None = None, query: str | None = None) -> int:
        if memory_id is not None:
            return await self.db.rowcount("DELETE FROM ai_memory WHERE id=? AND user_id=?", (memory_id, user_id))
        if query:
            return await self.db.rowcount("DELETE FROM ai_memory WHERE user_id=? AND LOWER(content) LIKE ?", (user_id, f"%{query.lower()}%"))
        return 0

    async def clear_all(self, user_id: int) -> int:
        n = await self.db.rowcount("DELETE FROM ai_memory WHERE user_id=?", (user_id,))
        n += await self.db.rowcount("DELETE FROM ai_history WHERE user_id=?", (user_id,))
        return n

    async def count(self, user_id: int) -> int:
        return int(await self.db.fetchval("SELECT COUNT(*) FROM ai_memory WHERE user_id=? AND kind='fact'", (user_id,), 0))

    # ---- retention -------------------------------------------------------------------
    async def apply_retention(self, settings_service: Any) -> int:
        """Delete history older than each user's retention setting; delete expired facts."""
        now = int(time.time())
        removed = await self.db.rowcount("DELETE FROM ai_memory WHERE expires_at IS NOT NULL AND expires_at < ?", (now,))
        users = await self.db.fetchall("SELECT DISTINCT user_id FROM ai_history")
        for u in users:
            days = await settings_service.get(u["user_id"], "history_retention_days")
            removed += await self.db.rowcount("DELETE FROM ai_history WHERE user_id=? AND created_at < ?", (u["user_id"], now - int(days) * 86400))
        return removed
