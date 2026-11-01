"""Onboarding before a Business connection exists: welcome, connection wizard, infographic, check, language.

Telegram path (2026 clients): Settings → Edit profile → «Chat automation» (older clients: Telegram Business → Chatbots).
The «Open settings» button uses ``tg://settings/edit``; if a client or the server rejects that link the keyboard is
re-sent without it and the text instructions remain — no dead buttons.
"""
from __future__ import annotations

import logging
from typing import Any

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, InlineKeyboardMarkup, Message

from ..business.rights import inspect, status_title
from ..keyboards import kb, without_tg_links
from ..localization import tr
from ..media.infographic import png_bytes
from .ui import access, ensure_user, render, screen, show

log = logging.getLogger(__name__)
router = Router(name="onboarding")
router.message.filter(F.chat.type == "private")
router.callback_query.filter(F.message.chat.type == "private")

SETTINGS_LINK = "tg://settings/edit"
_photo_cache: dict[str, str] = {}   # lang -> Telegram file_id of the uploaded infographic


def bot_username(app: Any) -> str:
    return getattr(getattr(app, "bot_info", None), "username", None) or "ChatHelperBot"


# ---------------------------------------------------------------------------------------------------------
@screen("locked", public=True)
async def screen_welcome(app: Any, uid: int, s: dict[str, Any]) -> tuple[str, Any]:
    lang = s["lang"]
    acc = await access(app, uid)
    text = "\n".join([
        tr(lang, "✨ <b>Chat helper</b>", "✨ <b>Chat helper</b>"),
        tr(lang, "Умный помощник для Telegram.", "Telegram uchun aqlli yordamchi."), "",
        tr(lang, "🧠 AI-ассистент и AI-двойник", "🧠 AI yordamchi va AI-egizak"),
        tr(lang, "💬 Автоответчик и бизнес-часы", "💬 Avtojavob va ish vaqti"),
        tr(lang, "💤 AFK с таймером", "💤 Taymerli AFK"),
        tr(lang, "🔕 Mute и 🛡 Protect для отдельных чатов", "🔕 Alohida chatlar uchun Mute va 🛡 Protect"),
        tr(lang, "🎬 Media Studio · 🎮 Игры · ⚡ Команды в чатах", "🎬 Media Studio · 🎮 O'yinlar · ⚡ Chatlarda buyruqlar"), "",
        tr(lang, "Для начала подключите свой Telegram-аккаунт. Это официальная функция Telegram «Автоматизация чатов»: "
                 "без паролей, кодов входа и сторонних программ.",
           "Boshlash uchun Telegram akkauntingizni ulang. Bu Telegram'ning rasmiy «Chat automation» funksiyasi: "
           "parollar, kirish kodlari va begona dasturlarsiz."),
    ])
    rows = [[(tr(lang, "🔗 Подключить", "🔗 Ulash"), "m:connect"), (tr(lang, "📖 Возможности", "📖 Imkoniyatlar"), "m:features")],
            [(tr(lang, "🌐 Язык", "🌐 Til"), "m:lang"), (tr(lang, "❓ Помощь", "❓ Yordam"), "m:help")]]
    if acc.is_super:
        rows.append([(tr(lang, "👑 Админ-панель", "👑 Admin panel"), "m:admin")])
    return text, kb(rows)


