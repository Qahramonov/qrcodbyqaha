"""System & advanced commands: help, status, ping, timer, animations, reminders, templates, export, limits…"""
from __future__ import annotations

import asyncio
import json
import time
from typing import Any

from aiogram import F, Router
from aiogram.types import BufferedInputFile, CallbackQuery, FSInputFile

from .. import __version__
from ..business.rights import status_title
from ..commands.context import CommandContext, CommandError, UsageError
from ..commands.parser import split_pipe
from ..commands.registry import CATEGORIES, LIMITED_BY_TELEGRAM, registry
from ..core.logging import ring_handler
from ..core.timeutil import fmt_dt, human_duration, parse_duration
from ..keyboards import kb
from ..localization import on_off
from ..security.sanitize import clip, esc
from .autoreply import mode_title

router = Router(name="system_cmds")
SYS = dict(rate=(20, 60))


@registry.command("help", "system", aliases=["помощь", "h", "yordam", "start_help"], ru="Список команд по категориям или справка по команде",
                  uz="Buyruqlar ro'yxati yoki buyruq bo'yicha yordam", syntax=".help [команда]", examples=[".help", ".help speed"], sandbox_safe=True, **SYS)
async def cmd_help(ctx: CommandContext) -> None:
    pre = ctx.prefix
    if ctx.args:
        spec = ctx.app.registry.resolve(ctx.args[0].lstrip(pre).lstrip("./"))
        if spec is None:
            raise CommandError(ctx.t("Команда не найдена.", "Buyruq topilmadi."))
        d = spec.to_dict(ctx.lang, pre)
        lines = [f"<b>{esc(d['name'])}</b> — {esc(d['description'])}", f"<code>{esc(d['syntax'])}</code>"]
        if d["aliases"]:
            lines.append(ctx.t("Алиасы: ", "Taxalluslar: ") + esc(", ".join(d["aliases"])))
        lines += [f"• <code>{esc(e.replace('.', pre, 1))}</code>" for e in d["examples"][:3]]
        if d["notes"]:
            lines.append("ℹ️ " + esc(d["notes"]))
        await ctx.answer("\n".join(lines), private=ctx.is_business)
        return
    lines = [ctx.t("📖 <b>Chat helper — команды</b> (префикс <code>{p}</code>)", "📖 <b>Chat helper — buyruqlar</b> (prefiks <code>{p}</code>)", p=pre)]
    for cat, specs in ctx.app.registry.by_category().items():
        if not specs:
            continue
        emoji, ru, uz = CATEGORIES.get(cat, ("•", cat, cat))
        names = " ".join(f"{pre}{s.id}" for s in sorted(specs, key=lambda x: x.id))
        lines.append(f"\n{emoji} <b>{ctx.t(ru, uz)}</b>\n<code>{esc(names)}</code>")
    lines.append(ctx.t("\nПодробно: <code>{p}help команда</code> · меню: /menu", "\nBatafsil: <code>{p}help buyruq</code> · menyu: /menu", p=pre))
    await ctx.answer("\n".join(lines), private=ctx.is_business)


@registry.command("commands", "system", aliases=["команды", "buyruqlar", "cmds"], ru="Компактный список всех команд", uz="Barcha buyruqlarning qisqa ro'yxati",
                  syntax=".commands", examples=[".commands"], sandbox_safe=True, **SYS)
async def cmd_commands(ctx: CommandContext) -> None:
    names = sorted(ctx.app.registry.commands)
    await ctx.answer(ctx.t("⌨️ Команд: {n}\n", "⌨️ Buyruqlar: {n}\n", n=len(names)) + "<code>" + esc(" ".join(ctx.prefix + n for n in names)) + "</code>",
                     private=ctx.is_business)


@registry.command("menu", "system", aliases=["меню", "menyu"], ru="Открыть меню Chat helper (в личке с ботом)", uz="Chat helper menyusini ochish",
                  syntax=".menu", examples=[".menu"], **SYS)
async def cmd_menu(ctx: CommandContext) -> None:
    from ..handlers.panel import screen_home
    text, markup = await screen_home(ctx.app, ctx.user_id, ctx.settings)
    await ctx.app.sender.send_text(ctx.user_id, text, markup=markup)
    await ctx.cleanup_command(fallback_text="📋")


