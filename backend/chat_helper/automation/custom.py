"""Custom Command Builder: users compose their own commands from safe, predefined actions."""
from __future__ import annotations

import random
import re
import time
from typing import TYPE_CHECKING, Any

from aiogram.types import Message

from ..core.timeutil import local_dt
from ..database.db import dumps, loads
from ..security.sanitize import esc
from ..services.settings import MODES

if TYPE_CHECKING:  # pragma: no cover
    from ..business.connections import Conn
    from ..core.context import AppContext

SAFE_ACTIONS = ("text", "random", "template", "set_mode", "afk_on", "afk_off", "dice", "notify")
_NAME_RE = re.compile(r"^[a-zа-яё0-9_]{2,24}$")


def validate_custom(name: str, actions: list[dict[str, Any]], registry: Any) -> tuple[str, list[dict[str, Any]]]:
    name = (name or "").strip().lower().lstrip("./")
    if not _NAME_RE.match(name):
        raise ValueError("name: 2-24 letters/digits/_")
    if registry.resolve(name) is not None:
        raise ValueError("name collides with a built-in command")
    if not isinstance(actions, list) or not 1 <= len(actions) <= 5:
        raise ValueError("1..5 actions")
    out = []
    for a in actions:
        t = a.get("type")
        if t not in SAFE_ACTIONS:
            raise ValueError(f"action not allowed: {t}")
        c: dict[str, Any] = {"type": t}
        if t in ("text", "notify"):
            c["text"] = str(a.get("text") or "")[:2000]
            if not c["text"]:
                raise ValueError(f"{t}: text required")
        elif t == "random":
            opts = [str(o)[:500] for o in (a.get("options") or []) if str(o).strip()]
            if not 2 <= len(opts) <= 20:
                raise ValueError("random: 2..20 options")
            c["options"] = opts
        elif t == "template":
            c["name"] = str(a.get("name") or "").lower()[:40]
        elif t == "set_mode":
            if a.get("mode") not in MODES:
                raise ValueError("set_mode: invalid mode")
            c["mode"] = a["mode"]
        elif t == "afk_on":
            c["reason"] = str(a.get("reason") or "")[:200]
        elif t == "dice":
            c["emoji"] = a.get("emoji") if a.get("emoji") in ("🎲", "🎯", "🏀", "⚽", "🎳", "🎰") else "🎲"
        out.append(c)
    return name, out


class CustomCommandService:
    def __init__(self, app: "AppContext") -> None:
        self.app = app

    async def list(self, user_id: int) -> list[dict[str, Any]]:
        rows = await self.app.db.fetchall("SELECT * FROM custom_commands WHERE user_id=? ORDER BY name", (user_id,))
        for r in rows:
            r["actions"] = loads(r.pop("actions_json"), [])
        return rows

    async def find(self, user_id: int, name: str) -> dict[str, Any] | None:
        row = await self.app.db.fetchone("SELECT * FROM custom_commands WHERE user_id=? AND name=? AND enabled=1", (user_id, name.lower()))
        if row:
            row["actions"] = loads(row.pop("actions_json"), [])
        return row

    async def save(self, user_id: int, name: str, actions: list[dict[str, Any]], description: str = "") -> dict[str, Any]:
        name, clean = validate_custom(name, actions, self.app.registry)
        limit = await self.app.subs.limit(user_id, "custom_commands")
        existing = await self.app.db.fetchval("SELECT 1 FROM custom_commands WHERE user_id=? AND name=?", (user_id, name))
        n = await self.app.db.fetchval("SELECT COUNT(*) FROM custom_commands WHERE user_id=?", (user_id,), 0)
        if not existing and limit is not None and n >= limit:
            raise ValueError(f"custom command limit reached ({limit})")
        await self.app.db.execute(
            "INSERT INTO custom_commands(user_id, name, description, actions_json, created_at) VALUES (?,?,?,?,?) "
            "ON CONFLICT(user_id, name) DO UPDATE SET description=excluded.description, actions_json=excluded.actions_json, enabled=1",
            (user_id, name, description[:200], dumps(clean), int(time.time())))
        return await self.find(user_id, name)  # type: ignore[return-value]

    async def delete(self, user_id: int, name: str) -> bool:
        return await self.app.db.rowcount("DELETE FROM custom_commands WHERE user_id=? AND name=?", (user_id, name.lower())) > 0

    async def run(self, cmd: dict[str, Any], *, message: Message, user_id: int, source: str, conn: "Conn | None",
                  settings: dict[str, Any], parsed: Any) -> list[str]:
        app = self.app
        bc_id = conn.id if (conn and source == "business") else None
        chat_id = message.chat.id
        tz_name = settings.get("timezone") or app.config.timezone
        now = local_dt(None, tz_name)
        values = {"args": esc(parsed.raw_args), "time": now.strftime("%H:%M"), "date": now.strftime("%d.%m.%Y"),
                  "name": esc(message.chat.full_name or "")}

        def fill(t: str) -> str:
            out = esc(t)
            for k, v in values.items():
                out = out.replace("{" + k + "}", v)
            return out
        done = []
        edited = False
        for a in cmd["actions"]:
            t = a["type"]
            if t in ("text", "random", "template"):
                if t == "text":
                    body = fill(a["text"])
                elif t == "random":
                    body = fill(random.SystemRandom().choice(a["options"]))
                else:
                    row = await app.db.fetchone("SELECT text FROM reply_templates WHERE user_id=? AND name=?", (user_id, a["name"]))
                    body = fill(row["text"]) if row else "—"
                if source == "business" and not edited:
                    res = await app.sender.edit_text(chat_id, message.message_id, body, bc_id=bc_id)
                    edited = res.ok
                    if not res.ok:
                        await app.sender.send_text(chat_id, body, bc_id=bc_id)
                else:
                    await app.sender.send_text(chat_id, body, bc_id=bc_id)
            elif t == "set_mode":
                await app.autoreply.set_mode(user_id, a["mode"])
            elif t == "afk_on":
                await app.afk.enable(user_id, a.get("reason") or None)
            elif t == "afk_off":
                await app.afk.disable(user_id, reason="custom_command")
            elif t == "dice":
                await app.sender.send_dice(chat_id, a["emoji"], bc_id=bc_id)
            elif t == "notify":
                await app.sender.send_text(user_id, fill(a["text"]))
            done.append(t)
        await app.db.execute("UPDATE custom_commands SET uses=uses+1 WHERE id=?", (cmd["id"],))
        await app.metrics.incr("commands", user_id)
        await app.metrics.incr("cmd:custom")
        return done
