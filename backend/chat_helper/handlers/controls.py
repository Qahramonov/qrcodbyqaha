"""Callback handler of the Chat Control Framework (``cc:`` buttons under control cards).

Checks, in this order, for every press: the card exists → the presser is the **owner** of the chat (Telegram user id
of the callback, never data from the button) → the card is still active → the Business connection is still enabled →
the button version matches the current state (stale/duplicate presses never toggle twice) → the callback id was not
processed before. Only then the action runs; the card(s) are re-rendered from the database state.
"""
from __future__ import annotations

import logging
from typing import Any

from aiogram import F, Router
from aiogram.types import CallbackQuery

from ..localization import tr
from ..modules.controls import apply_action, edit_card

log = logging.getLogger(__name__)
router = Router(name="controls")


@router.callback_query(F.data.startswith("cc:"))
async def on_control(cb: CallbackQuery, app: Any) -> None:
    parts = (cb.data or "").split(":")
    presser = cb.from_user.id
    lang = (await app.settings.all(presser))["lang"]
    if len(parts) < 4:
        await cb.answer()
        return
    _, token, action, version = parts[:4]
    arg = parts[4] if len(parts) > 4 else ""
    card = await app.controls.card(token)
    if card is None:
        await cb.answer(tr(lang, "⌛ Эта кнопка устарела.", "⌛ Bu tugma eskirgan."))
        return
    if presser != card["owner_id"]:
        await app.audit.log("controls.foreign_press", actor_id=presser, actor_type="telegram", target_type="control",
                            target_id=token, module=card["module"], button=action)
        await cb.answer(tr(lang, "⛔ Управлять этой настройкой может только владелец чата.",
                           "⛔ Bu sozlamani faqat chat egasi boshqara oladi."), show_alert=True)
        return
    if card["status"] == "revoked":
        await cb.answer(tr(lang, "🔌 Chat helper отключён от аккаунта — кнопки больше не работают. Подключите снова: /connect",
                           "🔌 Chat helper akkauntdan uzilgan — tugmalar ishlamaydi. Qayta ulang: /connect"), show_alert=True)
        return
    if card["status"] != "active":
        await cb.answer(tr(lang, "⌛ Это сообщение управления больше не активно.", "⌛ Bu boshqaruv xabari endi faol emas."))
        return
    if card["connection_id"]:
        conn = await app.connections.get(card["connection_id"])
        if conn is None or not conn.is_enabled:
            await app.controls.close_card(token, "revoked")
            await cb.answer(tr(lang, "🔌 Chat helper отключён от аккаунта — кнопки больше не работают. Подключите снова: /connect",
                               "🔌 Chat helper akkauntdan uzilgan — tugmalar ishlamaydi. Qayta ulang: /connect"), show_alert=True)
            return
    if not version.isdigit() or int(version) != card["version"]:
        await cb.answer(tr(lang, "🔄 Состояние уже изменилось — показываю актуальное.", "🔄 Holat o'zgargan — dolzarbini ko'rsataman."))
        await edit_card(app, card)
        return
    if not await app.controls.record_action(cb.id, token, presser, action, "accepted"):
        await cb.answer()
        return
    try:
        toast, view = await apply_action(app, card, action, arg)
    except Exception:
        log.exception("control action %s/%s failed", card["module"], action)
        await cb.answer(tr(lang, "⚠️ Не удалось выполнить действие. Ошибка записана в журнал.",
                           "⚠️ Amalni bajarib bo'lmadi. Xato jurnalga yozildi."), show_alert=True)
        return
    if view == "__closed__":
        bc = card["connection_id"] if card["location"] == "chat" else None
        await app.sender.edit_text(card["host_chat_id"], card["message_id"], tr(lang, "✖️ Отменено", "✖️ Bekor qilindi"), bc_id=bc)
    elif view:
        fresh = await app.controls.card(token)
        await edit_card(app, fresh or card, view)
    await cb.answer(toast or None)