@registry.command("settings", "system", aliases=["настройки", "sozlamalar"], ru="Текущие настройки", uz="Joriy sozlamalar", syntax=".settings",
                  examples=[".settings"], sandbox_safe=True, **SYS)
async def cmd_settings(ctx: CommandContext) -> None:
    s = ctx.settings
    lines = [ctx.t("⚙️ <b>Настройки</b>", "⚙️ <b>Sozlamalar</b>"),
             f"🌐 {s['lang']} · {ctx.t('префикс', 'prefiks')} <code>{esc(s['prefix'])}</code> · 🕒 {esc(s['timezone'])}",
             f"💬 {mode_title(s['mode'], ctx.lang)}",
             f"⏸ {ctx.t('пауза автоматики', 'avtomatika pauzasi')}: {on_off(ctx.lang, s['automation_paused'])}",
             f"🧠 AI: {s['ai_style']} · {ctx.t('подтверждение', 'tasdiq')} {on_off(ctx.lang, s['ai_confirm'])}",
             f"🗑 {ctx.t('удалять команды', 'buyruqlarni o`chirish')}: {on_off(ctx.lang, s['delete_commands'])}",
             ctx.t("Изменить: /menu → Настройки или приложение Chat helper Control.", "O'zgartirish: /menu → Sozlamalar yoki Chat helper Control ilovasi.")]
    await ctx.answer("\n".join(lines), private=ctx.is_business)


@registry.command("status", "system", aliases=["статус", "holat"], ru="Статус подключения, режима и модулей", uz="Ulanish, rejim va modullar holati",
                  syntax=".status", examples=[".status"], **SYS)
async def cmd_status(ctx: CommandContext) -> None:
    app = ctx.app
    conn = ctx.conn or await app.connections.primary_for_user(ctx.user_id)
    afk = await app.afk.active(ctx.user_id)
    lines = [ctx.t("📡 <b>Статус Chat helper</b>", "📡 <b>Chat helper holati</b>"),
             "🔗 " + (status_title(conn.status, ctx.lang) if conn else ctx.t("не подключено", "ulanmagan")),
             "💬 " + mode_title(ctx.settings["mode"], ctx.lang),
             "💤 AFK: " + (human_duration(time.time() - afk["started_at"], ctx.lang) if afk else ctx.t("выкл.", "o'chiq")),
             f"🧠 AI: {'✅' if app.ai.available() else '—'} · 🎞 FFmpeg: {'✅' if app.health.ffmpeg_ok else '—'}",
             f"🎬 {ctx.t('очередь медиа', 'media navbati')}: {app.media.queue.status()['queued']}",
             f"💎 {ctx.plan.upper()} · ⏱ {human_duration(app.uptime, ctx.lang)}"]
    if app.runtime.emergency_stop:
        lines.append("🛑 EMERGENCY STOP")
    if app.runtime.paused_modules:
        lines.append("⏸ " + ", ".join(sorted(app.runtime.paused_modules)))
    await ctx.answer("\n".join(lines), private=ctx.is_business)


@registry.command("ping", "system", aliases=["пинг"], ru="Задержка до Telegram API и время отклика бота", uz="Telegram API kechikishi",
                  syntax=".ping", examples=[".ping"], **SYS)
async def cmd_ping(ctx: CommandContext) -> None:
    t0 = time.monotonic()
    tg = await ctx.app.health.check_telegram()
    api_ms = int((time.monotonic() - t0) * 1000)
    lag = ""
    if ctx.message is not None and ctx.message.date:
        lag = f" · {ctx.t('доставка', 'yetkazish')} ~{max(0, int(time.time() - ctx.message.date.timestamp()))} s"
    await ctx.answer(f"🏓 Pong! Telegram API: <b>{api_ms} ms</b>{'' if tg.get('ok') else ' ⚠️'}{lag}")


@registry.command("uptime", "system", aliases=["аптайм"], ru="Время работы backend", uz="Backend ishlash vaqti", syntax=".uptime", examples=[".uptime"],
                  sandbox_safe=True, **SYS)
async def cmd_uptime(ctx: CommandContext) -> None:
    await ctx.answer(f"⏱ {human_duration(ctx.app.uptime, ctx.lang, 3)} · v{__version__}")


