"""Users, roles and account status. Roles are always resolved on the server side."""
from __future__ import annotations

import time
from typing import Any

from ..database.db import Database

ROLE_SUPER = "super_admin"
ROLE_MOD = "moderator"
ROLE_USER = "user"


class UserService:
    def __init__(self, db: Database, super_admin_id: int) -> None:
        self.db = db
        self.super_admin_id = int(super_admin_id)

    async def upsert(self, user_id: int, username: str | None = None, first_name: str | None = None,
                     last_name: str | None = None, language: str | None = None, touch: bool = True) -> dict[str, Any]:
        now = int(time.time())
        lang = language if language in ("ru", "uz") else None
        await self.db.execute(
            "INSERT INTO users(id, username, first_name, last_name, language, created_at, last_seen_at) "
            "VALUES (?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET "
            "username=COALESCE(excluded.username, users.username), "
            "first_name=COALESCE(excluded.first_name, users.first_name), "
            "last_name=excluded.last_name, "
            "last_seen_at=CASE WHEN ? THEN excluded.last_seen_at ELSE users.last_seen_at END",
            (user_id, username, first_name, last_name, lang or "ru", now, now if touch else None, 1 if touch else 0))
        return await self.get(user_id)  # type: ignore[return-value]

    async def ensure(self, user_id: int) -> None:
        await self.db.execute("INSERT OR IGNORE INTO users(id, created_at) VALUES (?,?)", (user_id, int(time.time())))

    async def get(self, user_id: int) -> dict[str, Any] | None:
        return await self.db.fetchone("SELECT * FROM users WHERE id=?", (user_id,))

    async def role(self, user_id: int) -> str:
        """v3: exactly one administrator — the numeric SUPER_ADMIN_ID from configuration.

        Usernames, legacy ``moderator`` rows in ``admin_roles`` and request parameters never grant admin rights.
        Users can instead *delegate* specific settings to the super admin (see services/delegation.py).
        """
        return ROLE_SUPER if self.is_super_id(user_id) else ROLE_USER

    def is_super_id(self, user_id: int | None) -> bool:
        try:
            return user_id is not None and int(user_id) == self.super_admin_id
        except (TypeError, ValueError):
            return False

    async def is_admin(self, user_id: int) -> bool:
        return self.is_super_id(user_id)

    async def set_role(self, user_id: int, role: str | None, granted_by: int) -> None:
        if int(user_id) == self.super_admin_id:
            raise ValueError("super admin role is fixed by configuration")
        if role is None or role == ROLE_USER:
            # removes a legacy v1/v2 moderator row; such rows are ignored by role() anyway
            await self.db.execute("DELETE FROM admin_roles WHERE user_id=?", (user_id,))
            return
        raise ValueError("only the configured super admin has admin access in v3; use delegated management instead")

    async def is_restricted(self, user_id: int) -> bool:
        if int(user_id) == self.super_admin_id:
            return False
        return (await self.db.fetchval("SELECT status FROM users WHERE id=?", (user_id,))) == "restricted"

    async def restrict(self, user_id: int, reason: str) -> None:
        if int(user_id) == self.super_admin_id:
            raise ValueError("cannot restrict the super admin")
        await self.db.execute("UPDATE users SET status='restricted', restricted_reason=? WHERE id=?", (reason[:300], user_id))

    async def restore(self, user_id: int) -> None:
        await self.db.execute("UPDATE users SET status='active', restricted_reason=NULL WHERE id=?", (user_id,))

    async def set_language(self, user_id: int, lang: str) -> None:
        if lang in ("ru", "uz"):
            await self.db.execute("UPDATE users SET language=? WHERE id=?", (lang, user_id))

    async def set_bot_blocked(self, user_id: int, blocked: bool) -> None:
        await self.db.execute("UPDATE users SET bot_blocked=? WHERE id=?", (1 if blocked else 0, user_id))

    async def list(self, q: str | None = None, plan: str | None = None, active_days: int | None = None,
                   connected: bool | None = None, status: str | None = None, sort: str = "last_seen",
                   page: int = 1, page_size: int = 30) -> dict[str, Any]:
        where = ["1=1"]
        params: list[Any] = []
        if q:
            if q.lstrip("-").isdigit():
                where.append("u.id=?")
                params.append(int(q))
            else:
                where.append("(LOWER(u.username) LIKE ? OR LOWER(u.first_name) LIKE ? OR LOWER(u.last_name) LIKE ?)")
                like = f"%{q.lower().lstrip('@')}%"
                params += [like, like, like]
        if status:
            where.append("u.status=?")
            params.append(status)
        if active_days:
            where.append("u.last_seen_at >= ?")
            params.append(int(time.time()) - active_days * 86400)
        if connected is not None:
            cond = "EXISTS (SELECT 1 FROM business_connections bc WHERE bc.user_id=u.id AND bc.is_enabled=1)"
            where.append(cond if connected else f"NOT {cond}")
        plan_sql = ("COALESCE((SELECT s.plan_id FROM subscriptions s WHERE s.user_id=u.id AND s.status='active' "
                    "AND (s.expires_at IS NULL OR s.expires_at > strftime('%s','now')) ORDER BY s.id DESC LIMIT 1),'free')")
        if plan:
            where.append(f"{plan_sql}=?")
            params.append(plan)
        order = {
            "last_seen": "u.last_seen_at DESC",
            "created": "u.created_at DESC",
            "name": "LOWER(COALESCE(u.first_name, u.username, '')) ASC",
            "id": "u.id ASC",
        }.get(sort, "u.last_seen_at DESC")
        page = max(1, page)
        page_size = max(1, min(page_size, 100))
        wsql = " AND ".join(where)
        total = await self.db.fetchval(f"SELECT COUNT(*) FROM users u WHERE {wsql}", params, 0)
        rows = await self.db.fetchall(
            f"SELECT u.*, {plan_sql} AS plan, "
            "(SELECT COUNT(*) FROM business_connections bc WHERE bc.user_id=u.id AND bc.is_enabled=1) AS active_connections "
            f"FROM users u WHERE {wsql} ORDER BY {order} LIMIT ? OFFSET ?",
            params + [page_size, (page - 1) * page_size])
        return {"items": rows, "total": total, "page": page, "page_size": page_size}

    async def count(self) -> int:
        return int(await self.db.fetchval("SELECT COUNT(*) FROM users", default=0))

    async def delete_user_data(self, user_id: int) -> None:
        """GDPR-style erase of everything owned by the user (cascade + loose tables)."""
        async with self.db.transaction() as tx:
            for sql in (
                "DELETE FROM command_history WHERE user_id=?",
                "DELETE FROM ai_usage WHERE user_id=?",
                "DELETE FROM ai_costs WHERE user_id=?",
                "DELETE FROM media_jobs WHERE user_id=?",
                "DELETE FROM game_sessions WHERE owner_id=?",
                "DELETE FROM game_results WHERE owner_id=?",
                "DELETE FROM game_ratings WHERE owner_id=?",
                "DELETE FROM scheduled_tasks WHERE user_id=?",
                "DELETE FROM notification_events WHERE user_id=?",
                "DELETE FROM module_settings WHERE user_id=?",
                "DELETE FROM daily_metrics WHERE user_id=?",
                "DELETE FROM automation_executions WHERE user_id=?",
                "DELETE FROM business_connections WHERE user_id=?",
                "DELETE FROM user_settings WHERE user_id=?",
                "DELETE FROM chat_settings WHERE user_id=?",
                "DELETE FROM chat_permissions WHERE user_id=?",
                "DELETE FROM ai_history WHERE user_id=?",
                "DELETE FROM ai_memory WHERE user_id=?",
                "DELETE FROM ai_profiles WHERE user_id=?",
                "DELETE FROM ai_drafts WHERE user_id=?",
                "DELETE FROM afk_sessions WHERE user_id=?",
                "DELETE FROM autoresponse_rules WHERE user_id=?",
                "DELETE FROM reply_templates WHERE user_id=?",
                "DELETE FROM automation_rules WHERE user_id=?",
                "DELETE FROM custom_commands WHERE user_id=?",
                "DELETE FROM profile_history WHERE user_id=?",
                # v3 tables
                "DELETE FROM chat_control_states WHERE owner_id=?",
                "DELETE FROM control_messages WHERE owner_id=?",
                "DELETE FROM mute_rules WHERE owner_id=?",
                "DELETE FROM mute_events WHERE owner_id=?",
                "DELETE FROM ai_twin_profiles WHERE user_id=?",
                "DELETE FROM animation_jobs WHERE owner_id=?",
                "DELETE FROM repetition_jobs WHERE owner_id=?",
                "DELETE FROM reminders WHERE owner_id=?",
                "DELETE FROM permission_snapshots WHERE owner_id=?",
                "DELETE FROM delegated_permissions WHERE owner_id=?",
                "DELETE FROM delegation_consents WHERE owner_id=?",
                "DELETE FROM chat_messages WHERE owner_id=?",
                "DELETE FROM pairing_codes WHERE user_id=?",
            ):
                await tx.execute(sql, (user_id,))
            await tx.execute("UPDATE admin_sessions SET revoked_at=?, revoke_reason='data_deleted' "
                             "WHERE user_id=? AND revoked_at IS NULL", (int(time.time()), user_id))
