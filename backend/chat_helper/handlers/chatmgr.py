"""Chat Context Manager: «💬 Мои чаты», per-chat control panel in the bot DM and the Manage-Bot deep link.

Telegram shows a «bot manages this chat» bar in every managed chat; its settings button opens the bot with
``/start bizChat<user_chat_id>``. The payload is user-controlled, so it is never trusted: the sender must own an
enabled Business connection **and** the chat must be one that Chat helper has seen for that owner. Otherwise a safe
picker of the owner's own chats is shown — a random or foreign chat is never opened.
"""
from __future__ import annotations

import logging
import time
from typing import Any

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from ..core.timeutil import fmt_dt, human_duration
from ..keyboards import kb, paginate, pager
from ..localization import tr
from ..modules.autoreply import mode_title
from ..modules.controls import refresh_cards, set_mute
from ..security.sanitize import clip, esc
from .ui import PanelGate, access, ensure_user, render, screen

log = logging.getLogger(__name__)
router = Router(name="chatmgr")
router.message.filter(F.chat.type == "private")
router.callback_query.filter(F.message.chat.type == "private")
router.callback_query.middleware(PanelGate())


def _onoff(lang: str, v: bool) -> str:
    return tr(lang, "🟢 вкл", "🟢 yoq") if v else tr(lang, "⚪️ выкл", "⚪️ o'ch")


async def chat_panel(app: Any, owner: int, chat_id: int) -> tuple[str, Any]:
    s = await app.settings.all(owner)
    lang, tz = s["lang"], s.get("timezone") or app.config.timezone
    row = await app.chats.get(owner, chat_id)
    if row is None:
        return tr(lang, "Чат не найден.", "Chat topilmadi."), kb([[(tr(lang, "◀️ К списку чатов", "◀️ Chatlar ro'yxati"), "m:chats")]])
    acc = await access(app, owner)
    ctl = app.controls
    states = {m: await ctl.is_on(owner, chat_id, m) for m in ("mute", "protect", "nogif", "nomute")}
    mute = await ctl.get(owner, chat_id, "mute")
    words = ((await ctl.get(owner, chat_id, "nomute")) or {}).get("state", {}).get("words") or []
    afk = await app.afk.active(owner)
    ai_on = s["mode"] in ("ai", "hybrid") and row.get("ai_enabled") != 0
    name = esc(clip(row.get("title") or str(chat_id), 40)) + (f" (@{esc(row['username'])})" if row.get("username") else "")
    t = lambda ru, uz, **kw: tr(lang, ru, uz, **kw)  # noqa: E731
    lines = [t("💬 <b>Управление чатом</b>", "💬 <b>Chatni boshqarish</b>"), "",
             t("👤 Собеседник: {n}", "👤 Suhbatdosh: {n}", n=name),
             t("🔗 Подключение: {v}", "🔗 Ulanish: {v}", v=t("🟢 активно", "🟢 faol") if acc.connected else t("⚫️ отключено", "⚫️ uzilgan")),
             t("🧠 AI: {v}", "🧠 AI: {v}", v=_onoff(lang, ai_on) + (f" · {mode_title(s['mode'], lang)}" if s["mode"] in ("ai", "hybrid") else "")),
             t("💤 AFK: {v} · в этом чате: {c}", "💤 AFK: {v} · bu chatda: {c}", v=_onoff(lang, bool(afk)),
               c=t("отвечать", "javob berish") if row.get("afk_enabled") != 0 else t("молчать", "jim turish")),
             t("🔕 Mute: {v}", "🔕 Mute: {v}", v=_onoff(lang, states["mute"]) + (
                 (" · " + (t("до {x}", "{x} gacha", x=fmt_dt(mute["until_at"], tz, with_date=False)) if mute.get("until_at")
                           else t("бессрочно", "muddatsiz")) + t(" · удалено {d}", " · o'chirildi {d}", d=mute["state"].get("deleted", 0)))
                 if states["mute"] and mute else "")),
             t("🛡 Protect: {v}", "🛡 Protect: {v}", v=_onoff(lang, states["protect"])),
             t("🚫 GIF/стикеры: {v} · 🧹 Слова: {w}", "🚫 GIF/stikerlar: {v} · 🧹 So'zlar: {w}", v=_onoff(lang, states["nogif"]),
               w=(_onoff(lang, states["nomute"]) + f" ({len(words)})")),
             t("🎬 Media: {v}", "🎬 Media: {v}", v=_onoff(lang, bool(s.get("media_enabled", True))))]
    if row.get("muted_until") and row["muted_until"] > time.time():
        lines.append(t("🤫 Без автоответов ещё {d}", "🤫 Avtojavobsiz yana {d}", d=human_duration(row["muted_until"] - time.time(), lang)))
    c = f"ch:{chat_id}"
    rows = [[(t("🧠 AI {x}", "🧠 AI {x}", x="⏹" if ai_on else "▶️"), f"{c}:ai"), (t("🔕 Mute {x}", "🔕 Mute {x}", x="⏹" if states["mute"] else "▶️"), f"{c}:mute")],
            [(t("🛡 Protect {x}", "🛡 Protect {x}", x="⏹" if states["protect"] else "▶️"), f"{c}:protect"),
             (t("💤 AFK тут {x}", "💤 AFK bu yerda {x}", x="⏹" if row.get("afk_enabled") != 0 else "▶️"), f"{c}:afk")],
            [(t("🚫 GIF/стикеры {x}", "🚫 GIF/stiker {x}", x="⏹" if states["nogif"] else "▶️"), f"{c}:nogif"),
             (t("🧹 Слова", "🧹 So'zlar"), f"{c}:words")],
            [(t("⚡ Быстрые команды", "⚡ Tezkor buyruqlar"), f"{c}:quick"), (t("⚙️ Расширенные", "⚙️ Kengaytirilgan"), f"{c}:adv")],
            [(t("◀️ Мои чаты", "◀️ Chatlarim"), "m:chats"), (t("🏠 Меню", "🏠 Menyu"), "m:home")]]
    return "\n".join(lines), kb(rows)


