"""Shared infrastructure of the Telegram panel: screen registry, access gate, rendering helpers.

Access model (v3):
* **Super Admin** — only the numeric ``SUPER_ADMIN_ID`` from configuration (never a username or a request field).
* **Connected user** — has an *enabled* Telegram Business connection to Chat helper.
* **Not connected** — may only use onboarding: /start, /help, /connect, connection check, instructions, language,
  support (and /app to pair the Control app, which itself shows the connection wizard).

Every gate is enforced on the server side at each entry point: menu rendering (:func:`show`), callbacks and FSM
messages (:class:`PanelGate`), dot-commands (``CommandExecutor``) and the REST API (``api/deps.py``).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message, TelegramObject

from ..localization import tr

log = logging.getLogger(__name__)

ScreenFn = Callable[..., Awaitable[tuple[str, Any]]]


@dataclass
class ScreenDef:
    fn: ScreenFn
    public: bool = False       # allowed before a Business connection exists
    admin: bool = False        # super admin only


SCREENS: dict[str, ScreenDef] = {}


def screen(name: str, *, public: bool = False, admin: bool = False) -> Callable[[ScreenFn], ScreenFn]:
    def deco(fn: ScreenFn) -> ScreenFn:
        SCREENS[name] = ScreenDef(fn, public=public, admin=admin)
        return fn
    return deco


def register_screen(name: str, fn: ScreenFn, *, public: bool = False, admin: bool = False) -> None:
    SCREENS[name] = ScreenDef(fn, public=public, admin=admin)


@dataclass
class Access:
    uid: int
    is_super: bool
    connected: bool
    conn: Any = None

    @property
    def locked(self) -> bool:
        """Features are locked until the account is connected (the super admin keeps the system panel)."""
        return not self.connected and not self.is_super


async def access(app: Any, uid: int) -> Access:
    conn = None
    for c in await app.connections.for_user(uid):
        if c.is_enabled:
            conn = c
            break
    return Access(uid=uid, is_super=app.users.is_super_id(uid), connected=conn is not None, conn=conn)


async def ensure_user(app: Any, msg_or_cb: Message | CallbackQuery) -> int:
    u = msg_or_cb.from_user
    await app.users.upsert(u.id, u.username, u.first_name, u.last_name, u.language_code)
    return u.id


async def render(target: Message, text: str, markup: InlineKeyboardMarkup | None, edit: bool = True) -> None:
    """Edit the panel message in place when possible, otherwise send a new one."""
    if edit:
        try:
            await target.edit_text(text, reply_markup=markup, disable_web_page_preview=True)
            return
        except TelegramBadRequest as e:
            if "not modified" in str(e).lower():
                return
            # photo messages (onboarding infographic) cannot be edited into text → send a fresh message
    await target.answer(text, reply_markup=markup, disable_web_page_preview=True)


async def show(app: Any, uid: int, name: str, target: Message, edit: bool, *args: Any) -> None:
    s = await app.settings.all(uid)
    acc = await access(app, uid)
    sd = SCREENS.get(name)
    if sd is None or (sd.admin and not acc.is_super):
        name, sd = "home", SCREENS["home"]
        args = ()
    if not sd.public and acc.locked:
        name, sd = "locked", SCREENS["locked"]
        args = ()
    text, markup = await sd.fn(app, uid, s, *args)
    await render(target, text, markup, edit)


# ------------------------------------------------------------------------------------------------------------
# Gate middleware for callbacks and FSM messages of the panel routers
# ------------------------------------------------------------------------------------------------------------
PUBLIC_CALLBACKS = ("noop", "ob:", "help:", "app:", "lang:", "st:lang:")
PUBLIC_SCREENS = ("m:home", "m:connect", "m:help", "m:features", "m:lang", "m:locked", "m:app")
ADMIN_CALLBACKS = ("adm:", "bc:", "ax:")
PUBLIC_COMMANDS = ("/start", "/help", "/connect", "/menu", "/cancel", "/app", "/lang", "/support")
PUBLIC_STATES = ("PS:support",)
ADMIN_STATES = ("PS:broadcast_text", "AX:")


def _is_public_callback(data: str) -> bool:
    if data.startswith("m:"):
        return any(data == s or data.startswith(s + ":") for s in PUBLIC_SCREENS) or data.split(":")[1] in (
            sname for sname, sd in SCREENS.items() if sd.public)
    return data.startswith(PUBLIC_CALLBACKS)


class PanelGate(BaseMiddleware):
    """Blocks admin actions for everyone except the super admin and feature actions before connection."""

    async def __call__(self, handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]], event: TelegramObject,
                      data: dict[str, Any]) -> Any:
        app = data.get("app")
        if app is None:
            return await handler(event, data)
        if isinstance(event, CallbackQuery) and event.from_user is not None:
            cb_data = event.data or ""
            uid = event.from_user.id
            if cb_data.startswith(ADMIN_CALLBACKS):
                if not app.users.is_super_id(uid):
                    await app.audit.log("security.admin_callback_denied", actor_id=uid, actor_type="telegram", data=cb_data[:64])
                    s = await app.settings.all(uid)
                    await event.answer(tr(s["lang"], "⛔ Недостаточно прав.", "⛔ Huquq yetarli emas."), show_alert=True)
                    return None
                return await handler(event, data)
            if _is_public_callback(cb_data):
                return await handler(event, data)
            acc = await access(app, uid)
            if acc.locked:
                s = await app.settings.all(uid)
                await event.answer(tr(s["lang"], "🔒 Сначала подключите Telegram-аккаунт к Chat helper.",
                                      "🔒 Avval Telegram akkauntingizni Chat helper'ga ulang."), show_alert=True)
                if event.message is not None:
                    await show(app, uid, "locked", event.message, True)
                return None
            return await handler(event, data)
        if isinstance(event, Message) and event.from_user is not None and event.chat.type == "private":
            uid = event.from_user.id
            state: FSMContext | None = data.get("state")
            cur = await state.get_state() if state is not None else None
            if cur and cur.startswith(ADMIN_STATES) and not app.users.is_super_id(uid):
                await state.clear()
                await app.audit.log("security.admin_state_denied", actor_id=uid, actor_type="telegram", state=cur)
                s = await app.settings.all(uid)
                await event.answer(tr(s["lang"], "⛔ Недостаточно прав.", "⛔ Huquq yetarli emas."))
                return None
            text = (event.text or "").strip()
            if text.startswith("/") and text.split()[0].split("@")[0].lower() in PUBLIC_COMMANDS:
                return await handler(event, data)
            if cur and cur.startswith(PUBLIC_STATES):
                return await handler(event, data)
            if cur:
                acc = await access(app, uid)
                if acc.locked:
                    await state.clear()
                    s = await app.settings.all(uid)
                    await event.answer(tr(s["lang"], "🔒 Сначала подключите Telegram-аккаунт: /connect",
                                          "🔒 Avval Telegram akkauntingizni ulang: /connect"))
                    return None
        return await handler(event, data)
