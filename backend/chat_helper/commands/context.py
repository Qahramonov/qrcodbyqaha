"""CommandContext: everything a handler needs + response helpers that respect Telegram limits."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from aiogram.types import InlineKeyboardMarkup, Message

from ..business import sender as S
from ..localization import p, tr
from .parser import ParsedCommand
from .registry import CommandSpec

if TYPE_CHECKING:  # pragma: no cover
    from ..business.connections import Conn
    from ..core.context import AppContext

log = logging.getLogger(__name__)


class CommandError(Exception):
    """User-facing error: message is shown as-is."""


class UsageError(CommandError):
    """Wrong arguments: syntax help is shown."""

    def __init__(self, hint: str = "") -> None:
        super().__init__(hint)


class CommandContext:
    def __init__(self, app: "AppContext", spec: CommandSpec, parsed: ParsedCommand, *, user_id: int,
                 source: str, message: Message | None, conn: "Conn | None", chat_id: int,
                 settings: dict[str, Any], role: str = "user", plan: str = "free") -> None:
        self.app = app
        self.spec = spec
        self.parsed = parsed
        self.user_id = user_id
        self.source = source              # business | private | sandbox
        self.message = message
        self.conn = conn
        self.chat_id = chat_id
        self.settings = settings
        self.lang = settings.get("lang", "ru")
        self.role = role
        self.plan = plan
        self.outputs: list[dict[str, Any]] = []   # sandbox capture
        self.result_message_id: int | None = None
        self._edited_in_place = False
        self.command_deleted = False

    # ---- convenience --------------------------------------------------------------
    @property
    def args(self) -> list[str]:
        return self.parsed.args

    @property
    def raw(self) -> str:
        return self.parsed.raw_args

    @property
    def prefix(self) -> str:
        return self.settings.get("prefix", ".")

    @property
    def reply(self) -> Message | None:
        return self.message.reply_to_message if self.message is not None else None

    @property
    def bc_id(self) -> str | None:
        return self.conn.id if (self.source == "business" and self.conn) else None

    @property
    def is_business(self) -> bool:
        return self.source == "business"

    @property
    def is_admin(self) -> bool:
        return self.role == "super_admin"

    @property
    def is_super(self) -> bool:
        return self.role == "super_admin"

    def t(self, ru: str, uz: str, **kw: Any) -> str:
        return tr(self.lang, ru, uz, **kw)

    def usage(self) -> str:
        return p(self.lang, "usage", syntax=self.spec.syntax.replace(".", self.prefix, 1))

    def reply_text(self) -> str:
        r = self.reply
        if r is None:
            return ""
        return r.text or r.caption or ""

    def text_arg_or_reply(self) -> str:
        return self.raw or self.reply_text()

    # ---- responses ---------------------------------------------------------------
    async def answer(self, text: str, *, markup: InlineKeyboardMarkup | None = None, private: bool = False,
                     parse_mode: str | None = "HTML", in_place: bool = True) -> int | None:
        if self.source == "sandbox":
            self.outputs.append({"type": "text", "text": text})
            return None
        sender = self.app.sender
        if private or self.source == "private":
            res = await sender.send_text(self.user_id, text, markup=markup, parse_mode=parse_mode,
                                         reply_to=self.message.message_id if (self.message and self.source == "private") else None)
            self.result_message_id = res.message_id
            if private and self.is_business and in_place:
                await self.cleanup_command(fallback_text="🔒")
            return res.message_id
        # business chat: prefer editing the owner's command message in place
        if in_place and self.message is not None and not self._edited_in_place:
            res = await sender.edit_text(self.chat_id, self.message.message_id, text, bc_id=self.bc_id,
                                         markup=markup, parse_mode=parse_mode)
            if res.ok:
                self._edited_in_place = True
                self.result_message_id = self.message.message_id
                return self.message.message_id
        res = await sender.send_text(self.chat_id, text, bc_id=self.bc_id, markup=markup, parse_mode=parse_mode,
                                     reply_to=self.message.message_id if self.message else None)
        if res.ok:
            self.result_message_id = res.message_id
            return res.message_id
        await self._fallback_private(text, res)
        return None

    async def _fallback_private(self, text: str, res: S.SendResult) -> None:
        reason = {
            S.WINDOW: self.t("Telegram разрешает боту писать в чат только если собеседник писал за последние 24 часа.",
                             "Telegram botga faqat suhbatdosh so'nggi 24 soatda yozgan chatga yozishga ruxsat beradi."),
            S.RIGHTS: self.t("Боту не хватает бизнес-прав (нужно «Отвечать на сообщения»).",
                             "Botda biznes huquqlari yetarli emas («Xabarlarga javob berish» kerak)."),
            S.CONNECTION: self.t("Бизнес-подключение недействительно — переподключите бота.",
                                 "Biznes ulanish yaroqsiz — botni qayta ulang."),
        }.get(res.kind, self.t("Не удалось отправить в чат.", "Chatga yuborib bo'lmadi."))
        await self.app.sender.send_text(self.user_id, f"{text}\n\n<i>ℹ️ {reason}</i>", parse_mode="HTML")

    async def answer_private(self, text: str, markup: InlineKeyboardMarkup | None = None) -> int | None:
        return await self.answer(text, markup=markup, private=True)

    async def status(self, text: str) -> None:
        """Interim status in place (e.g. '⏳ processing'). Silent on failure."""
        if self.source == "sandbox" or self.message is None:
            return
        if self.is_business:
            res = await self.app.sender.edit_text(self.chat_id, self.message.message_id, text, bc_id=self.bc_id)
            if res.ok:
                self._edited_in_place = True
        else:
            await self.app.sender.action(self.chat_id, "typing")

    async def typing(self, action: str = "typing") -> None:
        if self.source == "sandbox":
            return
        await self.app.sender.action(self.chat_id, action, bc_id=self.bc_id)

    async def send_media(self, kind: str, media: Any, *, caption: str | None = None, reply_to: int | None = None,
                         markup: InlineKeyboardMarkup | None = None, private: bool = False, **extra: Any) -> S.SendResult:
        if self.source == "sandbox":
            self.outputs.append({"type": kind, "caption": caption or ""})
            return S.SendResult(True)
        if private or self.source == "private":
            return await self.app.sender.send_media(self.user_id, kind, media, caption=caption, markup=markup,
                                                    reply_to=reply_to if self.source == "private" else None, **extra)
        res = await self.app.sender.send_media(self.chat_id, kind, media, bc_id=self.bc_id, caption=caption,
                                               reply_to=reply_to, markup=markup, **extra)
        if not res.ok and res.kind in (S.WINDOW, S.RIGHTS, S.CONNECTION):
            await self._fallback_private(self.t("🎞 Результат отправлен сюда.", "🎞 Natija shu yerga yuborildi."), res)
            return await self.app.sender.send_media(self.user_id, kind, media, caption=caption, **extra)
        return res

    async def cleanup_command(self, fallback_text: str | None = None) -> None:
        """Remove the owner's command message from the business chat when possible."""
        if not self.is_business or self.message is None or self.command_deleted:
            return
        can_delete = bool(self.conn and self.conn.can("can_delete_all_messages"))
        if can_delete and self.settings.get("delete_commands", True):
            res = await self.app.sender.delete(self.chat_id, [self.message.message_id], bc_id=self.bc_id)
            if res.ok:
                self.command_deleted = True
                return
        if fallback_text and not self._edited_in_place:
            await self.app.sender.edit_text(self.chat_id, self.message.message_id, fallback_text, bc_id=self.bc_id)

    async def require_ai(self) -> None:
        if not self.app.ai.available():
            raise CommandError(p(self.lang, "requires_ai"))
