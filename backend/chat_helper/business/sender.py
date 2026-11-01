"""Sending/editing/deleting on behalf of a business account with error classification,
flood control, retries and fallbacks. Only official Bot API methods are used."""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any

from aiogram import Bot
from aiogram.exceptions import (TelegramBadRequest, TelegramForbiddenError, TelegramNetworkError,
                                TelegramRetryAfter, TelegramServerError)
from aiogram.types import InlineKeyboardMarkup, LinkPreviewOptions, ReplyParameters

log = logging.getLogger(__name__)

# error kinds
OK = "ok"
WINDOW = "window_24h"           # chat had no incoming message in last 24h / peer not usable
RIGHTS = "missing_rights"
CONNECTION = "connection_invalid"
NOT_MODIFIED = "not_modified"
NOT_FOUND = "not_found"
TOO_OLD = "too_old"
FORBIDDEN = "forbidden"
NETWORK = "network"
BAD_REQUEST = "bad_request"


def classify(exc: Exception) -> str:
    text = str(exc).upper()
    if isinstance(exc, TelegramForbiddenError):
        return FORBIDDEN
    if isinstance(exc, (TelegramNetworkError, TelegramServerError)):
        return NETWORK
    if "NOT MODIFIED" in text:
        return NOT_MODIFIED
    if "PEER_USAGE_MISSING" in text or "BUSINESS_PEER" in text or "24" in text and "HOUR" in text:
        return WINDOW
    if "BUSINESS_CONNECTION" in text or "BOT_BUSINESS_MISSING" in text:
        return CONNECTION
    if "RIGHT" in text or "NOT ENOUGH" in text or "CHAT_WRITE_FORBIDDEN" in text or "NOT ALLOWED" in text:
        return RIGHTS
    if "MESSAGE TO EDIT NOT FOUND" in text or "MESSAGE_ID_INVALID" in text or "NOT FOUND" in text:
        return NOT_FOUND
    if "CAN'T BE EDITED" in text or "CANT BE EDITED" in text or "TOO OLD" in text or "48" in text:
        return TOO_OLD
    return BAD_REQUEST


@dataclass
class SendResult:
    ok: bool
    message: Any = None
    kind: str = OK
    error: str = ""

    @property
    def message_id(self) -> int | None:
        return getattr(self.message, "message_id", None)


class FloodControl:
    """~1 msg/s per chat, ~25 msg/s globally (Telegram recommendations)."""

    def __init__(self, per_chat_interval: float = 1.0, global_rate: int = 25) -> None:
        self.per_chat_interval = per_chat_interval
        self.global_interval = 1.0 / global_rate
        self._chat_last: dict[int, float] = {}
        self._chat_locks: dict[int, asyncio.Lock] = {}
        self._global_last = 0.0
        self._global_lock = asyncio.Lock()

    async def wait(self, chat_id: int) -> None:
        lock = self._chat_locks.setdefault(chat_id, asyncio.Lock())
        async with lock:
            delay = self._chat_last.get(chat_id, 0) + self.per_chat_interval - time.monotonic()
            if delay > 0:
                await asyncio.sleep(delay)
            self._chat_last[chat_id] = time.monotonic()
        async with self._global_lock:
            delay = self._global_last + self.global_interval - time.monotonic()
            if delay > 0:
                await asyncio.sleep(delay)
            self._global_last = time.monotonic()
        if len(self._chat_last) > 5000:
            cutoff = time.monotonic() - 60
            for k in [k for k, v in self._chat_last.items() if v < cutoff]:
                self._chat_last.pop(k, None)
                self._chat_locks.pop(k, None)


