"""Application container shared by Telegram handlers, background workers and the REST API."""
from __future__ import annotations

import logging
import time
from typing import Any

from ..database.db import Database, dumps, loads

log = logging.getLogger(__name__)

MODULES = ("afk", "ai", "voice", "media", "games", "text", "profile", "autoreply", "automation", "system",
           "broadcast", "payments")


class Runtime:
    """Global runtime switches (Emergency Stop, maintenance, paused modules). Persisted in module_settings(0, '__runtime__')."""

    def __init__(self, db: Database) -> None:
        self.db = db
        self.emergency_stop = False
        self.maintenance = False
        self.paused_modules: set[str] = set()
        self.extra: dict[str, Any] = {}

    async def load(self) -> None:
        row = await self.db.fetchone("SELECT config_json FROM module_settings WHERE user_id=0 AND module='__runtime__'")
        data = loads(row["config_json"], {}) if row else {}
        self.emergency_stop = bool(data.get("emergency_stop"))
        self.maintenance = bool(data.get("maintenance"))
        self.paused_modules = set(data.get("paused_modules") or [])
        self.extra = data.get("extra") or {}

    async def save(self) -> None:
        data = {"emergency_stop": self.emergency_stop, "maintenance": self.maintenance,
                "paused_modules": sorted(self.paused_modules), "extra": self.extra}
        await self.db.execute(
            "INSERT INTO module_settings(user_id, module, enabled, config_json, updated_at) VALUES (0,'__runtime__',1,?,?) "
            "ON CONFLICT(user_id, module) DO UPDATE SET config_json=excluded.config_json, updated_at=excluded.updated_at",
            (dumps(data), int(time.time())))

    def is_module_paused(self, module: str) -> bool:
        return module in self.paused_modules

    def as_dict(self) -> dict[str, Any]:
        return {"emergency_stop": self.emergency_stop, "maintenance": self.maintenance,
                "paused_modules": sorted(self.paused_modules), "modules": list(MODULES), "extra": self.extra}


class AppContext:
    """Populated by ``chat_helper.app.build_app``. Attributes are typed loosely to avoid import cycles."""

    def __init__(self) -> None:
        self.config: Any = None
        self.db: Database = None  # type: ignore[assignment]
        self.bot: Any = None
        self.bot_info: Any = None
        self.events: Any = None
        self.runtime: Runtime = None  # type: ignore[assignment]
        self.users: Any = None
        self.settings: Any = None
        self.chats: Any = None
        self.connections: Any = None
        self.audit: Any = None
        self.metrics: Any = None
        self.notifications: Any = None
        self.quotas: Any = None
        self.limiter: Any = None
        self.dedup: Any = None
        self.loop_guard: Any = None
        self.sender: Any = None
        self.registry: Any = None
        self.executor: Any = None
        self.custom_commands: Any = None
        self.ai: Any = None
        self.ai_auto: Any = None
        self.pipeline: Any = None
        self.media: Any = None
        self.games: Any = None
        self.afk: Any = None
        self.autoreply: Any = None
        self.automation: Any = None
        self.subs: Any = None
        self.payments: Any = None
        self.scheduler: Any = None
        self.broadcast: Any = None
        self.health: Any = None
        self.auth: Any = None
        self.profile: Any = None
        self.backups: Any = None
        self.inbox: Any = None
        self.flags: Any = None
        self.started_at = time.time()
        self.polling_active = False
        self.tasks: list[Any] = []

    @property
    def uptime(self) -> int:
        return int(time.time() - self.started_at)
