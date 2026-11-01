"""Chat Control Framework — per-chat module states and interactive control messages.

* ``chat_control_states``: one row per (owner, chat, module) — mute, protect, nogif, nomute … with optional timer.
* ``control_messages``: every message with control buttons (in the business chat or in the bot DM). The callback data
  carries an unguessable token + a *version*; the version increases on each state change, so an old/duplicate button
  press can never flip a state twice (idempotency) and cards of a revoked connection stop working.
* ``control_actions``: processed callback ids (exactly-once handling of repeated deliveries) + audit trail.

All queries are scoped by ``owner_id`` — data of different users is never mixed.
"""
from __future__ import annotations

import secrets
import time
from typing import Any

from ..database.db import Database, dumps, loads

MODULES = ("mute", "protect", "nogif", "nomute", "afk", "auto", "re", "online", "activity")


class ChatControlService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self._cache: dict[tuple[int, int], dict[str, dict[str, Any]]] = {}

    # ---- states -------------------------------------------------------------------------------------------
    @staticmethod
    def _row(r: dict[str, Any]) -> dict[str, Any]:
        r = dict(r)
        r["enabled"] = bool(r["enabled"])
        r["state"] = loads(r.pop("state_json", "{}"), {}) or {}
        return r

    async def states(self, owner_id: int, chat_id: int) -> dict[str, dict[str, Any]]:
        key = (owner_id, chat_id)
        if key not in self._cache:
            rows = await self.db.fetchall("SELECT * FROM chat_control_states WHERE owner_id=? AND chat_id=?", key)
            self._cache[key] = {r["module"]: self._row(r) for r in rows}
        return self._cache[key]

    async def get(self, owner_id: int, chat_id: int, module: str) -> dict[str, Any] | None:
        return (await self.states(owner_id, chat_id)).get(module)

    async def is_on(self, owner_id: int, chat_id: int, module: str) -> bool:
        row = await self.get(owner_id, chat_id, module)
        if not row or not row["enabled"]:
            return False
        return not (row.get("until_at") and row["until_at"] <= time.time())

    async def set(self, owner_id: int, chat_id: int, module: str, enabled: bool, *, until_at: int | None = None,
                  state: dict[str, Any] | None = None, connection_id: str | None = None, keep_until: bool = False) -> dict[str, Any]:
        if module not in MODULES:
            raise ValueError(f"unknown module {module}")
        now = int(time.time())
        cur = await self.get(owner_id, chat_id, module)
        new_state = dict(cur["state"]) if cur else {}
        if state:
            new_state.update(state)
        if keep_until and cur:
            until_at = cur.get("until_at")
        if not enabled:
            until_at = None
        await self.db.execute(
            "INSERT INTO chat_control_states(owner_id, chat_id, module, enabled, state_json, until_at, connection_id, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(owner_id, chat_id, module) DO UPDATE SET enabled=excluded.enabled, "
            "state_json=excluded.state_json, until_at=excluded.until_at, "
            "connection_id=COALESCE(excluded.connection_id, chat_control_states.connection_id), updated_at=excluded.updated_at",
            (owner_id, chat_id, module, 1 if enabled else 0, dumps(new_state), until_at, connection_id, now))
        self._cache.pop((owner_id, chat_id), None)
        return await self.get(owner_id, chat_id, module)  # type: ignore[return-value]

    async def update_state(self, owner_id: int, chat_id: int, module: str, **values: Any) -> None:
        row = await self.get(owner_id, chat_id, module)
        if not row:
            return
        st = dict(row["state"])
        st.update(values)
        await self.db.execute("UPDATE chat_control_states SET state_json=?, updated_at=? WHERE owner_id=? AND chat_id=? AND module=?",
                              (dumps(st), int(time.time()), owner_id, chat_id, module))
        self._cache.pop((owner_id, chat_id), None)

    async def incr(self, owner_id: int, chat_id: int, module: str, field: str, by: int = 1) -> int:
        row = await self.get(owner_id, chat_id, module)
        if not row:
            return 0
        val = int(row["state"].get(field, 0)) + by
        await self.update_state(owner_id, chat_id, module, **{field: val})
        return val

    async def active(self, owner_id: int | None = None, module: str | None = None) -> list[dict[str, Any]]:
        sql = "SELECT * FROM chat_control_states WHERE enabled=1"
        params: list[Any] = []
        if owner_id is not None:
            sql += " AND owner_id=?"
            params.append(owner_id)
        if module is not None:
            sql += " AND module=?"
            params.append(module)
        rows = await self.db.fetchall(sql + " ORDER BY updated_at DESC LIMIT 500", params)
        now = time.time()
        return [self._row(r) for r in rows if not (r["until_at"] and r["until_at"] <= now)]

    async def due_for_expiry(self) -> list[dict[str, Any]]:
        rows = await self.db.fetchall("SELECT * FROM chat_control_states WHERE enabled=1 AND until_at IS NOT NULL AND until_at<=?",
                                      (int(time.time()),))
        return [self._row(r) for r in rows]

    async def counts(self) -> dict[str, int]:
        rows = await self.db.fetchall("SELECT module, COUNT(*) AS n FROM chat_control_states WHERE enabled=1 GROUP BY module")
        return {r["module"]: r["n"] for r in rows}

    def invalidate(self, owner_id: int | None = None) -> None:
        if owner_id is None:
            self._cache.clear()
            return
        for k in [k for k in self._cache if k[0] == owner_id]:
            self._cache.pop(k, None)

    # ---- control messages ---------------------------------------------------------------------------------
    async def create_card(self, owner_id: int, chat_id: int, module: str, *, location: str, host_chat_id: int,
                          message_id: int | None, connection_id: str | None) -> str:
        token = secrets.token_urlsafe(8)[:10]
        now = int(time.time())
        await self.db.execute(
            "INSERT INTO control_messages(token, owner_id, connection_id, chat_id, module, location, host_chat_id, message_id, "
            "version, status, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,0,'active',?,?)",
            (token, owner_id, connection_id, chat_id, module, location, host_chat_id, message_id, now, now))
        return token

    async def card(self, token: str) -> dict[str, Any] | None:
        if not token or len(token) > 16:
            return None
        return await self.db.fetchone("SELECT * FROM control_messages WHERE token=?", (token,))

    async def set_card_message(self, token: str, message_id: int, location: str | None = None, host_chat_id: int | None = None) -> None:
        sets, params = ["message_id=?", "updated_at=?"], [message_id, int(time.time())]
        if location:
            sets.append("location=?")
            params.append(location)
        if host_chat_id is not None:
            sets.append("host_chat_id=?")
            params.append(host_chat_id)
        await self.db.execute(f"UPDATE control_messages SET {', '.join(sets)} WHERE token=?", (*params, token))

    async def cards(self, owner_id: int, chat_id: int, module: str) -> list[dict[str, Any]]:
        return await self.db.fetchall(
            "SELECT * FROM control_messages WHERE owner_id=? AND chat_id=? AND module=? AND status='active' ORDER BY created_at DESC LIMIT 5",
            (owner_id, chat_id, module))

    async def bump(self, owner_id: int, chat_id: int, module: str) -> None:
        """State changed → invalidate every older button (version check in callbacks)."""
        await self.db.execute("UPDATE control_messages SET version=version+1, updated_at=? WHERE owner_id=? AND chat_id=? AND module=? "
                              "AND status='active'", (int(time.time()), owner_id, chat_id, module))

    async def close_card(self, token: str, status: str = "closed") -> None:
        await self.db.execute("UPDATE control_messages SET status=?, updated_at=? WHERE token=?", (status, int(time.time()), token))

    async def revoke_connection(self, connection_id: str) -> int:
        return await self.db.rowcount("UPDATE control_messages SET status='revoked', updated_at=? WHERE connection_id=? AND status='active'",
                                      (int(time.time()), connection_id))

    async def record_action(self, callback_id: str, token: str, actor_id: int, action: str, result: str) -> bool:
        """False if this callback id was already processed (Telegram may redeliver an update)."""
        n = await self.db.rowcount(
            "INSERT OR IGNORE INTO control_actions(callback_id, token, actor_id, action, result, created_at) VALUES (?,?,?,?,?,?)",
            (callback_id[:64], token, actor_id, action[:32], result[:64], int(time.time())))
        return n == 1

    async def cleanup(self, days: int = 30) -> int:
        cutoff = int(time.time()) - days * 86400
        n = await self.db.rowcount("DELETE FROM control_actions WHERE created_at<?", (cutoff,))
        n += await self.db.rowcount("DELETE FROM control_messages WHERE status!='active' AND updated_at<?", (cutoff,))
        return n
