"""v3 user panel sections: My account, Delegation, Quick commands, Mute Manager, Protect Manager, Text tools, Reminders."""
from __future__ import annotations

import time
from typing import Any

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from ..business.rights import status_title
from ..core.timeutil import fmt_dt, parse_duration
from ..keyboards import kb
from ..localization import tr
from ..modules.chat_filters import MUTE_TYPES, type_title
from ..modules.controls import refresh_cards, set_mute
from ..security.sanitize import clip, esc
from ..services.delegation import SCOPES
from .ui import PanelGate, access, ensure_user, screen, show

router = Router(name="account")
router.message.filter(F.chat.type == "private")
router.callback_query.filter(F.message.chat.type == "private")
router.message.middleware(PanelGate())
router.callback_query.middleware(PanelGate())

QUICK_DEFAULT = ["afk", "unafk", "mute", "unmute", "protect", "ai", "sum", "a", "remind", "re"]
TEXT_TOOLS = [("calc", "2+2*2"), ("fix", "ghbdtn"), ("r", "Привет"), ("morse", "SOS"), ("ball", "Получится?"), ("upper", "текст"),
              ("translate", "en Привет"), ("base64", "hello"), ("hash", "md5 hello"), ("password", "16"), ("qr", "https://t.me"),
              ("uuid", ""), ("time", "Asia/Tashkent"), ("geo", "41.3111, 69.2797")]


class AC(StatesGroup):
    reminder = State()
    whitelist = State()


def _t(lang: str):
    return lambda ru, uz, **kw: tr(lang, ru, uz, **kw)


@screen("account")
async def screen_account(app: Any, uid: int, s: dict[str, Any]) -> tuple[str, Any]:
    lang = s["lang"]
    t = _t(lang)
    u = await app.users.get(uid) or {}
    acc = await access(app, uid)
    plan = await app.subs.plan_of(uid)
    grants = [k for k, v in (await app.delegation.grants(uid)).items() if v["active"]]
    lines = [t("👤 <b>Мой аккаунт</b>", "👤 <b>Mening akkauntim</b>"), "",
             f"🆔 <code>{uid}</code>" + (f" · @{esc(u['username'])}" if u.get("username") else ""),
             t("Имя: {n}", "Ism: {n}", n=esc(u.get("first_name") or "—")),
             t("Подключение: {s}", "Ulanish: {s}", s=status_title(acc.conn.status, lang) if acc.conn else t("⚪️ нет", "⚪️ yo'q")),
             t("Тариф: {p} · язык: {l}", "Tarif: {p} · til: {l}", p=plan.upper(), l=lang.upper()),
             t("Делегирование администратору: {d}", "Administratorga vakolat: {d}", d=", ".join(grants) if grants else t("нет", "yo'q"))]
    rows = [[(t("🔗 Подключение и права", "🔗 Ulanish va huquqlar"), "m:connect")],
            [(t("🤝 Делегирование", "🤝 Vakolat berish"), "m:delegation"), (t("🔐 Приватность и данные", "🔐 Maxfiylik va ma'lumotlar"), "m:privacy")],
            [(t("📱 Приложение и устройства", "📱 Ilova va qurilmalar"), "m:app"), (t("💎 Подписка", "💎 Obuna"), "m:sub")],
            [(t("🌐 Язык", "🌐 Til"), "m:lang"), (t("🏠 Меню", "🏠 Menyu"), "m:home")]]
    return "\n".join(lines), kb(rows)