def wizard_text(app: Any, lang: str) -> str:
    b = bot_username(app)
    return "\n".join([
        tr(lang, "🔗 <b>Подключение Chat helper</b>", "🔗 <b>Chat helper'ni ulash</b>"), "",
        tr(lang, "1️⃣ Скопируйте username бота: <code>@{b}</code>", "1️⃣ Bot username'ini nusxalang: <code>@{b}</code>", b=b),
        tr(lang, "2️⃣ Откройте настройки Telegram → «Изм.» (профиль)", "2️⃣ Telegram sozlamalari → «Tahrirlash» (profil)"),
        tr(lang, "3️⃣ Найдите раздел «Автоматизация чатов»\n      <i>в старых версиях: Telegram для бизнеса → Чат-боты</i>",
           "3️⃣ «Chat automation» (Chatlarni avtomatlashtirish) bo'limini toping\n      <i>eski versiyalarda: Telegram Business → Chat-botlar</i>"),
        tr(lang, "4️⃣ Нажмите «Добавить» и вставьте <code>@{b}</code>", "4️⃣ «Qo'shish» ni bosing va <code>@{b}</code> ni qo'ying", b=b),
        tr(lang, "5️⃣ Выберите чаты: все личные или только нужные", "5️⃣ Chatlarni tanlang: barcha shaxsiy yoki faqat keraklilari"),
        tr(lang, "6️⃣ Права: «Ответы на сообщения» обязательно; «Удаление входящих» — для 🔕 Mute; "
                 "«Удаление исходящих» — для уборки команд. Подарки и звёзды не включайте.",
           "6️⃣ Huquqlar: «Xabarlarga javob berish» majburiy; «Kiruvchilarni o'chirish» — 🔕 Mute uchun; "
           "«Chiquvchilarni o'chirish» — buyruqlarni tozalash uchun. Sovg'a va yulduzlarni yoqmang."),
        tr(lang, "7️⃣ Вернитесь сюда и нажмите «🔄 Проверить подключение»", "7️⃣ Bu yerga qayting va «🔄 Ulanishni tekshirish» ni bosing"), "",
        tr(lang, "ℹ️ Бот работает через официальный Telegram Bot API. Мы никогда не просим пароли, коды входа или файлы сессии.",
           "ℹ️ Bot rasmiy Telegram Bot API orqali ishlaydi. Biz hech qachon parol, kirish kodi yoki sessiya fayllarini so'ramaymiz."),
    ])


def wizard_rows(app: Any, lang: str) -> list[list[tuple[str, str]]]:
    b = bot_username(app)
    return [[(tr(lang, "📋 Скопировать @{b}", "📋 @{b} ni nusxalash", b=b), f"copy:@{b}")],
            [(tr(lang, "⚙️ Открыть настройки Telegram", "⚙️ Telegram sozlamalarini ochish"), "url:" + SETTINGS_LINK)],
            [(tr(lang, "🖼 Инструкция в картинке", "🖼 Rasmli yo'riqnoma"), "ob:guide")],
            [(tr(lang, "🔄 Проверить подключение", "🔄 Ulanishni tekshirish"), "ob:check")],
            [(tr(lang, "⬅️ Назад", "⬅️ Orqaga"), "m:home")]]


@screen("connect", public=True)
async def screen_connect(app: Any, uid: int, s: dict[str, Any]) -> tuple[str, Any]:
    lang = s["lang"]
    acc = await access(app, uid)
    if not acc.connected:
        conns = await app.connections.for_user(uid)
        text = wizard_text(app, lang)
        if conns:  # known but disabled connection
            text += "\n\n" + tr(lang, "⚫️ Ранее подключение было отключено — добавьте бота снова по шагам выше.",
                                "⚫️ Ulanish avval o'chirilgan — botni yuqoridagi qadamlar bo'yicha qayta qo'shing.")
        return text, kb(wizard_rows(app, lang))
    return await connection_status_screen(app, uid, s)


