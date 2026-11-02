"""Incoming-message filters of a business chat: 🔕 Mute, 🚫 NoGIF and 🧹 word filter (.nomute).

Rules (deliberately strict):
* only **new incoming** messages of the counterpart are touched — never the owner's messages, never other chats,
  never history from before the mode was enabled;
* deletion uses the official ``deleteBusinessMessages`` and needs the business right *can_delete_all_messages*
  («Удаление входящих» in Telegram settings);
* every attempt is logged in ``mute_events`` (unique per message → repeated updates are not processed twice);
* if Telegram refuses, the owner is told the real reason — we never claim a message disappeared when it did not.
"""
from __future__ import annotations

import logging
import re
import time
from typing import TYPE_CHECKING, Any

from aiogram.types import Message

from ..business import sender as S
from ..database.db import dumps, loads
from ..localization import tr

if TYPE_CHECKING:  # pragma: no cover
    from ..business.connections import Conn
    from ..core.context import AppContext

log = logging.getLogger(__name__)

MUTE_TYPES = ("all", "text", "media", "photo", "video", "voice", "circle", "gif", "sticker", "document", "audio")
MEDIA_KINDS = {"photo", "video", "voice", "circle", "gif", "sticker", "document", "audio"}
NOGIF_TYPES = ("gif", "sticker", "circle")
TYPE_TITLES = {
    "all": ("chat_filters.type_titles.vsyo"), "text": ("chat_filters.type_titles.tekst"), "media": ("chat_filters.type_titles.vse_media"), "photo": ("chat_filters.type_titles.foto"),
    "video": ("chat_filters.type_titles.video"), "voice": ("chat_filters.type_titles.golosovye"), "circle": ("chat_filters.type_titles.kruzhki"), "gif": ("chat_filters.type_titles.gif"),
    "sticker": ("chat_filters.type_titles.stikery"), "document": ("chat_filters.type_titles.fayly"), "audio": ("chat_filters.type_titles.audio"),
}
TYPE_ALIASES = {
    "все": "all", "всё": "all", "hammasi": "all", "текст": "text", "matn": "text", "медиа": "media", "фото": "photo", "rasm": "photo",
    "видео": "video", "голос": "voice", "голосовые": "voice", "ovoz": "voice", "кружки": "circle", "кружок": "circle", "гиф": "gif",
    "гифки": "gif", "стикеры": "sticker", "стикер": "sticker", "stiker": "sticker", "файлы": "document", "file": "document",
    "аудио": "audio", "stickers": "sticker", "gifs": "gif", "voices": "voice", "circles": "circle", "note": "circle",
}


def message_kind(m: Message) -> str | None:
    if m.animation:
        return "gif"
    if m.sticker:
        return "sticker"
    if m.video_note:
        return "circle"
    for attr, kind in (("voice", "voice"), ("photo", "photo"), ("video", "video"), ("audio", "audio"), ("document", "document")):
        if getattr(m, attr, None):
            return kind
    if m.text:
        return "text"
    for attr in ("location", "contact", "poll", "dice", "venue"):
        if getattr(m, attr, None):
            return attr
    return None  # service / unknown content → never deleted


def type_title(t: str, lang: str) -> str:
    key = TYPE_TITLES.get(t)
    return tr(lang, key) if key else t


def normalize_type(word: str) -> str | None:
    w = word.lower().strip()
    if w in MUTE_TYPES:
        return w
    return TYPE_ALIASES.get(w)


def mute_matches(kind: str | None, types: list[str], keep: list[str]) -> bool:
    if kind is None or kind in keep or ("media" in keep and kind in MEDIA_KINDS):
        return False
    if "all" in types:
        return True
    if "media" in types and kind in MEDIA_KINDS:
        return True
    return kind in types


def word_matches(text: str, words: list[str]) -> str | None:
    low = text.lower()
    for w in words:
        w = w.strip().lower()
        if w and re.search(r"(?<!\w)" + re.escape(w) + r"(?!\w)", low):
            return w
    return None