@registry.command("about", "system", aliases=["оботе", "haqida"], ru="О Chat helper", uz="Chat helper haqida", syntax=".about", examples=[".about"],
                  sandbox_safe=True, **SYS)
async def cmd_about(ctx: CommandContext) -> None:
    await ctx.answer(ctx.t("✨ <b>Chat helper</b> v{v}\nTelegram Business-автоматизация: AFK, AI, автоответы, Media Studio, игры.\n"
                           "Работает через официальный Bot API (Telegram «Автоматизация чатов», Secretary Mode). Управление: Chat helper Control (Android).",
                           "✨ <b>Chat helper</b> v{v}\nTelegram Business avtomatlashtirish: AFK, AI, avtojavoblar, Media Studio, o'yinlar.\n"
                           "Rasmiy Bot API orqali ishlaydi. Boshqaruv: Chat helper Control (Android).", v=__version__), private=ctx.is_business)


@registry.command("logs", "system", aliases=["логи"], ru="Последние предупреждения и ошибки (только администратор)", uz="So'nggi xatolar (faqat admin)",
                  syntax=".logs [N]", examples=[".logs", ".logs 40"], admin_only=True, **SYS)
async def cmd_logs(ctx: CommandContext) -> None:
    n = int(ctx.args[0]) if ctx.args and ctx.args[0].isdigit() else 20
    rows = ring_handler.query(level="WARNING", limit=min(n, 60))
    text = "\n".join(f"{time.strftime('%H:%M:%S', time.localtime(r['ts']))} {r['level'][0]} {r['logger']}: {r['message']}" for r in reversed(rows)) or "—"
    await ctx.answer("<pre>" + esc(text[-3800:]) + "</pre>", private=True)


@registry.command("clear", "system", aliases=["очистить", "tozala"], ru="Очистить сохранённый AI-контекст и превью этого чата (all — всех чатов)",
                  uz="Ushbu chatning AI konteksti va ko'rinishlarini tozalash (all — barchasi)", syntax=".clear [all]", examples=[".clear", ".clear all"], **SYS)
async def cmd_clear(ctx: CommandContext) -> None:
    if ctx.parsed.first == "all":
        n = await ctx.app.ai.memory.clear_all(ctx.user_id)
        await ctx.app.chats.clear_previews(ctx.user_id)
    else:
        n = await ctx.app.ai.memory.clear_chat(ctx.user_id, ctx.chat_id)
        await ctx.app.db.execute("UPDATE chat_settings SET last_preview=NULL WHERE user_id=? AND chat_id=?", (ctx.user_id, ctx.chat_id))
    await ctx.answer(ctx.t("🧹 Очищено записей: {n}", "🧹 Tozalandi: {n}", n=n), private=True)


@registry.command("export", "system", aliases=["экспорт", "eksport"], ru="Экспорт ваших данных (JSON в личку)", uz="Ma'lumotlaringizni eksport (JSON shaxsiy chatga)",
                  syntax=".export", examples=[".export"], rate=(3, 3600))
async def cmd_export(ctx: CommandContext) -> None:
    data = await ctx.app.backups.export_user(ctx.user_id)
    blob = json.dumps(data, ensure_ascii=False, indent=1, default=str).encode()
    await ctx.app.bot.send_document(ctx.user_id, BufferedInputFile(blob, f"chat_helper_export_{ctx.user_id}.json"),
                                    caption=ctx.t("📦 Ваши данные", "📦 Ma'lumotlaringiz"))
    await ctx.app.audit.log("privacy.export", actor_id=ctx.user_id, target_type="user", target_id=ctx.user_id)
    await ctx.cleanup_command(fallback_text="📦")


_BACKUP_CONFIRM: dict[int, float] = {}


@registry.command("backup", "system", aliases=["бэкап", "zaxira"], ru="Резервная копия базы (супер-админ, с подтверждением); для остальных — экспорт данных",
                  uz="Bazaning zaxira nusxasi (super-admin, tasdiq bilan)", syntax=".backup", examples=[".backup"], rate=(3, 600))