async def send_chat_panel(app: Any, owner: int, chat_id: int, focus: str | None = None) -> None:
    text, markup = await chat_panel(app, owner, chat_id)
    await app.sender.send_text(owner, text, markup=markup)


@screen("chats")
async def screen_chats(app: Any, uid: int, s: dict[str, Any], page: int = 0) -> tuple[str, Any]:
    lang = s["lang"]
    data = await app.chats.list(uid, sort="recent", page=1, page_size=200)
    items = data["items"]
    lines = [tr(lang, "💬 <b>Мои чаты</b>", "💬 <b>Chatlarim</b>"), ""]
    if not items:
        lines.append(tr(lang, "Пока нет чатов. Они появятся, когда в подключённых чатах будут новые сообщения.",
                        "Hozircha chatlar yo'q. Ulangan chatlarda yangi xabarlar paydo bo'lganda ko'rinadi."))
    chunk, page, pages = paginate(items, int(page), 8)
    rows = []
    for r in chunk:
        icons = ""
        for m, ic in (("mute", "🔕"), ("protect", "🛡"), ("nogif", "🚫"), ("nomute", "🧹")):
            if await app.controls.is_on(uid, r["chat_id"], m):
                icons += ic
        label = (icons + " " if icons else "") + clip(r.get("title") or str(r["chat_id"]), 28) + (f" · {r['unanswered']}" if r.get("unanswered") else "")
        rows.append([(label, f"ch:{r['chat_id']}:open")])
    if pages > 1:
        rows.append(pager("m:chats", page, pages))
    rows.append([(tr(lang, "⬅️ Назад", "⬅️ Orqaga"), "m:home")])
    return "\n".join(lines), kb(rows)