class FilterEngine:
    def __init__(self, app: "AppContext") -> None:
        self.app = app
        self._rights_warned: dict[tuple[int, int], float] = {}

    # ---- personal mute settings (defaults chat_id=0, optional per-chat override) -----------------------------
    async def mute_settings(self, owner_id: int, chat_id: int) -> dict[str, Any]:
        rows = await self.app.db.fetchall("SELECT * FROM mute_rules WHERE owner_id=? AND chat_id IN (0, ?) ORDER BY chat_id", (owner_id, chat_id))
        out = {"types": ["all"], "keep": [], "whitelist": [], "report": True, "scope": "default"}
        for r in rows:  # defaults first, then the chat override
            out = {"types": loads(r["types_json"], ["all"]) or ["all"], "keep": loads(r["keep_types_json"], []) or [],
                   "whitelist": loads(r["whitelist_json"], []) or [], "report": bool(r["report"]),
                   "scope": "chat" if r["chat_id"] else "default"}
        return out

    async def set_mute_settings(self, owner_id: int, chat_id: int, *, types: list[str] | None = None, keep: list[str] | None = None,
                                whitelist: list[str] | None = None, report: bool | None = None) -> dict[str, Any]:
        cur = await self.mute_settings(owner_id, chat_id)
        types = [t for t in (types if types is not None else cur["types"]) if t in MUTE_TYPES] or ["all"]
        keep = [t for t in (keep if keep is not None else cur["keep"]) if t in MUTE_TYPES and t != "all"]
        wl = [w.strip()[:40] for w in (whitelist if whitelist is not None else cur["whitelist"]) if w and w.strip()][:30]
        rep = cur["report"] if report is None else bool(report)
        await self.app.db.execute(
            "INSERT INTO mute_rules(owner_id, chat_id, types_json, keep_types_json, whitelist_json, report, updated_at) VALUES (?,?,?,?,?,?,?) "
            "ON CONFLICT(owner_id, chat_id) DO UPDATE SET types_json=excluded.types_json, keep_types_json=excluded.keep_types_json, "
            "whitelist_json=excluded.whitelist_json, report=excluded.report, updated_at=excluded.updated_at",
            (owner_id, chat_id, dumps(types), dumps(keep), dumps(wl), 1 if rep else 0, int(time.time())))
        return await self.mute_settings(owner_id, chat_id)

    # ---- incoming --------------------------------------------------------------------------------------------
    async def decide(self, owner_id: int, chat_id: int, message: Message) -> tuple[str, str] | None:
        """Return (source, reason) if this incoming message must be deleted."""
        ctl = self.app.controls
        states = await ctl.states(owner_id, chat_id)
        if not states:
            return None
        kind = message_kind(message)
        if kind is None:
            return None
        text = message.text or message.caption or ""
        now = time.time()

        def on(module: str) -> dict[str, Any] | None:
            row = states.get(module)
            if row and row["enabled"] and not (row.get("until_at") and row["until_at"] <= now):
                return row
            return None

        if on("mute"):
            ms = await self.mute_settings(owner_id, chat_id)
            if not (text and word_matches(text, ms["whitelist"])) and mute_matches(kind, ms["types"], ms["keep"]):
                return "mute", kind
        row = on("nogif")
        if row and kind in (row["state"].get("types") or ["gif", "sticker"]):
            return "nogif", kind
        row = on("nomute")
        if row and text:
            hit = word_matches(text, row["state"].get("words") or [])
            if hit:
                return "nomute", kind
        return None

    async def handle_incoming(self, conn: "Conn", message: Message) -> str | None:
        """Called first for every counterpart message. Returns the filter name if the message was deleted."""
        owner, chat_id = conn.user_id, message.chat.id
        if message.from_user is not None and message.from_user.id == owner:
            return None  # never the owner's own messages
        decision = await self.decide(owner, chat_id, message)
        if decision is None:
            return None
        source, kind = decision
        db = self.app.db
        fresh = await db.rowcount(
            "INSERT OR IGNORE INTO mute_events(owner_id, chat_id, message_id, msg_type, source, result, created_at) VALUES (?,?,?,?,?,?,?)",
            (owner, chat_id, message.message_id, kind, source, "pending", int(time.time())))
        if not fresh:
            return source  # duplicate update: already handled
        if not conn.can("can_delete_all_messages"):
            await self._result(owner, chat_id, message.message_id, source, "failed:no_right")
            await self._warn_rights(conn, chat_id)
            return None
        res = await self.app.sender.delete(chat_id, [message.message_id], bc_id=conn.id)
        if res.ok:
            await self._result(owner, chat_id, message.message_id, source, "deleted")
            await self.app.controls.incr(owner, chat_id, source, "deleted")
            await self.app.metrics.incr(f"filter_deleted:{source}", owner)
            self.app.events.emit("filter_deleted", user_id=owner, chat_id=chat_id, source=source, kind=kind)
            return source
        await self._result(owner, chat_id, message.message_id, source, f"failed:{res.kind}")
        if res.kind in (S.RIGHTS, S.FORBIDDEN):
            await self._warn_rights(conn, chat_id)
        elif res.kind == S.CONNECTION:
            await self.app.connections.mark_status(conn.id, "reconnection_required")
        return None

    async def _result(self, owner: int, chat_id: int, message_id: int, source: str, result: str) -> None:
        await self.app.db.execute("UPDATE mute_events SET result=? WHERE owner_id=? AND chat_id=? AND message_id=? AND source=?",
                                  (result, owner, chat_id, message_id, source))

    async def _warn_rights(self, conn: "Conn", chat_id: int) -> None:
        key = (conn.user_id, chat_id)
        if time.time() - self._rights_warned.get(key, 0) < 3600:
            return
        self._rights_warned[key] = time.time()
        s = await self.app.settings.all(conn.user_id)
        await self.app.sender.send_text(conn.user_id, tr(
            s["lang"], "chat_filters.telegram_razreshil_udalit_vhodyaschee_soobscheni"))

    async def stats(self, owner_id: int, chat_id: int | None = None, since: int | None = None) -> dict[str, int]:
        sql = "SELECT result, COUNT(*) AS n FROM mute_events WHERE owner_id=?"
        params: list[Any] = [owner_id]
        if chat_id is not None:
            sql += " AND chat_id=?"
            params.append(chat_id)
        if since is not None:
            sql += " AND created_at>=?"
            params.append(since)
        rows = await self.app.db.fetchall(sql + " GROUP BY result", params)
        out = {"deleted": 0, "failed": 0}
        for r in rows:
            out["deleted" if r["result"] == "deleted" else "failed"] += r["n"]
        return out