async def connection_status_screen(app: Any, uid: int, s: dict[str, Any]) -> tuple[str, Any]:
    from ..core.timeutil import fmt_dt
    lang = s["lang"]
    conns = await app.connections.for_user(uid)
    lines = [tr(lang, "🔗 <b>Подключение аккаунта</b>", "🔗 <b>Akkaunt ulanishi</b>"), ""]
    rows: list[list[tuple[str, str]]] = []
    for i, c in enumerate(conns[:5]):
        rep = inspect(c.rights, c.is_enabled, lang, c.paused)
        granted = sum(1 for v in c.rights.values() if v)
        lines.append(f"{status_title(c.status, lang)} · {fmt_dt(c.connected_at, s['timezone'])}"
                     + (tr(lang, " · ⏸ пауза", " · ⏸ pauza") if c.paused else ""))
        lines.append(tr(lang, "   Права: {g} из {n} · возможностей: {a}", "   Huquqlar: {g}/{n} · imkoniyatlar: {a}",
                        g=granted, n=len(c.rights), a=sum(1 for cap in rep["capabilities"] if cap["available"])))
        rows.append([(tr(lang, "🔍 Права", "🔍 Huquqlar"), f"conn:insp:{i}"),
                     ((tr(lang, "▶️ Возобновить", "▶️ Davom") if c.paused else tr(lang, "⏸ Пауза", "⏸ Pauza")),
                      f"conn:{'resume' if c.paused else 'pause'}:{i}")])
    lines += ["", tr(lang, "Отключить бота: Настройки → Изм. → Автоматизация чатов → Chat helper → Отключить.",
                     "Botni uzish: Sozlamalar → Tahrirlash → Chat automation → Chat helper → O'chirish.")]
    rows.append([(tr(lang, "🔄 Обновить статус", "🔄 Holatni yangilash"), "ob:check")])
    rows.append([(tr(lang, "⬅️ Назад", "⬅️ Orqaga"), "m:home")])
    return "\n".join(lines), kb(rows)


@screen("features", public=True)
async def screen_features(app: Any, uid: int, s: dict[str, Any]) -> tuple[str, Any]:
    lang = s["lang"]
    p = s["prefix"]
    text = "\n".join([
        tr(lang, "📖 <b>Возможности Chat helper</b>", "📖 <b>Chat helper imkoniyatlari</b>"), "",
        tr(lang, "⚡ <b>Команды прямо в чатах</b>: пишите <code>{p}afk</code>, <code>{p}ai вопрос</code>, <code>{p}mute</code> — "
                 "бот выполнит и заменит команду результатом.",
           "⚡ <b>Chatlarda buyruqlar</b>: <code>{p}afk</code>, <code>{p}ai savol</code>, <code>{p}mute</code> deb yozing — "
           "bot bajaradi va buyruqni natija bilan almashtiradi.", p=p),
        tr(lang, "🎛 <b>Кнопки управления</b> под сообщениями: выключить Mute, AFK или автоответ в одно касание.",
           "🎛 Xabarlar ostidagi <b>boshqaruv tugmalari</b>: Mute, AFK yoki avtojavobni bir bosishda o'chirish."),
        tr(lang, "🧠 <b>AI</b>: ответы, перевод, пересказ, подсказки, AI-двойник в вашем стиле.",
           "🧠 <b>AI</b>: javoblar, tarjima, xulosa, maslahatlar, sizning uslubingizdagi AI-egizak."),
        tr(lang, "🔕 <b>Mute</b>: новые входящие в выбранном чате удаляются (если Telegram разрешает).",
           "🔕 <b>Mute</b>: tanlangan chatdagi yangi kiruvchi xabarlar o'chiriladi (Telegram ruxsat bersa)."),
        tr(lang, "🎬 <b>Media Studio</b>: кружки, реверс, скорость, громкость, рамки, мемы, GIF, OCR.",
           "🎬 <b>Media Studio</b>: dumaloq video, teskari, tezlik, ovoz, ramkalar, memlar, GIF, OCR."),
        tr(lang, "🎮 <b>Игры</b>: дуэль, крестики-нолики, викторина, кости и другие — без ставок.",
           "🎮 <b>O'yinlar</b>: duel, krestik-nolik, viktorina, zar va boshqalar — garovsiz."),
        tr(lang, "📱 <b>Chat helper Control</b>: приложение для Android с полным управлением.",
           "📱 <b>Chat helper Control</b>: to'liq boshqaruvli Android ilova."), "",
        tr(lang, "Ограничения Telegram: только личные чаты; бот пишет, если собеседник писал за 24 часа; "
                 "статус «в сети» изменить нельзя.",
           "Telegram cheklovlari: faqat shaxsiy chatlar; suhbatdosh 24 soat ichida yozgan bo'lsa bot yozadi; "
           "«onlayn» holatini o'zgartirib bo'lmaydi."),
    ])
    rows = [[(tr(lang, "🔗 Подключить", "🔗 Ulash"), "m:connect")], [(tr(lang, "⬅️ Назад", "⬅️ Orqaga"), "m:home")]]
    return text, kb(rows)