async def open_from_deeplink(app: Any, uid: int, payload: str, message: Message) -> None:
    """/start bizChat<user_chat_id> from Telegram's «bot manages this chat» bar."""
    s = await app.settings.all(uid)
    lang = s["lang"]
    raw = payload[len("bizChat"):]
    acc = await access(app, uid)
    if not acc.connected:
        from .onboarding import send_wizard
        await send_wizard(app, uid, message)
        return
    chat_id = int(raw) if raw.lstrip("-").isdigit() else None
    row = await app.chats.get(uid, chat_id) if chat_id is not None else None
    await app.audit.log("chat_context.deeplink", actor_id=uid, actor_type="telegram", target_type="chat", target_id=chat_id,
                        verified=row is not None)
    if row is None:
        text = tr(lang, "🔍 Не удалось подтвердить этот чат: Chat helper ещё не видел в нём сообщений после подключения. "
                        "Выберите чат из списка или напишите в нём любое сообщение и откройте панель снова.",
                  "🔍 Bu chatni tasdiqlab bo'lmadi: Chat helper ulangandan keyin unda xabar ko'rmagan. "
                  "Ro'yxatdan chat tanlang yoki unga xabar yozib, panelni qayta oching.")
        _, markup = await screen_chats(app, uid, s)
        await message.answer(text, reply_markup=markup)
        return
    text, markup = await chat_panel(app, uid, chat_id)
    await message.answer(text, reply_markup=markup)


