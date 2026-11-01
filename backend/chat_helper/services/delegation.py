"""Delegated management: a user voluntarily lets the super admin help with specific settings.

Business rights of the bot never imply that the administrator may act on a user's account. Each scope is granted
by the user, can expire, can be revoked at any time and every use is recorded in ``delegation_consents``.
Profile changes additionally need a per-change confirmation by the user. Stars/Gifts operations are never delegable.
"""
from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from ..database.db import dumps, loads

if TYPE_CHECKING:  # pragma: no cover
    from ..core.context import AppContext

SCOPES: dict[str, tuple[str, str]] = {
    "ai": ("🧠 Настройки AI и AI-двойника", "🧠 AI va AI-egizak sozlamalari"),
    "afk": ("💤 AFK и автоответчик", "💤 AFK va avtojavob"),
    "commands": ("⌨️ Включение/выключение команд", "⌨️ Buyruqlarni yoqish/o'chirish"),
    "automation": ("⚙️ Правила автоматизации", "⚙️ Avtomatlashtirish qoidalari"),
    "diagnostics": ("🩺 Просмотр технической диагностики", "🩺 Texnik diagnostikani ko'rish"),
    "profile": ("👤 Профиль (каждое изменение подтверждаете вы)", "👤 Profil (har bir o'zgarishni siz tasdiqlaysiz)"),
}
# settings keys an administrator may change for each granted scope
SCOPE_KEYS: dict[str, tuple[str, ...]] = {
    "ai": ("ai_style", "ai_language", "ai_confirm", "ai_debounce_sec", "ai_reply_limit_per_chat_day", "ai_disclosure",
           "ai_context_messages", "ai_daily_summary", "ai_priority_detection"),
    "afk": ("mode", "afk_cooldown_min", "afk_auto_off", "afk_ai", "afk_notify_summary", "afk_text_morning", "afk_text_day",
            "afk_text_evening", "afk_text_night", "autoreply_cooldown_sec", "max_auto_replies_per_chat_day", "welcome_enabled",
            "welcome_text", "work_start", "work_end", "work_days", "offhours_text"),
    "commands": ("disabled_commands", "prefix", "delete_commands"),
    "automation": ("automation_paused",),
}