@screen("delegation")
async def screen_delegation(app: Any, uid: int, s: dict[str, Any]) -> tuple[str, Any]:
    lang = s["lang"]
    t = _t(lang)
    grants = await app.delegation.grants(uid)
    lines = [t("🤝 <b>Делегирование</b>", "🤝 <b>Vakolat berish</b>"),
             t("Вы можете добровольно разрешить администратору Chat helper помогать с отдельными настройками. "
               "Права бота в Telegram сами по себе такого доступа не дают. Любое разрешение можно отозвать; каждое действие "
               "администратора записывается. Подарки и звёзды не делегируются никогда.",
               "Siz Chat helper administratoriga alohida sozlamalarda yordam berishga ixtiyoriy ruxsat berishingiz mumkin. "
               "Telegram'dagi bot huquqlari bunday kirishni o'z-o'zidan bermaydi. Har qanday ruxsatni qaytarib olish mumkin; "
               "administratorning har bir amali yoziladi. Sovg'a va yulduzlar hech qachon berilmaydi."), ""]
    rows = []
    for scope, title in SCOPES.items():
        on = bool(grants.get(scope, {}).get("active"))
        lines.append(("🟢 " if on else "⚪️ ") + tr(lang, *title))
        rows.append([(("⏹ " if on else "▶️ ") + tr(lang, *title).split(" ", 1)[1][:30], f"dg:{scope}")])
    rows.append([(t("⬅️ Мой аккаунт", "⬅️ Akkauntim"), "m:account")])
    return "\n".join(lines), kb(rows)


@screen("quick")
async def screen_quick(app: Any, uid: int, s: dict[str, Any]) -> tuple[str, Any]:
    lang = s["lang"]
    t = _t(lang)
    fav = s.get("favorite_commands") or QUICK_DEFAULT
    lines = [t("⚡ <b>Быстрые команды</b>", "⚡ <b>Tezkor buyruqlar</b>"),
             t("Нажмите, чтобы скопировать команду, и вставьте её в нужный чат.", "Buyruqni nusxalash uchun bosing va kerakli chatga qo'ying."), ""]
    rows = []
    for cid in fav[:12]:
        spec = app.registry.commands.get(cid)
        if spec is None:
            continue
        lines.append(f"<code>{s['prefix']}{cid}</code> — {esc(clip(spec.describe(lang), 70))}")
        rows.append((f"{s['prefix']}{cid}", f"copy:{s['prefix']}{cid} "))
    grid_rows = [rows[i:i + 3] for i in range(0, len(rows), 3)]
    grid_rows += [[(t("💤 AFK вкл/выкл", "💤 AFK yoq/o'ch"), "qk:afk"), (t("⏸ Пауза автоматики", "⏸ Avtomatika pauzasi"), "qk:pause")],
                  [(t("🎞 Студия анимаций", "🎞 Animatsiya studiyasi"), "qk:anim"), (t("⌨️ Все команды", "⌨️ Barcha buyruqlar"), "m:commands")],
                  [(t("⭐ Изменить избранное", "⭐ Sevimlilarni o'zgartirish"), "qk:fav"), (t("🏠 Меню", "🏠 Menyu"), "m:home")]]
    return "\n".join(lines), kb(grid_rows)