# ---------------------------------------------------------------------------------------------------------
@router.callback_query(F.data.startswith("ch:"))
async def cb_chat(cb: CallbackQuery, app: Any) -> None:
    uid = await ensure_user(app, cb)
    s = await app.settings.all(uid)
    lang = s["lang"]
    t = lambda ru, uz, **kw: tr(lang, ru, uz, **kw)  # noqa: E731
    parts = (cb.data or "").split(":")
    if len(parts) < 3 or not parts[1].lstrip("-").isdigit():
        await cb.answer()
        return
    chat_id, action = int(parts[1]), parts[2]
    arg = parts[3] if len(parts) > 3 else ""
    row = await app.chats.get(uid, chat_id)          # ownership: only chats of this owner exist for him
    if row is None:
        await cb.answer(t("Чат не найден.", "Chat topilmadi."), show_alert=True)
        return
    acc = await access(app, uid)
    conn = acc.conn
    toast = ""
    if action == "ai":
        if s["mode"] not in ("ai", "hybrid"):
            await cb.answer(t("Сначала включите режим AI или Hybrid: меню → Автоответчик.", "Avval AI yoki Hybrid rejimini yoqing: menyu → Avtojavob."),
                            show_alert=True)
            return
        await app.chats.update(uid, chat_id, {"ai_enabled": row.get("ai_enabled") == 0})
        toast = "🧠"
    elif action == "afk":
        await app.chats.update(uid, chat_id, {"afk_enabled": row.get("afk_enabled") == 0})
        toast = "💤"
    elif action in ("protect", "nogif"):
        on = not await app.controls.is_on(uid, chat_id, action)
        if action == "nogif" and on and not (conn and conn.can("can_delete_all_messages")):
            await cb.answer(t("🔐 Нужно право «Удаление входящих» в настройках Автоматизации чатов.",
                              "🔐 Chat automation sozlamalarida «Kiruvchilarni o'chirish» huquqi kerak."), show_alert=True)
            return
        await app.controls.set(uid, chat_id, action, on, connection_id=conn.id if conn else None)
        await refresh_cards(app, uid, chat_id, action)
        toast = "✅" if on else "⏹"
    elif action == "mute":
        if await app.controls.is_on(uid, chat_id, "mute"):
            await set_mute(app, uid, chat_id, False)
            toast = t("🔓 Mute отключён", "🔓 Mute o'chirildi")
        else:
            if not (conn and conn.can("can_delete_all_messages")):
                await cb.answer(t("🔐 Для Mute нужно право «Удаление входящих» в настройках Автоматизации чатов.",
                                  "🔐 Mute uchun Chat automation sozlamalarida «Kiruvchilarni o'chirish» huquqi kerak."), show_alert=True)
                return
            if not s.get("mute_confirmed") and arg != "ok":
                text = t("⚠️ <b>Включить Mute?</b>\nНовые входящие сообщения в этом чате будут удаляться у обеих сторон (если Telegram разрешает). "
                         "Удаление необратимо; ваши сообщения и старая переписка не затрагиваются.",
                         "⚠️ <b>Mute yoqilsinmi?</b>\nUshbu chatdagi yangi kiruvchi xabarlar ikkala tomonda o'chiriladi (Telegram ruxsat bersa). "
                         "O'chirish qaytarilmaydi; sizning xabarlaringiz va eski yozishmalar o'zgarmaydi.")
                markup = kb([[(t("✅ Включить", "✅ Yoqish"), f"ch:{chat_id}:mute:ok")],
                             [(t("✅ Включить и не спрашивать", "✅ Yoqish va so'ramaslik"), f"ch:{chat_id}:muteall:ok")],
                             [(t("✖️ Отмена", "✖️ Bekor qilish"), f"ch:{chat_id}:open")]])
                await cb.answer()
                await render(cb.message, text, markup)
                return
            await set_mute(app, uid, chat_id, True, conn_id=conn.id if conn else None)
            await app.controls.update_state(uid, chat_id, "mute", confirmed_at=int(time.time()))
            toast = t("🔕 Mute включён", "🔕 Mute yoqildi")
    elif action == "muteall":
        await app.settings.set(uid, "mute_confirmed", True)
        await set_mute(app, uid, chat_id, True, conn_id=conn.id if conn else None)
        toast = t("🔕 Mute включён", "🔕 Mute yoqildi")
    elif action == "words":
        words = ((await app.controls.get(uid, chat_id, "nomute")) or {}).get("state", {}).get("words") or []
        text = "\n".join([t("🧹 <b>Фильтр слов</b>", "🧹 <b>So'z filtri</b>"),
                          t("Входящие сообщения с этими словами удаляются.", "Ushbu so'zli kiruvchi xabarlar o'chiriladi."), "",
                          ("• " + ", ".join(esc(w) for w in words)) if words else t("Слов пока нет.", "Hozircha so'z yo'q."), "",
                          t("Добавить: в этом чате напишите <code>{p}nomute add слово</code>", "Qo'shish: shu chatda <code>{p}nomute add so'z</code> yozing",
                            p=s["prefix"])])
        on = await app.controls.is_on(uid, chat_id, "nomute")
        rows = [[((t("⏹ Выключить фильтр", "⏹ Filtrni o'chirish") if on else t("▶️ Включить фильтр", "▶️ Filtrni yoqish")), f"ch:{chat_id}:nomute")]]
        if words:
            rows.append([(t("🗑 Очистить слова", "🗑 So'zlarni tozalash"), f"ch:{chat_id}:wclear")])
        rows.append([(t("◀️ Назад", "◀️ Orqaga"), f"ch:{chat_id}:open")])
        await cb.answer()
        await render(cb.message, text, kb(rows))
        return
    elif action == "nomute":
        words = ((await app.controls.get(uid, chat_id, "nomute")) or {}).get("state", {}).get("words") or []
        on = not await app.controls.is_on(uid, chat_id, "nomute")
        if on and not words:
            await cb.answer(t("Сначала добавьте слова командой .nomute add", "Avval .nomute add bilan so'z qo'shing"), show_alert=True)
            return
        await app.controls.set(uid, chat_id, "nomute", on, connection_id=conn.id if conn else None)
        await refresh_cards(app, uid, chat_id, "nomute")
        toast = "✅" if on else "⏹"
    elif action == "wclear":
        await app.controls.set(uid, chat_id, "nomute", False, state={"words": []})
        await refresh_cards(app, uid, chat_id, "nomute")
        toast = "🗑"
    elif action == "quick":
        text = t("⚡ <b>Быстрые действия для чата</b>", "⚡ <b>Chat uchun tezkor amallar</b>")
        rows = [[(t("📝 Пересказ последних 30 сообщений", "📝 So'nggi 30 xabar xulosasi"), f"ch:{chat_id}:q:sum")],
                [(t("🔕 Mute на 1 час", "🔕 1 soatga Mute"), f"ch:{chat_id}:q:mute1h"), (t("🎲 Кубик в чат", "🎲 Chatga zar"), f"ch:{chat_id}:q:dice")],
                [(t("🧹 Сбросить AI-контекст", "🧹 AI kontekstini tozalash"), f"ch:{chat_id}:q:resetai")],
                [(t("◀️ Назад", "◀️ Orqaga"), f"ch:{chat_id}:open")]]
        await cb.answer()
        await render(cb.message, text, kb(rows))
        return
    elif action == "q":
        toast = await _quick(app, uid, chat_id, arg, conn, s)
        if toast is None:
            return await cb.answer()
    elif action == "adv":
        text = "\n".join([t("⚙️ <b>Расширенные настройки чата</b>", "⚙️ <b>Chatning kengaytirilgan sozlamalari</b>"), "",
                          t("Язык ответов: {l}", "Javob tili: {l}", l=(row.get("language") or t("как в настройках", "sozlamalardagidek")).upper()),
                          t("Лимит автоответов в день: {n}", "Kunlik avtojavob limiti: {n}", n=row.get("reply_limit") or s["max_auto_replies_per_chat_day"]),
                          t("Игнорировать чат: {v}", "Chatni e'tiborsiz qoldirish: {v}", v=_onoff(lang, bool(row.get("ignored"))))])
        c = f"ch:{chat_id}"
        rows = [[("RU", f"{c}:lang:ru"), ("UZ", f"{c}:lang:uz"), (t("Авто", "Avto"), f"{c}:lang:auto")],
                [("5/" + t("день", "kun"), f"{c}:limit:5"), ("20", f"{c}:limit:20"), ("50", f"{c}:limit:50")],
                [(t("🙈 Игнор вкл/выкл", "🙈 E'tiborsiz yoq/o'ch"), f"{c}:ignore")],
                [(t("◀️ Назад", "◀️ Orqaga"), f"{c}:open")]]
        await cb.answer()
        await render(cb.message, text, kb(rows))
        return
    elif action == "lang" and arg in ("ru", "uz", "auto"):
        await app.chats.update(uid, chat_id, {"language": None if arg == "auto" else arg})
        toast = "✅"
    elif action == "limit" and arg.isdigit():
        await app.chats.update(uid, chat_id, {"reply_limit": int(arg)})
        toast = "✅"
    elif action == "ignore":
        await app.chats.update(uid, chat_id, {"ignored": not bool(row.get("ignored"))})
        toast = "✅"
    text, markup = await chat_panel(app, uid, chat_id)
    await cb.answer(toast or None)
    await render(cb.message, text, markup)