class DelegationService:
    def __init__(self, app: "AppContext") -> None:
        self.app = app

    async def grants(self, owner_id: int) -> dict[str, dict[str, Any]]:
        rows = await self.app.db.fetchall("SELECT * FROM delegated_permissions WHERE owner_id=?", (owner_id,))
        now = time.time()
        return {r["scope"]: {**r, "active": r["revoked_at"] is None and (r["expires_at"] is None or r["expires_at"] > now)} for r in rows}

    async def is_granted(self, owner_id: int, scope: str) -> bool:
        g = (await self.grants(owner_id)).get(scope)
        return bool(g and g["active"])

    async def _log(self, owner_id: int, scope: str, action: str, actor_id: int, **details: Any) -> int:
        return await self.app.db.execute(
            "INSERT INTO delegation_consents(owner_id, scope, action, actor_id, details_json, created_at) VALUES (?,?,?,?,?,?)",
            (owner_id, scope, action, actor_id, dumps(details), int(time.time())))

    async def grant(self, owner_id: int, scope: str, days: int | None = None) -> None:
        if scope not in SCOPES:
            raise ValueError("unknown scope")
        now = int(time.time())
        await self.app.db.execute(
            "INSERT INTO delegated_permissions(owner_id, scope, granted_at, expires_at, revoked_at) VALUES (?,?,?,?,NULL) "
            "ON CONFLICT(owner_id, scope) DO UPDATE SET granted_at=excluded.granted_at, expires_at=excluded.expires_at, revoked_at=NULL",
            (owner_id, scope, now, now + days * 86400 if days else None))
        await self._log(owner_id, scope, "grant", owner_id, days=days)
        await self.app.audit.log("delegation.grant", actor_id=owner_id, target_type="delegation", target_id=scope, days=days)

    async def revoke(self, owner_id: int, scope: str) -> None:
        await self.app.db.execute("UPDATE delegated_permissions SET revoked_at=? WHERE owner_id=? AND scope=?",
                                  (int(time.time()), owner_id, scope))
        await self._log(owner_id, scope, "revoke", owner_id)
        await self.app.audit.log("delegation.revoke", actor_id=owner_id, target_type="delegation", target_id=scope)

    async def history(self, owner_id: int, limit: int = 30) -> list[dict[str, Any]]:
        rows = await self.app.db.fetchall("SELECT * FROM delegation_consents WHERE owner_id=? ORDER BY id DESC LIMIT ?", (owner_id, limit))
        for r in rows:
            r["details"] = loads(r.pop("details_json"), {})
        return rows

    def scope_for_key(self, key: str) -> str | None:
        for scope, keys in SCOPE_KEYS.items():
            if key in keys:
                return scope
        return None

    async def admin_update_settings(self, actor_id: int, owner_id: int, values: dict[str, Any]) -> dict[str, Any]:
        """Super admin changes a user's settings — only keys inside scopes the user granted. Every change is logged."""
        if not self.app.users.is_super_id(actor_id):
            raise PermissionError("only the super admin")
        for key in values:
            scope = self.scope_for_key(key)
            if scope is None or not await self.is_granted(owner_id, scope):
                raise PermissionError(f"not delegated: {key}")
        await self.app.settings.update(owner_id, values)
        for key in values:
            await self._log(owner_id, self.scope_for_key(key) or "?", "use", actor_id, key=key)
        await self.app.audit.log("delegation.use", actor_id=actor_id, target_type="user", target_id=owner_id, keys=sorted(values))
        return await self.app.settings.all(owner_id)

    # ---- profile: per-change confirmation by the user -----------------------------------------------------------
    async def request_profile_change(self, actor_id: int, owner_id: int, field: str, value: str) -> int:
        if not self.app.users.is_super_id(actor_id):
            raise PermissionError("only the super admin")
        if field not in ("name", "bio"):
            raise ValueError("field must be name or bio")
        if not await self.is_granted(owner_id, "profile"):
            raise PermissionError("not delegated: profile")
        rid = await self._log(owner_id, "profile", "request", actor_id, field=field, value=value[:140], status="pending")
        from ..keyboards import kb
        from ..localization import tr
        from ..security.sanitize import esc
        s = await self.app.settings.all(owner_id)
        lang = s["lang"]
        await self.app.sender.send_text(owner_id, tr(
            lang, "🤝 Администратор предлагает изменить ваш профиль ({f}):\n<code>{v}</code>\nПрименить?",
            "🤝 Administrator profilingizni o'zgartirishni taklif qilmoqda ({f}):\n<code>{v}</code>\nQo'llansinmi?", f=field, v=esc(value[:140])),
            markup=kb([[(tr(lang, "✅ Применить", "✅ Qo'llash"), f"dlg:ok:{rid}"), (tr(lang, "✖️ Отклонить", "✖️ Rad etish"), f"dlg:no:{rid}")]]))
        return rid

    async def decide_profile_change(self, owner_id: int, request_id: int, approve: bool) -> str:
        row = await self.app.db.fetchone("SELECT * FROM delegation_consents WHERE id=? AND owner_id=? AND action='request'", (request_id, owner_id))
        if row is None:
            return "not_found"
        details = loads(row["details_json"], {})
        if details.get("status") != "pending":
            return "already_decided"
        details["status"] = "approved" if approve else "rejected"
        await self.app.db.execute("UPDATE delegation_consents SET details_json=? WHERE id=?", (dumps(details), request_id))
        if not approve:
            return "rejected"
        if not await self.is_granted(owner_id, "profile"):
            return "not_delegated"
        res = await self.app.profile.apply_change(owner_id, details["field"], details["value"], source="delegation")
        await self._log(owner_id, "profile", "use", row["actor_id"], field=details["field"], result=str(res)[:60])
        return "applied" if res else "failed"