async def cmd_backup(ctx: CommandContext) -> None:
    if not ctx.is_super:
        await cmd_export(ctx)
        return
    _BACKUP_CONFIRM[ctx.user_id] = time.time()
    await ctx.answer(ctx.t("🗄 Создать резервную копию базы и прислать файл сюда? Файл содержит данные всех пользователей — храните его безопасно.",
                           "🗄 Baza zaxira nusxasini yaratib, faylni shu yerga yuboraymi? Faylda barcha foydalanuvchilar ma'lumotlari bor."),
                     markup=kb([[("✅ " + ctx.t("Создать", "Yaratish"), "sysbk:ok"), ("✖️", "sysbk:no")]]), private=True)


@router.callback_query(F.data.startswith("sysbk:"))
async def cb_backup(cb: CallbackQuery, app: Any) -> None:
    uid = cb.from_user.id
    if await app.users.role(uid) != "super_admin" or time.time() - _BACKUP_CONFIRM.pop(uid, 0) > 300:
        await cb.answer("—")
        return
    if cb.data.endswith(":no"):
        await cb.answer("✖️")
        return
    await cb.answer("⏳")
    path = await app.backups.create("manual")
    await app.bot.send_document(uid, FSInputFile(path), caption=f"🗄 {path.name}")
    await app.audit.log("system.backup_downloaded", actor_id=uid, target_type="backup", target_id=path.name)


@registry.command("lang", "system", aliases=["язык", "til"], ru="Язык интерфейса: ru или uz", uz="Interfeys tili: ru yoki uz", syntax=".lang ru|uz",
                  examples=[".lang uz"], **SYS)
async def cmd_lang(ctx: CommandContext) -> None:
    lang = ctx.parsed.first
    if lang not in ("ru", "uz"):
        raise UsageError()
    await ctx.app.settings.set(ctx.user_id, "lang", lang)
    await ctx.app.users.set_language(ctx.user_id, lang)
    await ctx.answer("🇷🇺 Русский ✅" if lang == "ru" else "🇺🇿 O'zbekcha ✅", private=ctx.is_business)


@registry.command("theme", "system", aliases=["тема", "mavzu"], ru="Стиль сообщений бота: classic, minimal, fancy, emoji", uz="Bot xabarlari uslubi",
                  syntax=".theme classic|minimal|fancy|emoji", examples=[".theme fancy"], **SYS)
async def cmd_theme(ctx: CommandContext) -> None:
    t = ctx.parsed.first
    if t not in ("classic", "minimal", "fancy", "emoji"):
        raise UsageError()
    await ctx.app.settings.set(ctx.user_id, "msg_theme", t)
    await ctx.answer(f"🎨 {t} ✅", private=ctx.is_business)


@registry.command("privacy", "system", aliases=["приватность", "maxfiylik"], ru="Что хранится и как удалить данные", uz="Nima saqlanadi va qanday o'chirish",
                  syntax=".privacy", examples=[".privacy"], sandbox_safe=True, **SYS)
async def cmd_privacy(ctx: CommandContext) -> None:
    s = ctx.settings
    await ctx.answer(ctx.t("🔐 <b>Приватность</b>\n• История для AI: {h} (хранение {d} дн.)\n• Превью сообщений: {pv}\n• Долгая память: {m}\n"
                           "• Переписка целиком не хранится; администратор не видит ваши чаты.\n• {p}export — экспорт · /menu → Приватность — удаление.",
                           "🔐 <b>Maxfiylik</b>\n• AI uchun tarix: {h} ({d} kun)\n• Xabar ko'rinishi: {pv}\n• Uzoq xotira: {m}\n"
                           "• Yozishmalar to'liq saqlanmaydi; administrator chatlaringizni ko'rmaydi.\n• {p}export — eksport · /menu → Maxfiylik — o'chirish.",
                           h=on_off(ctx.lang, s["ai_store_history"]), d=s["history_retention_days"], pv=on_off(ctx.lang, s["store_previews"]),
                           m=on_off(ctx.lang, s["ai_long_memory"]), p=ctx.prefix), private=ctx.is_business)


@registry.command("limits", "system", aliases=["лимиты", "limitlar"], ru="Лимиты тарифа и использование сегодня", uz="Tarif limitlari va bugungi foydalanish",
                  syntax=".limits", examples=[".limits"], **SYS)