@screen("mutes")
async def screen_mutes(app: Any, uid: int, s: dict[str, Any]) -> tuple[str, Any]:
    lang = s["lang"]
    t = _t(lang)
    tz = s.get("timezone") or app.config.timezone
    ms = await app.filters.mute_settings(uid, 0)
    lines = [t("🔕 <b>Mute Manager</b>", "🔕 <b>Mute Manager</b>"),
             t("Mute удаляет новые входящие сообщения выбранного чата (право «Удаление входящих»). Включается командой "
               "<code>{p}mute</code> в чате или из «💬 Мои чаты».", "Mute tanlangan chatdagi yangi kiruvchi xabarlarni o'chiradi "
               "(«Kiruvchilarni o'chirish» huquqi). Chatda <code>{p}mute</code> yoki «💬 Chatlarim» orqali yoqiladi.", p=s["prefix"]), ""]
    rows = []
    active = [r for r in await app.controls.active(uid) if r["module"] in ("mute", "nogif", "nomute")]
    if not active:
        lines.append(t("Сейчас нет активных фильтров.", "Hozir faol filtrlar yo'q."))
    for r in active[:10]:
        title = esc(clip(((await app.chats.get(uid, r["chat_id"])) or {}).get("title") or str(r["chat_id"]), 28))
        icon = {"mute": "🔕", "nogif": "🚫", "nomute": "🧹"}[r["module"]]
        until = fmt_dt(r["until_at"], tz, with_date=False) if r.get("until_at") else "∞"
        lines.append(f"{icon} {title} · {until} · " + t("удалено {d}", "o'chirildi {d}", d=r["state"].get("deleted", 0)))
        rows.append([(f"⏹ {icon} {clip(title, 22)}", f"mm:off:{r['module']}:{r['chat_id']}")])
    lines += ["", t("<b>Настройки по умолчанию</b>", "<b>Standart sozlamalar</b>"),
              t("Удалять: {x}", "O'chirish: {x}", x=", ".join(type_title(x, lang) for x in ms["types"])),
              t("Не удалять сообщения со словами: {w}", "Shu so'zli xabarlarni o'chirmaslik: {w}", w=esc(", ".join(ms["whitelist"])) or "—"),
              t("Подтверждение перед включением: {v}", "Yoqishdan oldin tasdiq: {v}", v=t("да", "ha") if not s.get("mute_confirmed") else t("нет", "yo'q")),
              t("Где показывать кнопки: {v}", "Tugmalar qayerda: {v}", v=t("в чате", "chatda") if s.get("controls_place") == "chat" else t("в личке", "shaxsiyda"))]
    type_btns = [(("✅ " if x in ms["types"] else "") + type_title(x, lang), f"mm:type:{x}") for x in ("all", "text", "media", "voice", "circle", "gif", "sticker")]
    rows += [type_btns[i:i + 4] for i in range(0, len(type_btns), 4)]
    rows += [[(t("📝 Слова-исключения", "📝 Istisno so'zlar"), "mm:wl"), (t("🔁 Спрашивать подтверждение", "🔁 Tasdiq so'rash"), "mm:confirm")],
             [(t("📍 Кнопки: в чате / в личке", "📍 Tugmalar: chatda / shaxsiyda"), "mm:place")],
             [(t("🏠 Меню", "🏠 Menyu"), "m:home")]]
    return "\n".join(lines), kb(rows)


@screen("protects")
async def screen_protects(app: Any, uid: int, s: dict[str, Any]) -> tuple[str, Any]:
    lang = s["lang"]
    t = _t(lang)
    lines = [t("🛡 <b>Protect Manager</b>", "🛡 <b>Protect Manager</b>"),
             t("В защищённых чатах всё, что отправляет Chat helper (автоответы, AI, медиа, команды), нельзя переслать или сохранить. "
               "Ваши обычные сообщения это не затрагивает, скриншоты Telegram не блокирует. Одно сообщение: <code>{p}g текст</code>.",
               "Himoyalangan chatlarda Chat helper yuboradigan hamma narsani uzatib yoki saqlab bo'lmaydi. Oddiy xabarlaringizga ta'sir "
               "qilmaydi, Telegram skrinshotlarni bloklamaydi. Bitta xabar: <code>{p}g matn</code>.", p=s["prefix"]), ""]
    rows = []
    active = [r for r in await app.controls.active(uid, module="protect")]
    if not active:
        lines.append(t("Нет защищённых чатов. Включить: <code>{p}protect</code> в чате.", "Himoyalangan chatlar yo'q. Yoqish: chatda <code>{p}protect</code>.",
                       p=s["prefix"]))
    for r in active[:12]:
        title = esc(clip(((await app.chats.get(uid, r["chat_id"])) or {}).get("title") or str(r["chat_id"]), 28))
        lines.append(f"🛡 {title}")
        rows.append([(f"🔓 {clip(title, 26)}", f"pp:off:{r['chat_id']}")])
    rows.append([(t("🏠 Меню", "🏠 Menyu"), "m:home")])
    return "\n".join(lines), kb(rows)


