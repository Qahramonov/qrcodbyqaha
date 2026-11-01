"""Business message pipeline: incoming (counterpart) and outgoing (owner) messages.

Order for incoming messages: dedup → bookkeeping → games → smart inbox → no-code automation →
auto reply (AFK / rules / business hours / AI). Every automated send passes the same safety gates.
"""
from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any

from aiogram.types import Message

from ..business.connections import Conn
from ..core.timeutil import day_part
from ..localization import tr
from ..security.sanitize import clip, esc
from .autoreply import fill

if TYPE_CHECKING:  # pragma: no cover
    from ..core.context import AppContext

log = logging.getLogger(__name__)


def media_type(m: Message) -> str | None:
    for kind in ("voice", "video_note", "audio", "video", "photo", "animation", "sticker", "document",
                 "location", "contact", "poll", "dice"):
        if getattr(m, kind, None):
            return kind
    return None


def display_name(u: Any) -> str:
    if u is None:
        return "—"
    name = " ".join(x for x in (getattr(u, "first_name", None), getattr(u, "last_name", None)) if x)
    return name or (("@" + u.username) if getattr(u, "username", None) else str(u.id))


class Pipeline:
    def __init__(self, app: "AppContext") -> None:
        self.app = app
        self._offhours_sent: dict[tuple[int, int], float] = {}
        self._owner_names: dict[int, str] = {}

    async def owner_name(self, conn: Conn) -> str:
        if conn.user_id not in self._owner_names:
            u = await self.app.users.get(conn.user_id)
            self._owner_names[conn.user_id] = (u or {}).get("first_name") or "Владелец"
        return self._owner_names[conn.user_id]

    def forget_owner_name(self, user_id: int) -> None:
        self._owner_names.pop(user_id, None)

    # ===================================================================================
    async def on_message(self, conn: Conn, message: Message) -> str:
        """Entry point for business_message updates. Returns a short outcome label (used in tests/logs)."""
        app = self.app
        if await app.dedup.seen(f"bm:{conn.id}:{message.chat.id}:{message.message_id}"):
            return "duplicate"
        if message.sender_business_bot is not None:
            return "own_bot_echo"  # sent by a bot on behalf of the account → never react (loop protection)
        if not conn.is_enabled:
            return "connection_disabled"
        sender = message.from_user
        if sender is not None and sender.id == conn.user_id:
            return await self.on_owner_message(conn, message)
        return await self.on_incoming(conn, message)

    # ---- owner (outgoing) ------------------------------------------------------------
    async def on_owner_message(self, conn: Conn, message: Message) -> str:
        app = self.app
        user_id = conn.user_id
        settings = await app.settings.all(user_id)
        await app.connections.touch(conn.id, incoming=False)
        await app.metrics.incr("messages_out", user_id)
        if await app.executor.try_handle(message, user_id=user_id, source="business", conn=conn, settings=settings):
            return "command"
        chat = message.chat
        await app.chats.touch(user_id, chat.id, title=display_name(chat), username=chat.username, incoming=False)
        await self.store_message(user_id, chat.id, message, outgoing=True, settings=settings)
        if settings.get("owner_pause_minutes", 15) > 0:
            await app.chats.set_owner_pause(user_id, chat.id, settings["owner_pause_minutes"])
        app.loop_guard.reset(user_id, chat.id)
        if app.ai_auto is not None:
            app.ai_auto.cancel_pending(user_id, chat.id)
        if app.games is not None and await app.games.on_chat_message(conn, message):
            return "game_move"
        if settings.get("afk_auto_off", True) and await app.afk.active(user_id):
            await app.afk.disable(user_id, reason="activity")
            return "afk_auto_off"
        return "owner_activity"

    # ---- counterpart (incoming) ----------------------------------------------------
    async def on_incoming(self, conn: Conn, message: Message) -> str:
        app = self.app
        user_id = conn.user_id
        if await app.users.is_restricted(user_id):
            return "owner_restricted"
        # v3 filters first (🔕 mute / 🚫 nogif / 🧹 words): a deleted message gets no further processing
        if not app.runtime.emergency_stop and app.filters is not None:
            deleted = await app.filters.handle_incoming(conn, message)
            if deleted:
                return f"filtered:{deleted}"
        settings = await app.settings.all(user_id)
        sender = message.from_user
        chat = message.chat
        text = message.text or message.caption or ""
        mtype = media_type(message)
        is_bot = bool(sender and sender.is_bot)
        preview = clip(text or f"[{mtype or 'message'}]", 160) if settings.get("store_previews", True) else None
        chat_row, is_new = await app.chats.touch(user_id, chat.id, title=display_name(sender or chat),
                                                 username=(sender.username if sender else None), is_bot=is_bot,
                                                 incoming=True, preview=preview)
        await app.connections.touch(conn.id, incoming=True)
        await app.metrics.incr("messages_in", user_id)
        await self.store_message(user_id, chat.id, message, outgoing=False, settings=settings)
        app.loop_guard.note_incoming(user_id, chat.id, text)
        app.events.emit("message_in", user_id=user_id, chat_id=chat.id, media=mtype, new_chat=is_new)

        if app.games is not None and await app.games.on_chat_message(conn, message):
            return "game_move"
        try:
            await app.inbox.on_incoming(user_id, chat_row, text, settings, is_new)
        except Exception:  # pragma: no cover - never block replies on inbox errors
            log.exception("inbox failed")
        if app.automation is not None:
            try:
                await app.automation.on_message(conn, message, settings, chat_row, is_new, mtype)
            except Exception:
                log.exception("automation failed")
        if settings.get("ai_auto_transcribe") and mtype in ("voice", "video_note") and app.ai_auto is not None:
            app.ai_auto.transcribe_for_owner(conn, message, settings)
        return await self.auto_reply(conn, message, settings, chat_row, is_new, mtype, text, is_bot)

    async def store_message(self, owner: int, chat_id: int, message: Message, *, outgoing: bool, settings: dict[str, Any]) -> None:
        """Keep a short, owner-scoped history for .sum and AI context (retention: history_retention_days)."""
        if not settings.get("ai_store_history", True) or int(settings.get("history_retention_days", 7)) <= 0:
            return
        text = message.text or message.caption
        try:
            await self.app.db.execute(
                "INSERT INTO chat_messages(owner_id, chat_id, message_id, outgoing, msg_type, text, created_at) VALUES (?,?,?,?,?,?,?)",
                (owner, chat_id, message.message_id, 1 if outgoing else 0, media_type(message) or ("text" if text else None),
                 clip(text, 2000) if text else None, int(time.time())))
        except Exception:  # pragma: no cover - history is best-effort
            log.exception("failed to store chat message")

    def gate(self, conn: Conn, settings: dict[str, Any], chat_row: dict[str, Any], is_bot: bool,
             check_limits: bool = True) -> str | None:
        """Returns a reason string if automated sending is NOT allowed, else None."""
        app = self.app
        now = time.time()
        if app.runtime.emergency_stop:
            return "emergency_stop"
        if app.runtime.is_module_paused("autoreply"):
            return "module_paused"
        if not conn.active:
            return "connection_inactive"
        if not conn.can("can_reply"):
            return "no_reply_right"
        if settings.get("automation_paused"):
            return "paused"
        if settings["mode"] == "silent":
            return "silent"
        if chat_row.get("ignored"):
            return "ignored"
        if settings.get("autoreply_scope") == "whitelist" and not chat_row.get("whitelisted"):
            return "not_whitelisted"
        if (chat_row.get("muted_until") or 0) > now:
            return "muted"
        if (chat_row.get("owner_paused_until") or 0) > now:
            return "owner_active"
        if is_bot:
            return "counterpart_is_bot"
        if check_limits:
            ok, why = app.loop_guard.allow(conn.user_id, chat_row["chat_id"], is_bot)
            if not ok:
                return why
        return None

    async def daily_limit_reached(self, user_id: int, chat_row: dict[str, Any], settings: dict[str, Any]) -> bool:
        limit = chat_row.get("reply_limit") or settings.get("max_auto_replies_per_chat_day", 20)
        return await self.app.chats.auto_replies_today(user_id, chat_row["chat_id"]) >= limit

    async def send_auto(self, conn: Conn, chat_id: int, text: str, reply_to: int | None, kind: str) -> bool:
        app = self.app
        res = await app.sender.send_text(chat_id, text, bc_id=conn.id, reply_to=reply_to)
        if res.ok:
            app.loop_guard.record_reply(conn.user_id, chat_id)
            await app.chats.count_auto_reply(conn.user_id, chat_id)
            await app.metrics.incr("auto_replies", conn.user_id)
            await app.metrics.incr(f"auto:{kind}", conn.user_id)
            app.events.emit("auto_reply", user_id=conn.user_id, chat_id=chat_id, kind=kind)
            return True
        app.events.emit("auto_reply_failed", user_id=conn.user_id, chat_id=chat_id, kind=kind, reason=res.kind, level="warning")
        if res.kind == "connection_invalid":
            await app.connections.mark_status(conn.id, "reconnection_required")
        return False

    async def auto_reply(self, conn: Conn, message: Message, settings: dict[str, Any], chat_row: dict[str, Any],
                         is_new: bool, mtype: str | None, text: str, is_bot: bool) -> str:
        app = self.app
        user_id, chat_id = conn.user_id, message.chat.id
        mode = settings["mode"]
        afk_active = await app.afk.active(user_id)
        if mode == "manual" and not afk_active:
            return "manual_mode"
        why = self.gate(conn, settings, chat_row, is_bot)
        if why:
            if afk_active:
                await app.afk.record_incoming(user_id, chat_id, replied=False)
            return f"blocked:{why}"
        if await self.daily_limit_reached(user_id, chat_row, settings):
            return "blocked:daily_limit"
        lang = chat_row.get("language") or settings["lang"]
        owner = await self.owner_name(conn)
        counterpart = display_name(message.from_user)
        tz_name = settings.get("timezone") or app.config.timezone

        # 1. hand-off to a human
        low = text.lower()
        if mode != "afk" and any(k.lower() in low for k in settings.get("handoff_keywords") or [] if k):
            await app.chats.set_owner_pause(user_id, chat_id, 60)
            await self.send_auto(conn, chat_id, tr(lang, "🙋 Передаю ваш вопрос владельцу — {o} ответит лично.",
                                                   "🙋 Savolingizni egasiga yetkazaman — {o} shaxsan javob beradi.", o=esc(owner)),
                                 message.message_id, "handoff")
            await app.notifications.notify(user_id, "handoff", tr(settings["lang"], "Собеседник просит ответить лично", "Suhbatdosh shaxsan javob so'ramoqda"),
                                           f"{counterpart}: {clip(text, 200)}", level="warning", push=True)
            return "handoff"

        # 2. AFK
        if afk_active or mode == "afk":
            replied = False
            if chat_row.get("afk_enabled") != 0 and app.afk.cooldown_ok(user_id, chat_id, settings["afk_cooldown_min"]):
                reply_text = None
                if settings.get("afk_ai") and app.ai_auto is not None and app.ai.available():
                    reply_text = await app.ai_auto.afk_reply(conn, message, settings, chat_row, afk_active)
                if not reply_text:
                    reply_text = await app.afk.build_reply(user_id, chat_id, settings, owner, chat_row.get("language"))
                replied = await self.send_auto(conn, chat_id, reply_text, message.message_id, "afk")
                if replied:
                    app.afk.mark_replied(user_id, chat_id)
            await app.afk.record_incoming(user_id, chat_id, replied)
            return "afk_reply" if replied else "afk_skip"

        # 3. welcome
        if is_new and settings.get("welcome_enabled") and settings.get("welcome_text") and mode in ("auto", "business", "hybrid", "ai"):
            await self.send_auto(conn, chat_id, fill(esc(settings["welcome_text"]), name=esc(counterpart), owner=esc(owner),
                                                     tz_name=tz_name), message.message_id, "welcome")
            if mode != "ai":
                return "welcome"

        # 4. rules
        if mode in ("auto", "business", "hybrid") and chat_row.get("autoreply_enabled") != 0:
            rule = await app.autoreply.match(user_id, chat_id, text, is_new_chat=is_new, media_type=mtype, settings=settings,
                                             chat_tags=chat_row.get("tags") or [], include_offhours=mode == "business")
            if rule:
                sent = await self.send_auto(conn, chat_id, fill(esc(rule["response"]), name=esc(counterpart), owner=esc(owner),
                                                                tz_name=tz_name), message.message_id, "rule")
                return "rule_reply" if sent else "rule_failed"

        # 5. business hours
        if mode == "business" and not app.autoreply.is_work_time(settings):
            key = (user_id, chat_id)
            if time.time() - self._offhours_sent.get(key, 0) > 3 * 3600:
                self._offhours_sent[key] = time.time()
                custom = settings.get("offhours_text")
                txt = esc(custom) if custom else tr(
                    lang, "🕘 Сейчас нерабочее время ({a}–{b}). {o} ответит в рабочие часы.",
                    "🕘 Hozir ish vaqti emas ({a}–{b}). {o} ish vaqtida javob beradi.",
                    a=settings["work_start"], b=settings["work_end"], o=esc(owner))
                sent = await self.send_auto(conn, chat_id, fill(txt, name=esc(counterpart), owner=esc(owner), tz_name=tz_name),
                                            message.message_id, "offhours")
                return "offhours" if sent else "offhours_failed"
            return "offhours_cooldown"

        # 6. AI
        if mode in ("ai", "hybrid") and chat_row.get("ai_enabled") != 0:
            if app.ai_auto is None or not app.ai.available():
                return "ai_unavailable"
            app.ai_auto.schedule(conn, message, settings, chat_row)
            return "ai_scheduled"
        return "no_action"

    # ---- edits / deletes -------------------------------------------------------------
    async def on_edited(self, conn: Conn, message: Message) -> str:
        app = self.app
        sender = message.from_user
        if message.sender_business_bot is not None:
            return "own_bot_echo"
        if sender is not None and sender.id == conn.user_id:
            # re-run a command if the owner edited a plain message into a command (typo fix)
            key = f"edit_cmd:{conn.id}:{message.chat.id}:{message.message_id}"
            settings = await app.settings.all(conn.user_id)
            from ..commands.parser import parse
            if parse(message.text or "", settings["prefix"]) and not await app.dedup.seen(key):
                await app.executor.try_handle(message, user_id=conn.user_id, source="business", conn=conn, settings=settings)
                return "edited_command"
        app.events.emit("message_edited", user_id=conn.user_id, chat_id=message.chat.id)
        await app.metrics.incr("messages_edited", conn.user_id)
        return "edited"

    async def on_deleted(self, conn: Conn, chat_id: int, message_ids: list[int]) -> str:
        self.app.events.emit("messages_deleted", user_id=conn.user_id, chat_id=chat_id, count=len(message_ids))
        await self.app.metrics.incr("messages_deleted", conn.user_id, len(message_ids))
        return "deleted"

    @staticmethod
    def part_of_day(tz_name: str) -> str:
        return day_part(tz_name)