async def cmd_limits(ctx: CommandContext) -> None:
    app = ctx.app
    lim = await app.subs.limits(ctx.user_id)
    used_ai = await app.quotas.used(f"ai:{ctx.user_id}")
    used_media = await app.quotas.used(f"media:{ctx.user_id}")
    f = lambda v: "∞" if v == -1 else str(v)  # noqa: E731
    await ctx.answer(ctx.t("📏 <b>Лимиты ({p})</b>\n🧠 AI: {ua}/{la} в день\n🎬 Медиа: {um}/{lm} в день\n📦 Файл: до {mb} МБ\n💬 Правил: {r} · ⚙️ автоматизаций: {a}",
                           "📏 <b>Limitlar ({p})</b>\n🧠 AI: {ua}/{la} kuniga\n🎬 Media: {um}/{lm} kuniga\n📦 Fayl: {mb} MB gacha\n💬 Qoidalar: {r} · ⚙️ avtomatlashtirish: {a}",
                           p=ctx.plan.upper(), ua=used_ai, la=f(lim["ai_requests_day"]), um=used_media, lm=f(lim["media_jobs_day"]),
                           mb=app.config.media_max_input_mb, r=f(lim["autoreply_rules"]), a=f(lim["automation_rules"])), private=ctx.is_business)


@registry.command("stats", "system", aliases=["статистика", "statistika"], ru="Ваша статистика за сегодня и 7 дней", uz="Bugungi va 7 kunlik statistika",
                  syntax=".stats", examples=[".stats"], **SYS)
async def cmd_stats(ctx: CommandContext) -> None:
    from ..handlers.panel import screen_stats
    text, _ = await screen_stats(ctx.app, ctx.user_id, ctx.settings)
    await ctx.answer(text, private=ctx.is_business)


@registry.command("inbox", "system", aliases=["входящие", "kiruvchi"], ru="Smart Inbox: кто ждёт ответа (ai — с AI-приоритетами)",
                  uz="Smart Inbox: kim javob kutmoqda (ai — AI ustuvorliklari bilan)", syntax=".inbox [ai]", examples=[".inbox", ".inbox ai"], **SYS)
async def cmd_inbox(ctx: CommandContext) -> None:
    text = await ctx.app.inbox.digest_text(ctx.user_id, ctx.lang, use_ai=ctx.parsed.first == "ai")
    await ctx.answer(text, private=True)


@registry.command("support", "system", aliases=["поддержка", "yordam_so'rov"], ru="Написать администратору Chat helper", uz="Chat helper administratoriga yozish",
                  syntax=".support текст", examples=[".support Не работает .speed"], rate=(3, 3600))
async def cmd_support(ctx: CommandContext) -> None:
    if not ctx.raw:
        raise UsageError()
    await ctx.app.support_message(ctx.user_id, ctx.raw)
    await ctx.answer(ctx.t("✅ Отправлено администратору.", "✅ Administratorga yuborildi."), private=True)


@registry.command("timer", "system", aliases=["таймер", "taymer"],
                  ru="Сообщение, которое удалится через время (или ответом — удалить ваше сообщение). Не защищённые «исчезающие» сообщения",
                  uz="Vaqt o'tib o'chadigan xabar (yoki javob — xabaringizni o'chirish). Himoyalangan «yo'qoladigan» xabar emas",
                  syntax=".timer время [текст]", examples=[".timer 30s Секретный код 1234", ".timer 10m (ответом на своё сообщение)"],
                  where="business", rights=["can_reply"], status=LIMITED_BY_TELEGRAM, rate=(10, 60),
                  notes_ru="Удаляет только то, что разрешено Bot API: сообщения бота (право «Удалять сообщения бота») или ваши (право «Удалять все»). Собеседник может успеть сохранить содержимое.",
                  notes_uz="Faqat Bot API ruxsat bergan xabarlarni o'chiradi. Suhbatdosh mazmunni saqlab qolishi mumkin.")