class BusinessSender:
    def __init__(self, bot: Bot, events: Any = None, metrics: Any = None) -> None:
        self.bot = bot
        self.events = events
        self.metrics = metrics
        self.flood = FloodControl()
        self.sent_ok = 0
        self.sent_failed = 0
        # v3 Protect: async (bc_id, chat_id) -> bool, set by the app; every business send consults it
        self.protect_resolver: Any = None

    async def _protect(self, protect: bool | None, bc_id: str | None, chat_id: int) -> bool | None:
        if protect is not None:
            return protect
        if bc_id and self.protect_resolver is not None:
            try:
                return bool(await self.protect_resolver(bc_id, chat_id)) or None
            except Exception:  # pragma: no cover - never block a send on the resolver
                log.exception("protect resolver failed")
        return None

    async def _call(self, chat_id: int, coro_factory, *, retries: int = 2, flood: bool = True) -> SendResult:
        attempt = 0
        while True:
            attempt += 1
            try:
                if flood:
                    await self.flood.wait(chat_id)
                res = await coro_factory()
                self.sent_ok += 1
                return SendResult(True, res)
            except TelegramRetryAfter as e:
                if attempt > retries or e.retry_after > 60:
                    self.sent_failed += 1
                    return SendResult(False, kind=NETWORK, error=f"flood wait {e.retry_after}s")
                await asyncio.sleep(e.retry_after + 0.5)
            except (TelegramNetworkError, TelegramServerError) as e:
                if attempt > retries:
                    self.sent_failed += 1
                    return SendResult(False, kind=NETWORK, error=str(e)[:300])
                await asyncio.sleep(2 ** attempt)
            except (TelegramBadRequest, TelegramForbiddenError) as e:
                kind = classify(e)
                if kind != NOT_MODIFIED:
                    self.sent_failed += 1
                    log.info("telegram call failed (%s): %s", kind, str(e)[:200])
                return SendResult(kind == NOT_MODIFIED, kind=kind, error=str(e)[:300])

    # ---- text --------------------------------------------------------------------------
    async def send_text(self, chat_id: int, text: str, *, bc_id: str | None = None, reply_to: int | None = None,
                        markup: InlineKeyboardMarkup | None = None, parse_mode: str | None = "HTML",
                        preview: bool = False, protect: bool | None = None) -> SendResult:
        text = text[:4096]
        rp = ReplyParameters(message_id=reply_to, allow_sending_without_reply=True) if reply_to else None
        pc = await self._protect(protect, bc_id, chat_id)
        return await self._call(chat_id, lambda: self.bot.send_message(
            chat_id=chat_id, text=text, business_connection_id=bc_id, reply_parameters=rp, reply_markup=markup,
            parse_mode=parse_mode, link_preview_options=LinkPreviewOptions(is_disabled=not preview), protect_content=pc))

    async def edit_text(self, chat_id: int, message_id: int, text: str, *, bc_id: str | None = None,
                        markup: InlineKeyboardMarkup | None = None, parse_mode: str | None = "HTML", retries: int = 2) -> SendResult:
        """``retries=0`` for animations: a rate-limited edit is reported at once instead of sleeping on FloodWait."""
        return await self._call(chat_id, lambda: self.bot.edit_message_text(
            text=text[:4096], chat_id=chat_id, message_id=message_id, business_connection_id=bc_id,
            reply_markup=markup, parse_mode=parse_mode, link_preview_options=LinkPreviewOptions(is_disabled=True)),
            flood=False, retries=retries)

    async def edit_markup(self, chat_id: int, message_id: int, markup: InlineKeyboardMarkup | None, *,
                          bc_id: str | None = None) -> SendResult:
        return await self._call(chat_id, lambda: self.bot.edit_message_reply_markup(
            chat_id=chat_id, message_id=message_id, business_connection_id=bc_id, reply_markup=markup), flood=False)

    async def edit_caption(self, chat_id: int, message_id: int, caption: str, *, bc_id: str | None = None) -> SendResult:
        return await self._call(chat_id, lambda: self.bot.edit_message_caption(
            chat_id=chat_id, message_id=message_id, business_connection_id=bc_id, caption=caption[:1024],
            parse_mode=None), flood=False)

    async def delete(self, chat_id: int, message_ids: list[int], *, bc_id: str | None = None) -> SendResult:
        if not message_ids:
            return SendResult(True)
        if bc_id:
            return await self._call(chat_id, lambda: self.bot.delete_business_messages(
                business_connection_id=bc_id, message_ids=message_ids[:100]), flood=False)
        return await self._call(chat_id, lambda: self.bot.delete_messages(chat_id=chat_id, message_ids=message_ids[:100]),
                                flood=False)

    async def action(self, chat_id: int, action: str = "typing", *, bc_id: str | None = None) -> SendResult:
        return await self._call(chat_id, lambda: self.bot.send_chat_action(
            chat_id=chat_id, action=action, business_connection_id=bc_id), retries=0, flood=False)

    async def read(self, chat_id: int, message_id: int, bc_id: str) -> SendResult:
        return await self._call(chat_id, lambda: self.bot.read_business_message(
            business_connection_id=bc_id, chat_id=chat_id, message_id=message_id), retries=0, flood=False)

    # ---- media ---------------------------------------------------------------------------
    async def send_media(self, chat_id: int, kind: str, media: Any, *, bc_id: str | None = None,
                         caption: str | None = None, reply_to: int | None = None,
                         markup: InlineKeyboardMarkup | None = None, protect: bool | None = None, **extra: Any) -> SendResult:
        rp = ReplyParameters(message_id=reply_to, allow_sending_without_reply=True) if reply_to else None
        common: dict[str, Any] = dict(chat_id=chat_id, business_connection_id=bc_id, reply_parameters=rp,
                                      reply_markup=markup, protect_content=await self._protect(protect, bc_id, chat_id))
        cap = {"caption": caption[:1024], "parse_mode": "HTML"} if caption else {}
        b = self.bot
        factories = {
            "photo": lambda: b.send_photo(photo=media, **cap, **common),
            "voice": lambda: b.send_voice(voice=media, **cap, **common, **extra),
            "audio": lambda: b.send_audio(audio=media, **cap, **common, **extra),
            "video": lambda: b.send_video(video=media, **cap, **common, supports_streaming=True, **extra),
            "video_note": lambda: b.send_video_note(video_note=media, **common, **extra),
            "animation": lambda: b.send_animation(animation=media, **cap, **common, **extra),
            "document": lambda: b.send_document(document=media, **cap, **common),
            "sticker": lambda: b.send_sticker(sticker=media, **common),
        }
        if kind not in factories:
            return SendResult(False, kind=BAD_REQUEST, error=f"unsupported media kind {kind}")
        return await self._call(chat_id, factories[kind], retries=1)

    async def send_location(self, chat_id: int, lat: float, lon: float, *, bc_id: str | None = None) -> SendResult:
        return await self._call(chat_id, lambda: self.bot.send_location(chat_id=chat_id, latitude=lat, longitude=lon,
                                                                        business_connection_id=bc_id))

    async def send_dice(self, chat_id: int, emoji: str = "🎲", *, bc_id: str | None = None,
                        reply_to: int | None = None) -> SendResult:
        rp = ReplyParameters(message_id=reply_to, allow_sending_without_reply=True) if reply_to else None
        return await self._call(chat_id, lambda: self.bot.send_dice(chat_id=chat_id, emoji=emoji,
                                                                    business_connection_id=bc_id, reply_parameters=rp))
