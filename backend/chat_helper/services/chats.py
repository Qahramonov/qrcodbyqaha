"""Per-chat settings & Smart Inbox metadata. Every query is scoped by the owner user_id."""
from __future__ import annotations

import time
from typing import Any

from ..database.db import Database, dumps, loads

EDITABLE = {
    "ai_enabled": "tri", "afk_enabled": "tri", "autoreply_enabled": "tri", "language": "str",
    "style": "str", "reply_limit": "int", "priority": "int", "manual_confirm": "tri",
    "muted_until": "int", "ignored": "bool", "whitelisted": "bool", "tags": "list",
}


class ChatService:
    def __init__(self, db: Database) -> None:
        self.db = db

    async def touch(self, user_id: int, chat_id: int, *, title: str | None = None, username: str | None = None,
                    is_bot: bool = False, incoming: bool | None = None, preview: str | None = None) -> tuple[dict[str, Any], bool]:
        """Create/update chat row. Returns (row, is_new)."""
        now = int(time.time())
        existing = await self.get(user_id, chat_id)
        if existing is None:
            await self.db.execute(
                "INSERT OR IGNORE INTO chat_settings(user_id, chat_id, title, username, is_bot, first_seen_at, updated_at) "
                "VALUES (?,?,?,?,?,?,?)", (user_id, chat_id, title, username, 1 if is_bot else 0, now, now))
        sets = ["updated_at=?"]
        params: list[Any] = [now]
        if title:
            sets.append("title=?")
            params.append(title[:128])
        if username:
            sets.append("username=?")
            params.append(username[:64])
        if incoming is True:
            sets += ["last_incoming_at=?", "unanswered=unanswered+1"]
            params.append(now)
            if preview is not None:
                sets.append("last_preview=?")
                params.append(preview[:160])
        elif incoming is False:
            sets += ["last_outgoing_at=?", "unanswered=0"]
            params.append(now)
        params += [user_id, chat_id]
        await self.db.execute(f"UPDATE chat_settings SET {', '.join(sets)} WHERE user_id=? AND chat_id=?", params)
        row = await self.get(user_id, chat_id)
        return row or {}, existing is None

    async def get(self, user_id: int, chat_id: int) -> dict[str, Any] | None:
        row = await self.db.fetchone("SELECT * FROM chat_settings WHERE user_id=? AND chat_id=?", (user_id, chat_id))
        if row:
            row["tags"] = loads(row.pop("tags_json", "[]"), [])
        return row

    async def list(self, user_id: int, q: str | None = None, sort: str = "recent", page: int = 1,
                   page_size: int = 50, only_unanswered: bool = False) -> dict[str, Any]:
        where = ["user_id=?"]
        params: list[Any] = [user_id]
        if q:
            where.append("(LOWER(COALESCE(title,'')) LIKE ? OR LOWER(COALESCE(username,'')) LIKE ? OR CAST(chat_id AS TEXT)=?)")
            like = f"%{q.lower().lstrip('@')}%"
            params += [like, like, q]
        if only_unanswered:
            where.append("unanswered > 0")
        order = {"recent": "COALESCE(last_incoming_at,0) DESC", "priority": "priority DESC, priority_score DESC",
                 "name": "LOWER(COALESCE(title,'')) ASC"}.get(sort, "COALESCE(last_incoming_at,0) DESC")
        wsql = " AND ".join(where)
        total = await self.db.fetchval(f"SELECT COUNT(*) FROM chat_settings WHERE {wsql}", params, 0)
        page = max(1, page)
        page_size = max(1, min(page_size, 200))
        rows = await self.db.fetchall(f"SELECT * FROM chat_settings WHERE {wsql} ORDER BY {order} LIMIT ? OFFSET ?",
                                      params + [page_size, (page - 1) * page_size])
        for r in rows:
            r["tags"] = loads(r.pop("tags_json", "[]"), [])
        return {"items": rows, "total": total, "page": page, "page_size": page_size}

    async def update(self, user_id: int, chat_id: int, values: dict[str, Any]) -> dict[str, Any] | None:
        if await self.get(user_id, chat_id) is None:
            return None
        sets, params = [], []
        for k, v in values.items():
            kind = EDITABLE.get(k)
            if kind is None:
                raise ValueError(f"field not editable: {k}")
            if kind == "tri":
                v = None if v is None else (1 if bool(v) else 0)
            elif kind == "bool":
                v = 1 if bool(v) else 0
            elif kind == "int":
                v = None if v is None else int(v)
                if k == "priority" and v is not None and not -5 <= v <= 5:
                    raise ValueError("priority must be -5..5")
                if k == "reply_limit" and v is not None and not 0 <= v <= 500:
                    raise ValueError("reply_limit must be 0..500")
            elif kind == "str":
                v = None if v in (None, "") else str(v)[:32]
            elif kind == "list":
                if not isinstance(v, list) or len(v) > 20:
                    raise ValueError("tags must be a list (max 20)")
                k, v = "tags_json", dumps([str(x)[:32] for x in v])
            sets.append(f"{k}=?")
            params.append(v)
        if sets:
            sets.append("updated_at=?")
            params += [int(time.time()), user_id, chat_id]
            await self.db.execute(f"UPDATE chat_settings SET {', '.join(sets)} WHERE user_id=? AND chat_id=?", params)
        return await self.get(user_id, chat_id)

    async def set_owner_pause(self, user_id: int, chat_id: int, minutes: int) -> None:
        until = int(time.time()) + minutes * 60 if minutes > 0 else None
        await self.db.execute("UPDATE chat_settings SET owner_paused_until=? WHERE user_id=? AND chat_id=?",
                              (until, user_id, chat_id))

    async def count_auto_reply(self, user_id: int, chat_id: int) -> int:
        """Increments today's auto-reply counter for the chat and returns new value."""
        from ..core.timeutil import today
        d = today()
        await self.db.execute(
            "UPDATE chat_settings SET auto_replies_today = CASE WHEN auto_replies_day=? THEN auto_replies_today+1 ELSE 1 END, "
            "auto_replies_day=?, last_auto_reply_at=? WHERE user_id=? AND chat_id=?",
            (d, d, int(time.time()), user_id, chat_id))
        return int(await self.db.fetchval("SELECT auto_replies_today FROM chat_settings WHERE user_id=? AND chat_id=?",
                                          (user_id, chat_id), 0))

    async def auto_replies_today(self, user_id: int, chat_id: int) -> int:
        from ..core.timeutil import today
        row = await self.db.fetchone("SELECT auto_replies_today, auto_replies_day FROM chat_settings WHERE user_id=? AND chat_id=?",
                                     (user_id, chat_id))
        if not row or row["auto_replies_day"] != today():
            return 0
        return int(row["auto_replies_today"])

    async def set_priority_score(self, user_id: int, chat_id: int, score: int) -> None:
        await self.db.execute("UPDATE chat_settings SET priority_score=? WHERE user_id=? AND chat_id=?",
                              (score, user_id, chat_id))

    async def delete_data(self, user_id: int, chat_id: int) -> None:
        async with self.db.transaction() as tx:
            await tx.execute("DELETE FROM ai_history WHERE user_id=? AND chat_id=?", (user_id, chat_id))
            await tx.execute("DELETE FROM ai_memory WHERE user_id=? AND chat_id=?", (user_id, chat_id))
            await tx.execute("DELETE FROM ai_drafts WHERE user_id=? AND chat_id=?", (user_id, chat_id))
            await tx.execute("DELETE FROM chat_permissions WHERE user_id=? AND chat_id=?", (user_id, chat_id))
            await tx.execute("DELETE FROM chat_settings WHERE user_id=? AND chat_id=?", (user_id, chat_id))

    async def clear_previews(self, user_id: int) -> None:
        await self.db.execute("UPDATE chat_settings SET last_preview=NULL WHERE user_id=?", (user_id,))