async def cmd_timer(ctx: CommandContext) -> None:
    if not ctx.args:
        raise UsageError()
    dur = parse_duration(ctx.args[0])
    if not dur or not 5 <= dur <= 7 * 86400:
        raise UsageError(ctx.t("Время от 5 секунд до 7 дней, например 30s, 10m, 2h.", "Vaqt 5 soniyadan 7 kungacha, masalan 30s, 10m, 2h."))
    text = ctx.raw.split(None, 1)[1] if len(ctx.raw.split(None, 1)) > 1 else ""
    conn = ctx.conn
    run_at = int(time.time()) + dur
    if text:
        if not conn.can("can_delete_sent_messages") and not conn.can("can_delete_all_messages"):
            raise CommandError(ctx.t("🔐 Нужно право «Удалять сообщения» для бота.", "🔐 Botga «Xabarlarni o'chirish» huquqi kerak."))
        mid = await ctx.answer(f"⏳ {esc(text)}\n<i>🕒 {human_duration(dur, ctx.lang)}</i>")
        if mid:
            await ctx.app.scheduler.add(ctx.user_id, "timer_delete", {"conn": conn.id, "chat_id": ctx.chat_id, "ids": [mid]}, run_at)
        return
    if ctx.reply is None:
        raise UsageError()
    own = ctx.reply.from_user is not None and ctx.reply.from_user.id == ctx.user_id
    need = "can_delete_all_messages" if own and ctx.reply.sender_business_bot is None else "can_delete_sent_messages"
    if not conn.can(need) and not conn.can("can_delete_all_messages"):
        raise CommandError(ctx.t("🔐 Не хватает права на удаление этого сообщения.", "🔐 Bu xabarni o'chirish huquqi yetarli emas."))
    if not own and ctx.reply.sender_business_bot is None:
        raise CommandError(ctx.t("Можно ставить таймер только на свои сообщения.", "Faqat o'z xabarlaringizga taymer qo'yish mumkin."))
    await ctx.app.scheduler.add(ctx.user_id, "timer_delete", {"conn": conn.id, "chat_id": ctx.chat_id, "ids": [ctx.reply.message_id]}, run_at)
    await ctx.cleanup_command(fallback_text=f"⏳ {human_duration(dur, ctx.lang)}")
    if not ctx.command_deleted:
        await ctx.app.scheduler.add(ctx.user_id, "timer_delete", {"conn": conn.id, "chat_id": ctx.chat_id, "ids": [ctx.message.message_id]}, run_at)


ACTIONS = {"typing": "typing", "печать": "typing", "voice": "record_voice", "голос": "record_voice", "video": "record_video_note",
           "кружок": "record_video_note", "photo": "upload_photo", "фото": "upload_photo", "doc": "upload_document", "file": "upload_document",
           "location": "find_location", "sticker": "choose_sticker", "videofile": "upload_video"}
_ACTIVE_R: dict[tuple[int, int], asyncio.Task] = {}


@registry.command("r", "system", aliases=["печатает", "action"], ru="Показать собеседнику «печатает…/записывает…» до 60 с",
                  uz="Suhbatdoshga «yozmoqda…/yozib olmoqda…» ni 60 s gacha ko'rsatish",
                  syntax=".r [typing|voice|video|photo|doc|sticker] [секунды]", examples=[".r", ".r voice 20"], where="business", rights=["can_reply"], **SYS)
async def cmd_r(ctx: CommandContext) -> None:
    action, secs = "typing", 15
    for a in ctx.args:
        if a.lower() in ACTIONS:
            action = ACTIONS[a.lower()]
        elif a.isdigit():
            secs = max(3, min(int(a), 60))
    key = (ctx.user_id, ctx.chat_id)
    old = _ACTIVE_R.pop(key, None)
    if old:
        old.cancel()
    await ctx.cleanup_command()

    async def loop():
        end = time.monotonic() + secs
        while time.monotonic() < end:
            await ctx.app.sender.action(ctx.chat_id, action, bc_id=ctx.bc_id)
            await asyncio.sleep(4.5)
        _ACTIVE_R.pop(key, None)
    _ACTIVE_R[key] = asyncio.create_task(loop())


@registry.command("a", "system", aliases=["анимация", "typewriter"], ru="Текст «печатается» анимацией (до 8 кадров, безопасно для лимитов)",
                  uz="Matn animatsiya bilan «yoziladi» (8 kadrgacha)", syntax=".a текст", examples=[".a Привет! Как дела?"], where="business",
                  rights=["can_reply"], rate=(5, 60))