async def _quick(app: Any, uid: int, chat_id: int, what: str, conn: Any, s: dict[str, Any]) -> str | None:
    lang = s["lang"]
    if what == "mute1h":
        if not (conn and conn.can("can_delete_all_messages")):
            return tr(lang, "🔐 Нужно право «Удаление входящих»", "🔐 «Kiruvchilarni o'chirish» huquqi kerak")
        if not s.get("mute_confirmed"):
            return tr(lang, "Сначала включите Mute кнопкой выше и подтвердите", "Avval yuqoridagi tugma bilan Mute'ni yoqib, tasdiqlang")
        await set_mute(app, uid, chat_id, True, until_for=3600, conn_id=conn.id)
        return tr(lang, "🔕 Mute на 1 час", "🔕 1 soatga Mute")
    if what == "dice":
        if not (conn and conn.can("can_reply")):
            return tr(lang, "🔐 Нет права «Ответы на сообщения»", "🔐 «Javob berish» huquqi yo'q")
        res = await app.sender.send_dice(chat_id, "🎲", bc_id=conn.id)
        return "🎲" if res.ok else tr(lang, "Не удалось ({k})", "Bo'lmadi ({k})", k=res.kind)
    if what == "resetai":
        await app.ai.memory.clear_chat(uid, chat_id)
        return "🧹"
    if what == "sum":
        from ..modules.ai_cmds import summarize_chat
        text = await summarize_chat(app, uid, chat_id, 30, lang)
        await app.sender.send_text(uid, text)
        return "📝"
    return None


@router.callback_query(F.data.startswith("cmute:"))
async def cb_legacy_quiet(cb: CallbackQuery, app: Any) -> None:
    """Old v2 «quiet for 2h» button from inbox alerts (kept for already sent messages)."""
    uid = await ensure_user(app, cb)
    chat_id = cb.data.split(":")[1]
    if not chat_id.lstrip("-").isdigit():
        await cb.answer()
        return
    row = await app.chats.update(uid, int(chat_id), {"muted_until": int(time.time()) + 7200})
    await cb.answer("🤫" if row else "—")