@screen("lang", public=True)
async def screen_lang(app: Any, uid: int, s: dict[str, Any]) -> tuple[str, Any]:
    lang = s["lang"]
    text = tr(lang, "🌐 <b>Язык интерфейса</b>\nВыберите язык меню, кнопок, подсказок и ответов бота.",
              "🌐 <b>Interfeys tili</b>\nMenyu, tugmalar, maslahatlar va bot javoblari tilini tanlang.")
    rows = [[(("✅ " if lang == "ru" else "") + "🇷🇺 Русский", "ob:lang:ru"), (("✅ " if lang == "uz" else "") + "🇺🇿 O'zbekcha", "ob:lang:uz")],
            [(tr(lang, "⬅️ Назад", "⬅️ Orqaga"), "m:home")]]
    return text, kb(rows)


# ---------------------------------------------------------------------------------------------------------
async def send_wizard(app: Any, uid: int, target: Message, edit: bool = False) -> None:
    s = await app.settings.all(uid)
    text, markup = await screen_connect(app, uid, s)
    try:
        await render(target, text, markup, edit)
    except TelegramBadRequest as e:
        log.warning("wizard keyboard rejected (%s) — retrying without tg:// link", str(e)[:120])
        await target.answer(text + "\n\n" + tr(s["lang"], "⚙️ Откройте настройки Telegram вручную.", "⚙️ Telegram sozlamalarini qo'lda oching."),
                            reply_markup=without_tg_links(markup), disable_web_page_preview=True)


async def send_infographic(app: Any, uid: int, target: Message) -> None:
    s = await app.settings.all(uid)
    lang = s["lang"]
    caption = tr(lang, "🖼 Как подключить Chat helper — 6 шагов. Username: <code>@{b}</code>",
                 "🖼 Chat helper'ni qanday ulash — 6 qadam. Username: <code>@{b}</code>", b=bot_username(app))
    markup = kb(wizard_rows(app, lang)[:2] + [[(tr(lang, "🔄 Проверить подключение", "🔄 Ulanishni tekshirish"), "ob:check")]])
    photo = _photo_cache.get(lang) or BufferedInputFile(png_bytes(lang), filename=f"chat_helper_connect_{lang}.png")
    for attempt_markup in (markup, without_tg_links(markup)):
        try:
            msg = await target.answer_photo(photo, caption=caption, reply_markup=attempt_markup)
            if msg.photo:
                _photo_cache[lang] = msg.photo[-1].file_id
            return
        except TelegramBadRequest as e:
            log.warning("infographic send failed (%s)", str(e)[:120])
            photo = BufferedInputFile(png_bytes(lang), filename=f"chat_helper_connect_{lang}.png")
    await target.answer(wizard_text(app, lang), reply_markup=without_tg_links(markup))