async def cmd_a(ctx: CommandContext) -> None:
    text = ctx.raw.strip()
    if not text or len(text) > 500:
        raise UsageError()
    frames = 8 if len(text) > 16 else max(2, len(text) // 2)
    step = max(1, len(text) // frames)
    for i in range(step, len(text), step):
        res = await ctx.app.sender.edit_text(ctx.chat_id, ctx.message.message_id, esc(text[:i]) + "▌", bc_id=ctx.bc_id)
        if not res.ok:
            break
        await asyncio.sleep(0.9)
    await ctx.app.sender.edit_text(ctx.chat_id, ctx.message.message_id, esc(text), bc_id=ctx.bc_id)


@registry.command("remind", "system", aliases=["напомни", "eslat"], ru="Напоминание вам в личку через время", uz="Vaqt o'tib shaxsiy chatga eslatma",
                  syntax=".remind время текст", examples=[".remind 30m позвонить маме", ".remind 2h проверить почту"], rate=(10, 60))
async def cmd_remind(ctx: CommandContext) -> None:
    if len(ctx.args) < 2:
        raise UsageError()
    dur = parse_duration(ctx.args[0])
    if not dur or not 30 <= dur <= 30 * 86400:
        raise UsageError()
    text = ctx.raw.split(None, 1)[1]
    run_at = int(time.time()) + dur
    await ctx.app.scheduler.add(ctx.user_id, "reminder", {"text": text[:1000], "chat_id": ctx.chat_id if ctx.is_business else None}, run_at)
    tz_name = ctx.settings.get("timezone") or ctx.app.config.timezone
    await ctx.answer(ctx.t("⏰ Напомню в {t}", "⏰ {t} da eslataman", t=fmt_dt(run_at, tz_name)), private=True)


@registry.command("tpl", "autoreply", aliases=["шаблон", "template", "shablon"], ru="Шаблоны ответов: save имя | текст, имя (вставить), list, del",
                  uz="Javob shablonlari: save nom | matn, nom (qo'yish), list, del", syntax=".tpl save имя | текст · .tpl имя · .tpl list · .tpl del имя",
                  examples=[".tpl save прайс | Наш прайс: …", ".tpl прайс"], **SYS)
async def cmd_tpl(ctx: CommandContext) -> None:
    db = ctx.app.db
    sub = ctx.parsed.first
    if sub in ("", "list", "список"):
        rows = await db.fetchall("SELECT name, text FROM reply_templates WHERE user_id=? ORDER BY name", (ctx.user_id,))
        body = "\n".join(f"• <b>{esc(r['name'])}</b>: {esc(clip(r['text'], 60))}" for r in rows) or ctx.t("Шаблонов нет.", "Shablonlar yo'q.")
        await ctx.answer("📑 " + body, private=ctx.is_business)
        return
    if sub in ("save", "сохранить", "add"):
        parts = split_pipe(ctx.raw.split(None, 1)[1] if len(ctx.raw.split(None, 1)) > 1 else "")
        if len(parts) < 2 or not parts[0] or not parts[1]:
            raise UsageError()
        n = await db.fetchval("SELECT COUNT(*) FROM reply_templates WHERE user_id=?", (ctx.user_id,), 0)
        if n >= 100:
            raise CommandError(ctx.t("Максимум 100 шаблонов.", "Maksimum 100 shablon."))
        await db.execute("INSERT INTO reply_templates(user_id, name, text, created_at) VALUES (?,?,?,?) ON CONFLICT(user_id, name) DO UPDATE SET text=excluded.text",
                         (ctx.user_id, parts[0][:40].lower(), "|".join(parts[1:])[:3000], int(time.time())))
        await ctx.answer("✅", private=ctx.is_business)
        return
    if sub in ("del", "удалить"):
        name = ctx.raw.split(None, 1)[1].strip().lower() if len(ctx.raw.split(None, 1)) > 1 else ""
        n = await db.rowcount("DELETE FROM reply_templates WHERE user_id=? AND name=?", (ctx.user_id, name))
        await ctx.answer("🗑" if n else "—", private=ctx.is_business)
        return
    row = await db.fetchone("SELECT text FROM reply_templates WHERE user_id=? AND name=?", (ctx.user_id, ctx.raw.strip().lower()))
    if not row:
        raise CommandError(ctx.t("Шаблон не найден.", "Shablon topilmadi."))
    await ctx.answer(esc(row["text"]))