@screen("texttools")
async def screen_texttools(app: Any, uid: int, s: dict[str, Any]) -> tuple[str, Any]:
    lang = s["lang"]
    t = _t(lang)
    lines = [t("📝 <b>Text Tools</b>", "📝 <b>Matn vositalari</b>"),
             t("Работают в любом чате и здесь. Нажмите, чтобы скопировать пример.", "Istalgan chatda va shu yerda ishlaydi. Misolni nusxalash uchun bosing."), ""]
    btns = []
    for cid, example in TEXT_TOOLS:
        spec = app.registry.commands.get(cid)
        if spec is None:
            continue
        cmd = f"{s['prefix']}{cid} {example}".strip()
        lines.append(f"<code>{esc(cmd)}</code> — {esc(clip(spec.describe(lang), 60))}")
        btns.append((f"{s['prefix']}{cid}", f"copy:{cmd}"))
    rows = [btns[i:i + 4] for i in range(0, len(btns), 4)]
    rows.append([(t("⌨️ Все команды", "⌨️ Barcha buyruqlar"), "cmd:cat:text:0"), (t("🏠 Меню", "🏠 Menyu"), "m:home")])
    return "\n".join(lines), kb(rows)


@screen("reminders")
async def screen_reminders(app: Any, uid: int, s: dict[str, Any]) -> tuple[str, Any]:
    lang = s["lang"]
    t = _t(lang)
    tz = s.get("timezone") or app.config.timezone
    rows_db = await app.reminders.list(uid)
    lines = [t("⏰ <b>Напоминания</b>", "⏰ <b>Eslatmalar</b>"), ""]
    rows = []
    if not rows_db:
        lines.append(t("Нет активных напоминаний.", "Faol eslatmalar yo'q."))
    for r in rows_db[:12]:
        where = t("в чат", "chatga") if r["kind"] == "chat" else t("в личку", "shaxsiyga")
        lines.append(f"#{r['id']} · {fmt_dt(r['run_at'], tz)} · {where} · {esc(clip(r['text'], 40))}")
        rows.append([(f"🗑 #{r['id']} {clip(r['text'], 24)}", f"rm:del:{r['id']}")])
    lines += ["", t("В чате: <code>{p}remindf 1h текст</code> — напомнит прямо в чат.", "Chatda: <code>{p}remindf 1h matn</code> — chatning o'ziga eslatadi.",
                    p=s["prefix"])]
    rows.append([(t("➕ Новое напоминание", "➕ Yangi eslatma"), "rm:new")])
    rows.append([(t("🏠 Меню", "🏠 Menyu"), "m:home")])
    return "\n".join(lines), kb(rows)


