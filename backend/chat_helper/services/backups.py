"""Backup Center (consistent SQLite online backups with retention) and personal data export."""
from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..database.db import loads

if TYPE_CHECKING:  # pragma: no cover
    from ..core.context import AppContext


class BackupService:
    def __init__(self, app: "AppContext") -> None:
        self.app = app
        self.dir: Path = app.config.backups_dir

    async def create(self, kind: str = "auto") -> Path:
        name = time.strftime(f"chat_helper_%Y%m%d_%H%M%S_{kind}.db")
        path = await self.app.db.backup_to(self.dir / name)
        await self.app.audit.log("system.backup", actor_type="system", target_type="backup", target_id=name, size=path.stat().st_size)
        await self.prune()
        return path

    async def prune(self) -> int:
        keep = max(1, self.app.config.backup_keep)
        files = sorted(self.dir.glob("chat_helper_*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
        removed = 0
        for f in files[keep:]:
            f.unlink(missing_ok=True)
            removed += 1
        return removed

    def list(self) -> list[dict[str, Any]]:
        return [{"name": f.name, "size": f.stat().st_size, "created_at": int(f.stat().st_mtime)}
                for f in sorted(self.dir.glob("chat_helper_*.db"), key=lambda p: p.stat().st_mtime, reverse=True)]

    async def auto(self) -> Path | None:
        files = self.list()
        if files and time.time() - files[0]["created_at"] < self.app.config.backup_interval_hours * 3600:
            return None
        return await self.create("auto")

    async def export_user(self, uid: int) -> dict[str, Any]:
        db = self.app.db

        async def q(sql: str, *params: Any) -> list[dict[str, Any]]:
            return await db.fetchall(sql, params)
        user = await db.fetchone("SELECT * FROM users WHERE id=?", (uid,))
        data: dict[str, Any] = {
            "exported_at": int(time.time()), "product": "Chat helper", "user": user,
            "settings": await self.app.settings.all(uid),
            "business_connections": [c.as_dict() for c in await self.app.connections.for_user(uid)],
            "chats": await q("SELECT chat_id, title, username, ai_enabled, afk_enabled, autoreply_enabled, language, style, priority, ignored, "
                             "whitelisted, tags_json, last_incoming_at, last_outgoing_at FROM chat_settings WHERE user_id=?", uid),
            "autoreply_rules": await q("SELECT * FROM autoresponse_rules WHERE user_id=?", uid),
            "reply_templates": await q("SELECT name, text, created_at FROM reply_templates WHERE user_id=?", uid),
            "automation_rules": await q("SELECT * FROM automation_rules WHERE user_id=?", uid),
            "custom_commands": await q("SELECT name, description, actions_json, uses FROM custom_commands WHERE user_id=?", uid),
            "ai_profiles": await q("SELECT * FROM ai_profiles WHERE user_id=?", uid),
            "ai_memory": await q("SELECT id, chat_id, kind, content, created_at, expires_at FROM ai_memory WHERE user_id=?", uid),
            "ai_history": await q("SELECT chat_id, role, content, created_at FROM ai_history WHERE user_id=? ORDER BY id DESC LIMIT 2000", uid),
            "ai_usage_daily": await q("SELECT * FROM ai_costs WHERE user_id=?", uid),
            "afk_sessions": await q("SELECT * FROM afk_sessions WHERE user_id=?", uid),
            "subscriptions": await q("SELECT * FROM subscriptions WHERE user_id=?", uid),
            "payments": await q("SELECT id, plan_id, amount, currency, status, created_at FROM payments WHERE user_id=?", uid),
            "game_results": await q("SELECT game, winner_id, loser_id, draw, created_at FROM game_results WHERE owner_id=? LIMIT 2000", uid),
            "profile_history": await q("SELECT * FROM profile_history WHERE user_id=?", uid),
            "app_sessions": await self.app.auth.sessions(uid, include_revoked=True),
            "notifications": await q("SELECT * FROM notification_events WHERE user_id=? ORDER BY id DESC LIMIT 500", uid),
            "command_history": await q("SELECT command_id, source, ok, created_at FROM command_history WHERE user_id=? ORDER BY id DESC LIMIT 2000", uid),
        }
        for r in data["chats"]:
            r["tags"] = loads(r.pop("tags_json", "[]"), [])
        return data