async def check_connection(app: Any, uid: int) -> tuple[bool, str, InlineKeyboardMarkup]:
    s = await app.settings.all(uid)
    lang = s["lang"]
    acc = await access(app, uid)
    if acc.connected:
        rep = inspect(acc.conn.rights, acc.conn.is_enabled, lang, acc.conn.paused)
        ok = [c["description"] for c in rep["capabilities"] if c["available"]]
        missing = [c for c in rep["capabilities"] if not c["available"]]
        lines = [tr(lang, "✅ <b>Подключение активно!</b>", "✅ <b>Ulanish faol!</b>"), rep["status_title"], ""]
        if ok:
            lines.append(tr(lang, "Доступно: {n}", "Mavjud: {n}", n=len(ok)))
        if missing:
            lines.append(tr(lang, "Без прав недоступно: {n} (подробнее — «🔍 Права»)", "Huquqsiz mavjud emas: {n} (batafsil — «🔍 Huquqlar»)",
                            n=len(missing)))
        rows = [[(tr(lang, "🏠 Открыть меню", "🏠 Menyuni ochish"), "m:home")],
                [(tr(lang, "🔍 Права", "🔍 Huquqlar"), "conn:insp:0")]]
        return True, "\n".join(lines), kb(rows)
    conns = await app.connections.for_user(uid)
    if conns:
        text = tr(lang, "⚫️ Подключение найдено, но выключено. Откройте «Автоматизация чатов» и включите Chat helper снова.",
                  "⚫️ Ulanish topildi, lekin o'chirilgan. «Chat automation» ni ochib, Chat helper'ni qayta yoqing.")
    else:
        text = "\n".join([
            tr(lang, "🔍 <b>Подключение пока не найдено.</b>", "🔍 <b>Ulanish hali topilmadi.</b>"), "",
            tr(lang, "Проверьте:", "Tekshiring:"),
            tr(lang, "• бот добавлен в «Автоматизация чатов» (username <code>@{b}</code>);",
               "• bot «Chat automation» ga qo'shilgan (username <code>@{b}</code>);", b=bot_username(app)),
            tr(lang, "• выбран хотя бы один чат;", "• kamida bitta chat tanlangan;"),
            tr(lang, "• бот не поставлен на паузу.", "• bot pauzaga qo'yilmagan."), "",
            tr(lang, "Если вы только что подключили — подождите несколько секунд и нажмите ещё раз.",
               "Hozirgina ulagan bo'lsangiz — bir necha soniya kuting va yana bosing."),
        ])
    return False, text, kb(wizard_rows(app, lang)[:2] + [[(tr(lang, "🔄 Проверить ещё раз", "🔄 Yana tekshirish"), "ob:check")],
                                                          [(tr(lang, "🖼 Инструкция в картинке", "🖼 Rasmli yo'riqnoma"), "ob:guide")]])


# ---------------------------------------------------------------------------------------------------------
@router.message(Command("connect"))
async def cmd_connect(message: Message, state: FSMContext, app: Any) -> None:
    await state.clear()
    uid = await ensure_user(app, message)
    await send_wizard(app, uid, message)


@router.message(Command("help"))
async def cmd_help(message: Message, state: FSMContext, app: Any) -> None:
    await state.clear()
    uid = await ensure_user(app, message)
    await show(app, uid, "help", message, False)


@router.message(Command("lang"))
async def cmd_lang(message: Message, app: Any) -> None:
    uid = await ensure_user(app, message)
    await show(app, uid, "lang", message, False)


@router.callback_query(F.data.startswith("ob:"))
async def cb_onboarding(cb: CallbackQuery, app: Any) -> None:
    uid = await ensure_user(app, cb)
    parts = (cb.data or "").split(":")
    action = parts[1] if len(parts) > 1 else ""
    if action == "check":
        ok_rate, retry = app.limiter.check(f"obcheck:{uid}", 6, 60)
        if not ok_rate:
            s = await app.settings.all(uid)
            await cb.answer(tr(s["lang"], "⏳ Подождите {s} с.", "⏳ {s} soniya kuting.", s=retry), show_alert=True)
            return
        ok, text, markup = await check_connection(app, uid)
        await cb.answer("✅" if ok else "🔍")
        await app.metrics.incr("onboarding_check_ok" if ok else "onboarding_check_missing", uid)
        try:
            await render(cb.message, text, markup, True)
        except TelegramBadRequest:
            await cb.message.answer(text, reply_markup=without_tg_links(markup))
        return
    if action == "guide":
        await cb.answer()
        await send_infographic(app, uid, cb.message)
        return
    if action == "lang" and len(parts) > 2 and parts[2] in ("ru", "uz"):
        await app.settings.set(uid, "lang", parts[2])
        await app.users.set_language(uid, parts[2])
        await cb.answer("✅")
        await show(app, uid, "home", cb.message, True)
        return
    await cb.answer()


def welcome_after_connect(lang: str) -> tuple[str, InlineKeyboardMarkup]:
    text = tr(lang, "🎉 Готово! Откройте меню, чтобы настроить AI, AFK, Mute и другие функции.",
              "🎉 Tayyor! AI, AFK, Mute va boshqa funksiyalarni sozlash uchun menyuni oching.")
    return text, kb([[(tr(lang, "🏠 Открыть меню", "🏠 Menyuni ochish"), "m:home")]])

