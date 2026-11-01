"""A fake Telegram Bot API session for tests: records every request and returns typed results.
The real aiogram Dispatcher, filters, routers and middlewares are exercised end-to-end."""
from __future__ import annotations

import datetime as dt
import itertools
from typing import Any, AsyncGenerator

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.base import BaseSession
from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import TelegramMethod
from aiogram.types import (BusinessBotRights, BusinessConnection, Chat, ChatFullInfo, Dice, File, InlineKeyboardMarkup, Message,
                           Update, User, Voice)

BOT_ID = 777000111
TOKEN = f"{BOT_ID}:AAAbbbCCCdddEEEfffGGGhhhIIIjjjKKKlll"
_ids = itertools.count(5000)
_upd = itertools.count(1)

SEND_METHODS = {"SendMessage", "SendPhoto", "SendVoice", "SendVideo", "SendVideoNote", "SendAudio", "SendAnimation", "SendDocument",
                "SendSticker", "SendDice", "SendInvoice"}


class FakeSession(BaseSession):
    def __init__(self) -> None:
        super().__init__()
        self.requests: list[TelegramMethod] = []
        self.fail: dict[str, Exception] = {}
        self.files: dict[str, bytes] = {}
        self.connections: dict[str, BusinessConnection] = {}
        self.dice_value = 64
        self.drop_markup = False   # simulate a server that silently drops inline keyboards on edits

    def calls(self, name: str) -> list[TelegramMethod]:
        return [r for r in self.requests if type(r).__name__ == name]

    def sent_texts(self) -> list[str]:
        return [r.text for r in self.requests if type(r).__name__ in ("SendMessage", "EditMessageText") and r.text]

    def clear(self) -> None:
        self.requests.clear()

    async def make_request(self, bot: Bot, method: TelegramMethod, timeout: int | None = None) -> Any:
        self.requests.append(method)
        name = type(method).__name__
        if name in self.fail:
            exc = self.fail[name]
            if getattr(exc, "_once", False):
                self.fail.pop(name)
            raise exc
        now = dt.datetime.now(dt.timezone.utc)
        if name in SEND_METHODS or name in ("EditMessageText", "EditMessageCaption", "EditMessageReplyMarkup"):
            chat_id = int(getattr(method, "chat_id", 0) or 0)
            mid = next(_ids) if name in SEND_METHODS else getattr(method, "message_id", next(_ids))
            kw: dict[str, Any] = {}
            if name == "SendDice":
                kw["dice"] = Dice(emoji=method.emoji or "🎲", value=self.dice_value)
            text = getattr(method, "text", None)
            markup = getattr(method, "reply_markup", None)
            if isinstance(markup, InlineKeyboardMarkup) and not self.drop_markup:
                kw["reply_markup"] = markup
            return Message(message_id=mid, date=now, chat=Chat(id=chat_id, type="private"), text=text,
                           business_connection_id=getattr(method, "business_connection_id", None),
                           from_user=User(id=BOT_ID, is_bot=True, first_name="Chat helper"), **kw)
        if name == "GetMe":
            return User(id=BOT_ID, is_bot=True, first_name="Chat helper", username="ChatHelperTestBot", can_connect_to_business=True)
        if name == "GetBusinessConnection":
            bc = self.connections.get(method.business_connection_id)
            if bc is None:
                raise TelegramBadRequest(method=method, message="Bad Request: BUSINESS_CONNECTION_INVALID")
            return bc
        if name == "GetChat":
            return ChatFullInfo(id=int(method.chat_id), type="private", first_name="Owner", last_name="Test", bio="old bio",
                                accent_color_id=0, max_reaction_count=11, accepted_gift_types={"unlimited_gifts": True, "limited_gifts": True,
                                                                                              "unique_gifts": True, "premium_subscription": True,
                                                                                              "gifts_from_channels": True})
        if name == "GetFile":
            return File(file_id=method.file_id, file_unique_id=method.file_id + "_u", file_path=f"files/{method.file_id}")
        if name == "GetUpdates":
            return []
        return True

    async def stream_content(self, url: str, headers: dict[str, Any] | None = None, timeout: int = 30, chunk_size: int = 65536,
                             raise_for_status: bool = True) -> AsyncGenerator[bytes, None]:
        file_id = url.rsplit("/", 1)[-1]
        yield self.files.get(file_id, b"")

    async def close(self) -> None:
        pass


def make_bot() -> tuple[Bot, FakeSession]:
    session = FakeSession()
    return Bot(TOKEN, session=session, default=DefaultBotProperties(parse_mode="HTML")), session


def rights(**overrides: bool) -> BusinessBotRights:
    base = dict(can_reply=True, can_read_messages=True, can_delete_sent_messages=True, can_delete_all_messages=True,
                can_edit_name=True, can_edit_bio=True, can_edit_profile_photo=True)
    base.update(overrides)
    return BusinessBotRights(**base)


def business_connection(conn_id: str, owner_id: int, enabled: bool = True, **rights_kw: bool) -> BusinessConnection:
    return BusinessConnection(id=conn_id, user=User(id=owner_id, is_bot=False, first_name="Owner", username=f"owner{owner_id}",
                                                    language_code="ru"),
                              user_chat_id=owner_id, date=dt.datetime.now(dt.timezone.utc), is_enabled=enabled, rights=rights(**rights_kw))


def update_connection(bc: BusinessConnection) -> Update:
    return Update(update_id=next(_upd), business_connection=bc)


def biz_message(conn_id: str, chat_id: int, sender_id: int, text: str | None = None, *, sender_is_bot: bool = False,
                via_bot: bool = False, reply_to: Message | None = None, message_id: int | None = None, voice: Voice | None = None,
                first_name: str = "Alice", **extra: Any) -> Message:
    return Message(message_id=message_id or next(_ids), date=dt.datetime.now(dt.timezone.utc),
                   chat=Chat(id=chat_id, type="private", first_name=first_name if sender_id == chat_id else "Contact"),
                   from_user=User(id=sender_id, is_bot=sender_is_bot, first_name=first_name), text=text, voice=voice,
                   business_connection_id=conn_id, reply_to_message=reply_to,
                   sender_business_bot=User(id=BOT_ID, is_bot=True, first_name="Chat helper") if via_bot else None, **extra)


def update_business_message(msg: Message) -> Update:
    return Update(update_id=next(_upd), business_message=msg)


def private_message(user_id: int, text: str, first_name: str = "Owner") -> Update:
    return Update(update_id=next(_upd), message=Message(message_id=next(_ids), date=dt.datetime.now(dt.timezone.utc),
                                                        chat=Chat(id=user_id, type="private", first_name=first_name),
                                                        from_user=User(id=user_id, is_bot=False, first_name=first_name, language_code="ru"),
                                                        text=text))
