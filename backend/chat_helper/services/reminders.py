"""Reminders: personal (bot DM) and chat reminders (posted into the business chat at the given time).

Stored in ``reminders`` and executed by the persistent scheduler, so they survive restarts. A chat reminder needs
the *can_reply* right and Telegram's 24-hour window at the moment it fires; if Telegram refuses, the owner gets the
reminder in the DM together with the reason — it is never silently lost.
"""
from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from ..localization import tr
from ..security.sanitize import esc

if TYPE_CHECKING:  # pragma: no cover
    from ..core.context import AppContext

MAX_PENDING = 50


class ReminderService:
    def __init__(self, app: "AppContext") -> None:
        self.app = app

    async def create(self, owner: int, text: str, run_at: int, *, kind: str = "dm", chat_id: int | None = None,
                     connection_id: str | None = None) -> dict[str, Any]:
        if kind not in ("dm", "chat"):
            raise ValueError("kind must be dm or chat")
        if kind == "chat" and (chat_id is None or not connection_id):
            raise ValueError("chat reminder needs chat_id and connection")
        now = int(time.time())
        if not now + 20 <= run_at <= now + 366 * 86400:
            raise ValueError("time out of range")
        pending = await self.app.db.fetchval("SELECT COUNT(*) FROM reminders WHERE owner_id=? AND status='pending'", (owner,), 0)
        if pending >= MAX_PENDING:
            raise ValueError("too many pending reminders")
        rid = await self.app.db.execute(
            "INSERT INTO reminders(owner_id, kind, connection_id, chat_id, text, run_at, status, created_at) VALUES (?,?,?,?,?,?,'pending',?)",
            (owner, kind, connection_id, chat_id, text[:1000], run_at, now))
        task_id = await self.app.scheduler.add(owner, "reminder" if kind == "dm" else "reminder_chat", {"rid": rid, "text": text[:1000]}, run_at)
        await self.app.db.execute("UPDATE reminders SET task_id=? WHERE id=?", (task_id, rid))
        return await self.get(owner, rid)  # type: ignore[return-value]

    async def get(self, owner: int, rid: int) -> dict[str, Any] | None:
        return await self.app.db.fetchone("SELECT * FROM reminders WHERE id=? AND owner_id=?", (rid, owner))

    async def list(self, owner: int, status: str | None = "pending", limit: int = 50) -> list[dict[str, Any]]:
        if status:
            return await self.app.db.fetchall("SELECT * FROM reminders WHERE owner_id=? AND status=? ORDER BY run_at LIMIT ?", (owner, status, limit))
        return await self.app.db.fetchall("SELECT * FROM reminders WHERE owner_id=? ORDER BY id DESC LIMIT ?", (owner, limit))

    async def cancel(self, owner: int, rid: int) -> bool:
        row = await self.get(owner, rid)
        if not row or row["status"] != "pending":
            return False
        if row["task_id"]:
            await self.app.scheduler.cancel(row["task_id"], owner)
        await self.app.db.execute("UPDATE reminders SET status='cancelled', done_at=? WHERE id=?", (int(time.time()), rid))
        return True

    async def _finish(self, rid: int, status: str, error: str | None = None) -> None:
        await self.app.db.execute("UPDATE reminders SET status=?, error=?, done_at=? WHERE id=?", (status, error, int(time.time()), rid))

    # ---- scheduler handlers ---------------------------------------------------------------------------------------
    async def fire_dm(self, task: dict[str, Any]) -> None:
        owner, p = task["user_id"], task["payload"]
        res = await self.app.sender.send_text(owner, "⏰ " + esc(p.get("text") or ""))
        if p.get("rid"):
            await self._finish(int(p["rid"]), "done" if res.ok else "failed", None if res.ok else res.kind)

    async def fire_chat(self, task: dict[str, Any]) -> None:
        owner, p = task["user_id"], task["payload"]
        row = await self.app.db.fetchone("SELECT * FROM reminders WHERE id=? AND owner_id=?", (p.get("rid"), owner))
        if row is None or row["status"] != "pending":
            return
        s = await self.app.settings.all(owner)
        conn = await self.app.connections.get(row["connection_id"]) if row["connection_id"] else None
        reason = None
        if conn is None or not conn.is_enabled or conn.user_id != owner:
            reason = tr(s["lang"], "бизнес-подключение отключено", "biznes ulanish uzilgan")
        elif not conn.can("can_reply"):
            reason = tr(s["lang"], "нет права «Ответы на сообщения»", "«Xabarlarga javob berish» huquqi yo'q")
        else:
            res = await self.app.sender.send_text(row["chat_id"], "⏰ " + esc(row["text"]), bc_id=conn.id)
            if res.ok:
                await self._finish(row["id"], "done")
                return
            reason = {"window_24h": tr(s["lang"], "собеседник не писал 24 часа (ограничение Telegram)",
                                       "suhbatdosh 24 soat yozmagan (Telegram cheklovi)")}.get(res.kind, res.kind)
        await self._finish(row["id"], "failed", reason)
        await self.app.sender.send_text(owner, tr(s["lang"], "⏰ Напоминание для чата не отправлено ({r}). Вот оно:\n{t}",
                                                  "⏰ Chat uchun eslatma yuborilmadi ({r}). Mana u:\n{t}", r=esc(reason or ""), t=esc(row["text"])))