# ---------------------------------------------------------------------------------------------------------------------
@router.callback_query(F.data.startswith(("dg:", "mm:", "pp:", "rm:", "qk:")))
async def cb_account(cb: CallbackQuery, state: FSMContext, app: Any) -> None:
    uid = await ensure_user(app, cb)
    s = await app.settings.all(uid)
    lang = s["lang"]
    t = _t(lang)
    parts = (cb.data or "").split(":")
    kind, action = parts[0], parts[1] if len(parts) > 1 else ""
    target = "home"
    if kind == "dg" and action in SCOPES:
        if await app.delegation.is_granted(uid, action):
            await app.delegation.revoke(uid, action)
        else:
            await app.delegation.grant(uid, action)
        target = "delegation"
    elif kind == "mm":
        target = "mutes"
        if action == "off" and len(parts) == 4 and parts[3].lstrip("-").isdigit():
            module, chat_id = parts[2], int(parts[3])
            if module == "mute":
                await set_mute(app, uid, chat_id, False)
            elif module in ("nogif", "nomute"):
                await app.controls.set(uid, chat_id, module, False)
                await refresh_cards(app, uid, chat_id, module)
        elif action == "type" and len(parts) == 3 and parts[2] in MUTE_TYPES:
            ms = await app.filters.mute_settings(uid, 0)
            x = parts[2]
            types = ["all"] if x == "all" else [y for y in ms["types"] if y != "all"]
            if x != "all":
                types = [y for y in types if y != x] if x in types else types + [x]
            await app.filters.set_mute_settings(uid, 0, types=types or ["all"])
        elif action == "confirm":
            await app.settings.set(uid, "mute_confirmed", not s.get("mute_confirmed"))
        elif action == "place":
            await app.settings.set(uid, "controls_place", "dm" if s.get("controls_place") == "chat" else "chat")
        elif action == "wl":
            await state.set_state(AC.whitelist)
            await cb.answer()
            await cb.message.answer(t("📝 Пришлите слова через запятую: сообщения с ними Mute не удалит (например: срочно, мама). «-» — очистить.",
                                      "📝 So'zlarni vergul bilan yuboring: ular bor xabarlarni Mute o'chirmaydi (masalan: shoshilinch, onam). «-» — tozalash."))
            return
    elif kind == "pp" and action == "off" and len(parts) == 3 and parts[2].lstrip("-").isdigit():
        await app.controls.set(uid, int(parts[2]), "protect", False)
        await refresh_cards(app, uid, int(parts[2]), "protect")
        target = "protects"
    elif kind == "rm":
        target = "reminders"
        if action == "del" and len(parts) == 3 and parts[2].isdigit():
            await app.reminders.cancel(uid, int(parts[2]))
        elif action == "new":
            await state.set_state(AC.reminder)
            await cb.answer()
            await cb.message.answer(t("⏰ Когда и о чём напомнить? Формат: <code>30m позвонить маме</code> или <code>2h отчёт</code>.",
                                      "⏰ Qachon va nima haqida eslatay? Format: <code>30m onamga qo'ng'iroq</code> yoki <code>2h hisobot</code>."))
            return
    elif kind == "qk":
        target = "quick"
        if action == "afk":
            if await app.afk.active(uid):
                await app.afk.disable(uid, reason="panel")
            else:
                await app.afk.enable(uid, None)
        elif action == "pause":
            await app.settings.set(uid, "automation_paused", not s.get("automation_paused"))
        elif action == "anim":
            from ..modules.animations import send_studio
            await cb.answer()
            await send_studio(app, uid)
            return
        elif action == "fav":
            await cb.answer(t("Избранное: отправьте «{p}fav команда1 команда2 …» боту", "Sevimlilar: botga «{p}fav buyruq1 buyruq2 …» yuboring",
                              p=s["prefix"]), show_alert=True)
            return
    await cb.answer("✅")
    await show(app, uid, target, cb.message, True)


@router.callback_query(F.data.startswith("dlg:"))
async def cb_delegated_profile(cb: CallbackQuery, app: Any) -> None:
    uid = await ensure_user(app, cb)
    parts = (cb.data or "").split(":")
    if len(parts) != 3 or not parts[2].isdigit():
        await cb.answer()
        return
    res = await app.delegation.decide_profile_change(uid, int(parts[2]), parts[1] == "ok")
    lang = (await app.settings.all(uid))["lang"]
    await cb.answer({"applied": tr(lang, "✅ Применено", "✅ Qo'llandi"), "rejected": tr(lang, "✖️ Отклонено", "✖️ Rad etildi")}.get(res, res),
                    show_alert=res not in ("applied", "rejected"))
    try:
        await cb.message.edit_reply_markup(reply_markup=None)
    except Exception:  # pragma: no cover
        pass


@router.message(AC.reminder, F.text)
async def st_reminder(message: Message, state: FSMContext, app: Any) -> None:
    uid = await ensure_user(app, message)
    s = await app.settings.all(uid)
    when, _, text = (message.text or "").strip().partition(" ")
    dur = parse_duration(when)
    if not dur or not text.strip():
        await message.answer(tr(s["lang"], "Формат: <code>30m текст</code>", "Format: <code>30m matn</code>"))
        return
    try:
        await app.reminders.create(uid, text.strip(), int(time.time()) + dur)
    except ValueError as e:
        await message.answer(esc(str(e)))
        return
    await state.clear()
    await show(app, uid, "reminders", message, False)


@router.message(AC.whitelist, F.text)
async def st_whitelist(message: Message, state: FSMContext, app: Any) -> None:
    uid = await ensure_user(app, message)
    txt = message.text.strip()
    words = [] if txt == "-" else [w.strip() for w in txt.split(",") if w.strip()]
    await app.filters.set_mute_settings(uid, 0, whitelist=words)
    await state.clear()
    await show(app, uid, "mutes", message, False)

