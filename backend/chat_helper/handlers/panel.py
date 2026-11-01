"""Telegram user panel (private chat with Chat helper): inline menus, settings, FSM inputs."""
from __future__ import annotations

import json
import logging
import time
from typing import Any

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandObject, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from ..business.rights import inspect, status_title
from ..commands.registry import CATEGORIES, PLAN_RANK
from ..core.context import AppContext
from ..core.timeutil import fmt_dt, human_duration
from ..keyboards import grid, kb, nav, paginate, pager, toggle
from ..localization import on_off, p, tr
from ..modules.afk import render_afk
from ..modules.autoreply import mode_title
from ..security.sanitize import clip, esc
from ..services.settings import MODES, MSG_THEMES, STYLES
from .ui import PanelGate, access, ensure_user, register_screen, render, show

log = logging.getLogger(__name__)
router = Router(name="panel")
router.message.filter(F.chat.type == "private")
router.callback_query.filter(F.message.chat.type == "private")
router.message.middleware(PanelGate())
router.callback_query.middleware(PanelGate())

TIMEZONES = ["Asia/Tashkent", "Asia/Samarkand", "Europe/Moscow", "Asia/Almaty", "Europe/Kyiv", "Asia/Dubai", "Europe/Istanbul", "UTC"]
PREFIXES = [".", "!", "-", ","]


class PS(StatesGroup):
    afk_reason = State()
    rule_keyword = State()
    rule_response = State()
    welcome_text = State()
    profile_name = State()
    profile_bio = State()
    profile_avatar = State()
    promo = State()
    support = State()
    playground = State()
    broadcast_text = State()


# ======================================================================================
# screens
# ======================================================================================

async def screen_home(app: AppContext, uid: int, s: dict[str, Any]) -> tuple[str, Any]:
    lang = s["lang"]
    conn = await app.connections.primary_for_user(uid)
    afk = await app.afk.active(uid)
    plan = await app.subs.plan_of(uid)
    role = await app.users.role(uid)
    user = await app.users.get(uid) or {}
    name = esc(user.get("first_name") or "")
    lines = [tr(lang, "✨ <b>Chat helper</b> — ваш помощник в Telegram", "✨ <b>Chat helper</b> — Telegram'dagi yordamchingiz"), ""]
    lines.append(tr(lang, "👋 Привет, {n}!", "👋 Salom, {n}!", n=name or "👤"))
    lines.append(tr(lang, "🔗 Бизнес-подключение: {s}", "🔗 Biznes ulanish: {s}",
                    s=status_title(conn.status, lang) if conn else tr(lang, "⚪️ не подключено", "⚪️ ulanmagan")))
    lines.append(tr(lang, "💬 Режим: {m}", "💬 Rejim: {m}", m=mode_title(s["mode"], lang)))
    if afk:
        lines.append(tr(lang, "💤 AFK: {d}", "💤 AFK: {d}", d=human_duration(time.time() - afk["started_at"], lang)))
    if s.get("automation_paused"):
        lines.append(tr(lang, "⏸ Автоматизация на паузе", "⏸ Avtomatlashtirish to'xtatilgan"))
    lines.append(tr(lang, "💎 Тариф: {p}", "💎 Tarif: {p}", p=plan.upper()))
    if app.runtime.emergency_stop:
        lines.append(p(lang, "emergency"))
    items = [
        (tr(lang, "🔗 Подключить аккаунт", "🔗 Akkauntni ulash"), "m:connect"),
        (tr(lang, "🧠 AI Assistant", "🧠 AI yordamchi"), "m:ai"),
        (tr(lang, "💬 Автоответчик", "💬 Avtojavob"), "m:autoreply"),
        ("💤 AFK", "m:afk"),
        ("🎬 Media Studio", "m:media"),
        (tr(lang, "🎮 Игры", "🎮 O'yinlar"), "m:games"),
        (tr(lang, "⌨️ Команды", "⌨️ Buyruqlar"), "m:commands"),
        (tr(lang, "👤 Профиль", "👤 Profil"), "m:profile"),
        (tr(lang, "📊 Статистика", "📊 Statistika"), "m:stats"),
        (tr(lang, "🔐 Приватность", "🔐 Maxfiylik"), "m:privacy"),
        (tr(lang, "💎 Подписка", "💎 Obuna"), "m:sub"),
        (tr(lang, "⚙️ Настройки", "⚙️ Sozlamalar"), "m:settings"),
        (tr(lang, "📱 Приложение", "📱 Ilova"), "m:app"),
        (tr(lang, "❓ Помощь", "❓ Yordam"), "m:help"),
    ]
    rows = grid(items, 2)
    if role == "super_admin":
        rows.append([(tr(lang, "🛡 Администрирование", "🛡 Boshqaruv"), "m:admin")])
    return "\n".join(lines), kb(rows)


async def screen_inspector(app: AppContext, uid: int, s: dict[str, Any], idx: int) -> tuple[str, Any]:
    lang = s["lang"]
    conns = await app.connections.for_user(uid)
    if idx >= len(conns):
        from .onboarding import screen_connect
        return await screen_connect(app, uid, s)
    c = conns[idx]
    rep = inspect(c.rights, c.is_enabled, lang, c.paused)
    lines = [tr(lang, "🔍 <b>Permission Inspector</b>", "🔍 <b>Huquqlar tekshiruvi</b>"), rep["status_title"], ""]
    for cap in rep["capabilities"]:
        mark = "✅" if cap["available"] else "❌"
        extra = "" if cap["available"] else " — " + ", ".join(cap["missing_titles"])
        lines.append(f"{mark} {cap['description']}{esc(extra)}")
    lines.append("")
    lines += ["ℹ️ " + esc(a) for a in rep["advice"]]
    return "\n".join(lines), kb([nav(lang, "m:connect")])


async def screen_ai(app: AppContext, uid: int, s: dict[str, Any]) -> tuple[str, Any]:
    lang = s["lang"]
    usage = await app.ai.usage_summary(uid)
    provs = [p_["name"] for p_ in app.ai.providers_status() if p_["configured"]]
    lines = [tr(lang, "🧠 <b>AI Assistant</b>", "🧠 <b>AI yordamchi</b>"), "",
             tr(lang, "Провайдеры: {p}", "Provayderlar: {p}", p=", ".join(provs) if provs else tr(lang, "не настроены", "sozlanmagan")),
             tr(lang, "Стиль: {s}", "Uslub: {s}", s=s["ai_style"]),
             tr(lang, "Сегодня: {r} запросов · ${c}", "Bugun: {r} so'rov · ${c}", r=usage["today_requests"], c=f"{usage['today_cost']:.4f}"),
             tr(lang, "Лимит: {l}/день", "Limit: {l}/kun", l=usage["daily_limit"] if usage["daily_limit"] is not None else "∞"), "",
             tr(lang, "Пишите мне любой вопрос — отвечу как ассистент. В чатах: <code>{p}gpt вопрос</code>",
                "Menga istalgan savolni yozing — yordamchi sifatida javob beraman. Chatlarda: <code>{p}gpt savol</code>", p=s["prefix"])]
    rows = [
        [toggle(tr(lang, "AI-автоответ", "AI-avtojavob"), s["mode"] in ("ai", "hybrid"), "mode:" + ("manual" if s["mode"] in ("ai", "hybrid") else "ai")),
         toggle(tr(lang, "Гибрид", "Gibrid"), s["mode"] == "hybrid", "mode:hybrid")],
        [toggle(tr(lang, "Подтверждать ответы", "Javoblarni tasdiqlash"), s["ai_confirm"], "tg:ai_confirm")],
        [toggle(tr(lang, "Долгая память", "Uzoq xotira"), s["ai_long_memory"], "tg:ai_long_memory"),
         toggle(tr(lang, "История", "Tarix"), s["ai_store_history"], "tg:ai_store_history")],
        [toggle(tr(lang, "Расшифровка голосовых", "Ovozlarni matnga"), s["ai_auto_transcribe"], "tg:ai_auto_transcribe")],
        [toggle(tr(lang, "Дневная сводка", "Kunlik xulosa"), s["ai_daily_summary"], "tg:ai_daily_summary"),
         toggle(tr(lang, "Приоритеты", "Ustuvorlik"), s["ai_priority_detection"], "tg:ai_priority_detection")],
        [(f"{'▶️ ' if st == s['ai_style'] else ''}{st}", f"ai:style:{st}") for st in STYLES[:4]],
        [(f"{'▶️ ' if st == s['ai_style'] else ''}{st}", f"ai:style:{st}") for st in STYLES[4:]],
        [(tr(lang, "🧪 Playground", "🧪 Playground"), "ai:pg"), (tr(lang, "🗂 Память", "🗂 Xotira"), "ai:mem")],
        [(tr(lang, "🧹 Очистить память", "🧹 Xotirani tozalash"), "ai:clear")],
        nav(lang),
    ]
    return "\n".join(lines), kb(rows)


async def screen_ai_memory(app: AppContext, uid: int, s: dict[str, Any]) -> tuple[str, Any]:
    lang = s["lang"]
    facts = await app.ai.memory.list(uid, limit=30)
    lines = [tr(lang, "🗂 <b>Сохранённые факты</b>", "🗂 <b>Saqlangan faktlar</b>")]
    if not facts:
        lines.append(tr(lang, "Пусто. Добавить: <code>{p}remember факт</code>", "Bo'sh. Qo'shish: <code>{p}remember fakt</code>", p=s["prefix"]))
    for f in facts:
        lines.append(f"• #{f['id']} {esc(clip(f['content'], 120))}")
    if not s["ai_long_memory"]:
        lines += ["", tr(lang, "ℹ️ Долгая память выключена — новые факты не сохраняются автоматически.",
                         "ℹ️ Uzoq xotira o'chirilgan — yangi faktlar avtomatik saqlanmaydi.")]
    return "\n".join(lines), kb([[(tr(lang, "🧹 Очистить всё", "🧹 Hammasini tozalash"), "ai:clear")], nav(lang, "m:ai")])


async def screen_autoreply(app: AppContext, uid: int, s: dict[str, Any], page: int = 0) -> tuple[str, Any]:
    lang = s["lang"]
    rules = await app.autoreply.rules(uid)
    part, page, pages = paginate(rules, page, 6)
    lines = [tr(lang, "💬 <b>Автоответчик</b>", "💬 <b>Avtojavob</b>"), tr(lang, "Режим: {m}", "Rejim: {m}", m=mode_title(s["mode"], lang)), "",
             tr(lang, "Правила ({n}):", "Qoidalar ({n}):", n=len(rules))]
    rows: list[list[tuple[str, str]]] = []
    for m in MODES:
        pass
    rows += grid([(("▶️ " if m == s["mode"] else "") + mode_title(m, lang).split(" — ")[0], f"mode:{m}") for m in MODES], 2)
    for r in part:
        lines.append(f"{'🟢' if r['enabled'] else '⚪️'} #{r['id']} {esc(clip(r['pattern'] or r['trigger_type'], 30))} → {esc(clip(r['response'], 40))}")
        rows.append([(("⏸ " if r["enabled"] else "▶️ ") + f"#{r['id']}", f"ar:tog:{r['id']}"), (f"🗑 #{r['id']}", f"ar:del:{r['id']}")])
    if pager("ar:list", page, pages):
        rows.append(pager("ar:list", page, pages))
    rows.append([(tr(lang, "➕ Правило", "➕ Qoida"), "ar:add"), (tr(lang, "👋 Приветствие", "👋 Salomlashish"), "ar:welcome")])
    rows.append([toggle(tr(lang, "Приветствие", "Salomlashish"), s["welcome_enabled"], "tg:welcome_enabled"),
                 toggle(tr(lang, "Пауза", "Pauza"), s["automation_paused"], "tg:automation_paused")])
    lines += ["", tr(lang, "🕘 Рабочие часы: {a}–{b} (режим «Бизнес»). Изменить: <code>{p}work 09:00-18:00</code>",
                     "🕘 Ish vaqti: {a}–{b} («Biznes» rejimi). O'zgartirish: <code>{p}work 09:00-18:00</code>",
                     a=s["work_start"], b=s["work_end"], p=s["prefix"])]
    rows.append(nav(lang))
    return "\n".join(lines), kb(rows)


async def screen_afk(app: AppContext, uid: int, s: dict[str, Any]) -> tuple[str, Any]:
    lang = s["lang"]
    sess = await app.afk.active(uid)
    st = await app.afk.stats(uid)
    lines = ["💤 <b>AFK</b>", ""]
    if sess:
        lines.append(tr(lang, "Статус: 🟢 включён · {d}", "Holat: 🟢 yoqilgan · {d}", d=human_duration(time.time() - sess["started_at"], lang)))
        if sess.get("reason"):
            lines.append(tr(lang, "Причина: {r}", "Sabab: {r}", r=esc(sess["reason"])))
        if sess.get("ends_at"):
            lines.append(tr(lang, "До: {t}", "Gacha: {t}", t=fmt_dt(sess["ends_at"], s["timezone"])))
        lines.append(tr(lang, "Сообщений: {m} · ответов: {r}", "Xabarlar: {m} · javoblar: {r}", m=sess["messages_received"], r=sess["replies_sent"]))
    else:
        lines.append(tr(lang, "Статус: ⚪️ выключен", "Holat: ⚪️ o'chirilgan"))
    lines += ["", tr(lang, "Всего сессий: {n} · времени: {t}", "Jami sessiyalar: {n} · vaqt: {t}",
                     n=st.get("sessions", 0), t=human_duration(st.get("total_sec", 0) or 0, lang))]
    rows = []
    if sess:
        rows.append([(tr(lang, "✅ Выключить AFK", "✅ AFK'ni o'chirish"), "afk:off")])
    else:
        rows.append([(tr(lang, "💤 Включить", "💤 Yoqish"), "afk:on:0"), ("30m", "afk:on:1800"), ("1h", "afk:on:3600"), ("3h", "afk:on:10800")])
        rows.append([(tr(lang, "🌙 До утра", "🌙 Ertalabgacha"), "afk:sleep")])
    rows.append([(tr(lang, "✏️ Причина", "✏️ Sabab"), "afk:reason"), (tr(lang, "👁 Предпросмотр", "👁 Ko'rish"), "afk:preview")])
    rows.append([(("▶️ " if t == s["msg_theme"] else "") + t, f"afk:theme:{t}") for t in MSG_THEMES])
    rows.append([toggle(tr(lang, "Авто-выкл.", "Avto-o'chirish"), s["afk_auto_off"], "tg:afk_auto_off"),
                 toggle("AI", s["afk_ai"], "tg:afk_ai")])
    rows.append([toggle(tr(lang, "Сводка", "Xulosa"), s["afk_notify_summary"], "tg:afk_notify_summary"),
                 (tr(lang, "⏱ Интервал {m}м", "⏱ Interval {m}d", m=s["afk_cooldown_min"]), "afk:cd")])
    lines += ["", tr(lang, "Исключение для чата: напишите в нём <code>{p}ignore</code>, или выключите AFK для чата в приложении.",
                     "Chat uchun istisno: unda <code>{p}ignore</code> yozing yoki ilovada AFK'ni o'chiring.", p=s["prefix"])]
    rows.append(nav(lang))
    return "\n".join(lines), kb(rows)


async def screen_media(app: AppContext, uid: int, s: dict[str, Any]) -> tuple[str, Any]:
    lang = s["lang"]
    used = await app.quotas.used(f"media:{uid}")
    lim = await app.subs.limit(uid, "media_jobs_day")
    pre = s["prefix"]
    lines = ["🎬 <b>Media Studio</b>", "",
             tr(lang, "Ответьте командой на медиа в любом чате (или пришлите медиа мне):", "Istalgan chatda mediaga buyruq bilan javob bering (yoki menga yuboring):"),
             f"<code>{pre}reverse</code> · <code>{pre}speed 2</code> · <code>{pre}ld 25</code> · <code>{pre}ramka gold</code>",
             f"<code>{pre}meme up ВЕРХ | down НИЗ</code> · <code>{pre}blur</code> · <code>{pre}circle</code> · <code>{pre}gif</code>",
             f"<code>{pre}mp3</code> · <code>{pre}voice</code> · <code>{pre}sticker</code> · <code>{pre}trim 0:05 0:15</code>", "",
             tr(lang, "FFmpeg: {f}", "FFmpeg: {f}", f="✅" if app.health.ffmpeg_ok else "❌ pkg install ffmpeg"),
             tr(lang, "Сегодня: {u}/{l} задач · макс. {mb} МБ", "Bugun: {u}/{l} vazifa · maks. {mb} MB",
                u=used, l=lim if lim is not None else "∞", mb=app.config.media_max_input_mb)]
    rows = [[toggle(tr(lang, "Модуль включён", "Modul yoqilgan"), s["media_enabled"], "tg:media_enabled")],
            [toggle(tr(lang, "Удалять команды из чата", "Buyruqlarni chatdan o'chirish"), s["delete_commands"], "tg:delete_commands")],
            [(tr(lang, "📋 Все медиа-команды", "📋 Barcha media buyruqlar"), "cmd:cat:media:0")],
            nav(lang)]
    return "\n".join(lines), kb(rows)


async def screen_games(app: AppContext, uid: int, s: dict[str, Any]) -> tuple[str, Any]:
    lang = s["lang"]
    top = await app.games.leaderboard(uid, None, limit=5)
    lines = [tr(lang, "🎮 <b>Игры</b>", "🎮 <b>O'yinlar</b>"), "",
             tr(lang, "Запускайте в чате с собеседником или здесь со мной:", "Suhbatdosh bilan chatda yoki shu yerda men bilan o'ynang:"),
             " · ".join(f"<code>{s['prefix']}{g}</code>" for g in ("duel", "revo", "ttt", "rps", "quiz", "dice", "slot", "coin", "guess",
                                                                   "mathgame", "wordgame", "reaction", "challenge", "rd")), "",
             tr(lang, "🏆 Лидеры:", "🏆 Yetakchilar:")]
    if not top:
        lines.append(tr(lang, "пока нет результатов", "hozircha natijalar yo'q"))
    for i, r in enumerate(top, 1):
        lines.append(f"{i}. {esc(r['name'] or r['player_id'])} — {r['wins']}W/{r['losses']}L · {r['rating']}")
    lines += ["", tr(lang, "Все игры развлекательные, без ставок.", "Barcha o'yinlar ko'ngilochar, garovsiz.")]
    rows = [[toggle(tr(lang, "Игры включены", "O'yinlar yoqilgan"), s["games_enabled"], "tg:games_enabled")],
            [(tr(lang, "📋 Команды игр", "📋 O'yin buyruqlari"), "cmd:cat:games:0")], nav(lang)]
    return "\n".join(lines), kb(rows)


async def screen_commands(app: AppContext, uid: int, s: dict[str, Any]) -> tuple[str, Any]:
    lang = s["lang"]
    cats = app.registry.by_category()
    lines = [tr(lang, "⌨️ <b>Команды</b> ({n})", "⌨️ <b>Buyruqlar</b> ({n})", n=len(app.registry)),
             tr(lang, "Префикс: <code>{p}</code> · пишите в любом чате бизнес-аккаунта или здесь.",
                "Prefiks: <code>{p}</code> · biznes akkauntning istalgan chatida yoki shu yerda yozing.", p=s["prefix"])]
    items = [(f"{CATEGORIES[c][0]} {tr(lang, CATEGORIES[c][1], CATEGORIES[c][2])} ({len(v)})", f"cmd:cat:{c}:0")
             for c, v in cats.items() if v and c in CATEGORIES]
    rows = grid(items, 2)
    rows.append(nav(lang))
    return "\n".join(lines), kb(rows)


async def screen_cmd_cat(app: AppContext, uid: int, s: dict[str, Any], cat: str, page: int) -> tuple[str, Any]:
    lang = s["lang"]
    specs = sorted(app.registry.by_category().get(cat, []), key=lambda x: x.id)
    part, page, pages = paginate(specs, page, 8)
    disabled = set(s.get("disabled_commands") or [])
    emoji, ru, uz = CATEGORIES.get(cat, ("•", cat, cat))
    lines = [f"{emoji} <b>{tr(lang, ru, uz)}</b>", ""]
    rows = []
    for sp in part:
        mark = "⚪️" if sp.id in disabled else "🟢"
        lines.append(f"{mark} <code>{s['prefix']}{sp.id}</code> — {esc(sp.describe(lang))}")
        rows.append([(f"ℹ️ {s['prefix']}{sp.id}", f"cmd:info:{sp.id}")])
    rows = grid([r[0] for r in rows], 2)
    if pager(f"cmd:cat:{cat}", page, pages):
        rows.append(pager(f"cmd:cat:{cat}", page, pages))
    rows.append(nav(lang, "m:commands"))
    return "\n".join(lines), kb(rows)


async def screen_cmd_info(app: AppContext, uid: int, s: dict[str, Any], cid: str) -> tuple[str, Any]:
    lang = s["lang"]
    sp = app.registry.resolve(cid)
    if sp is None:
        return await screen_commands(app, uid, s)
    d = sp.to_dict(lang, s["prefix"])
    on = sp.id not in (s.get("disabled_commands") or [])
    lines = [f"<b>{esc(d['name'])}</b>", esc(d["description"]), "",
             tr(lang, "Синтаксис: <code>{x}</code>", "Sintaksis: <code>{x}</code>", x=esc(d["syntax"]))]
    if d["aliases"]:
        lines.append(tr(lang, "Алиасы: {a}", "Taxalluslar: {a}", a=esc(", ".join(d["aliases"]))))
    for ex in d["examples"][:3]:
        lines.append(f"• <code>{esc(ex.replace('.', s['prefix'], 1))}</code>")
    lines.append(tr(lang, "Тариф: {p} · статус: {st}", "Tarif: {p} · holat: {st}", p=d["min_plan"].upper(), st=d["status"]))
    if d["rights"]:
        lines.append(tr(lang, "Права: {r}", "Huquqlar: {r}", r=", ".join(d["rights"])))
    if d["notes"]:
        lines.append("ℹ️ " + esc(d["notes"]))
    rows = [[toggle(tr(lang, "Команда включена", "Buyruq yoqilgan"), on, f"cmd:tog:{sp.id}")], nav(lang, f"cmd:cat:{sp.category}:0")]
    return "\n".join(lines), kb(rows)


async def screen_profile(app: AppContext, uid: int, s: dict[str, Any]) -> tuple[str, Any]:
    lang = s["lang"]
    info = await app.profile.current(uid)
    conn = await app.connections.primary_for_user(uid)
    lines = [tr(lang, "👤 <b>Профиль бизнес-аккаунта</b>", "👤 <b>Biznes akkaunt profili</b>"), "",
             tr(lang, "Имя: {n}", "Ism: {n}", n=esc(info.get("first_name") or "—")),
             tr(lang, "Фамилия: {n}", "Familiya: {n}", n=esc(info.get("last_name") or "—")),
             tr(lang, "Био: {b}", "Bio: {b}", b=esc(info.get("bio") or "—")),
             tr(lang, "Часы: {c}", "Soat: {c}", c=on_off(lang, s["clock_enabled"]))]
    if conn is None:
        lines += ["", tr(lang, "⚠️ Подключите бизнес-аккаунт, чтобы менять профиль.", "⚠️ Profilni o'zgartirish uchun biznes akkauntni ulang.")]
    else:
        for r, t in (("can_edit_name", tr(lang, "имя", "ism")), ("can_edit_bio", "bio"), ("can_edit_profile_photo", tr(lang, "фото", "rasm"))):
            if not conn.can(r):
                lines.append(tr(lang, "🔒 Нет права менять {t}", "🔒 {t}ni o'zgartirish huquqi yo'q", t=t))
    rows = [[(tr(lang, "✏️ Имя", "✏️ Ism"), "pr:name"), ("✏️ Bio", "pr:bio"), (tr(lang, "🖼 Аватар", "🖼 Avatar"), "pr:avatar")],
            [(tr(lang, "💾 Бэкап", "💾 Zaxira"), "pr:backup"), (tr(lang, "♻️ Восстановить", "♻️ Tiklash"), "pr:restore"),
             (tr(lang, "🕘 История", "🕘 Tarix"), "pr:hist")],
            [toggle(tr(lang, "Часы в профиле", "Profildagi soat"), s["clock_enabled"], "tg:clock_enabled"),
             ((f"→ {s['clock_field']}"), "pr:clockfield")],
            nav(lang)]
    lines += ["", tr(lang, "ℹ️ Постоянный статус «онлайн» недоступен в Bot API — такую функцию мы не имитируем.",
                     "ℹ️ Doimiy «onlayn» holati Bot API'da mavjud emas — biz uni taqlid qilmaymiz.")]
    return "\n".join(lines), kb(rows)


async def screen_stats(app: AppContext, uid: int, s: dict[str, Any]) -> tuple[str, Any]:
    lang = s["lang"]
    from ..core.timeutil import today
    import datetime as dt
    d7 = (dt.datetime.now(dt.timezone.utc).date() - dt.timedelta(days=6)).isoformat()
    m = app.metrics
    vals = {}
    for k in ("messages_in", "messages_out", "auto_replies", "ai_requests", "media_jobs", "commands", "games_played"):
        vals[k] = (int(await m.total(k, uid, today())), int(await m.total(k, uid, d7)))
    labels = {"messages_in": ("📥 Входящие", "📥 Kiruvchi"), "messages_out": ("📤 Исходящие", "📤 Chiquvchi"),
              "auto_replies": ("🤖 Автоответы", "🤖 Avtojavoblar"), "ai_requests": ("🧠 AI-запросы", "🧠 AI so'rovlar"),
              "media_jobs": ("🎬 Медиа", "🎬 Media"), "commands": ("⌨️ Команды", "⌨️ Buyruqlar"), "games_played": ("🎮 Игры", "🎮 O'yinlar")}
    lines = [tr(lang, "📊 <b>Статистика</b>  (сегодня / 7 дней)", "📊 <b>Statistika</b>  (bugun / 7 kun)"), ""]
    for k, (a, b) in vals.items():
        lines.append(f"{tr(lang, *labels[k])}: <b>{a}</b> / {b}")
    chats = await app.chats.list(uid, page_size=1)
    unanswered = await app.inbox.unanswered(uid, 100)
    lines += ["", tr(lang, "💬 Чатов: {c} · ждут ответа: {u}", "💬 Chatlar: {c} · javob kutmoqda: {u}", c=chats["total"], u=len(unanswered))]
    return "\n".join(lines), kb([[(tr(lang, "📬 Smart Inbox", "📬 Smart Inbox"), "inbox")], nav(lang)])


async def screen_privacy(app: AppContext, uid: int, s: dict[str, Any]) -> tuple[str, Any]:
    lang = s["lang"]
    lines = [tr(lang, "🔐 <b>Приватность</b>", "🔐 <b>Maxfiylik</b>"), "",
             tr(lang, "• Мы не храним полную переписку. Для AI-контекста сохраняются последние сообщения чата (если включено) и удаляются через {d} дн.\n"
                      "• Администратор не видит содержимое ваших чатов.\n• Экспорт и удаление данных — в любой момент.",
                "• Biz to'liq yozishmalarni saqlamaymiz. AI konteksti uchun so'nggi xabarlar (yoqilgan bo'lsa) saqlanadi va {d} kundan keyin o'chiriladi.\n"
                "• Administrator chatlaringiz mazmunini ko'rmaydi.\n• Ma'lumotlarni eksport va o'chirish — istalgan vaqtda.",
                d=s["history_retention_days"])]
    rows = [[(("▶️ " if s["history_retention_days"] == d else "") + tr(lang, "{d} дн.", "{d} kun", d=d), f"pv:ret:{d}") for d in (0, 1, 7, 30)],
            [toggle(tr(lang, "История для AI", "AI uchun tarix"), s["ai_store_history"], "tg:ai_store_history"),
             toggle(tr(lang, "Превью", "Ko'rinish"), s["store_previews"], "tg:store_previews")],
            [toggle(tr(lang, "Долгая память (согласие)", "Uzoq xotira (rozilik)"), s["ai_long_memory"], "tg:ai_long_memory")],
            [(tr(lang, "📦 Экспорт данных", "📦 Ma'lumotlarni eksport"), "pv:export")],
            [(tr(lang, "🗑 Удалить все мои данные", "🗑 Barcha ma'lumotlarimni o'chirish"), "pv:del")],
            nav(lang)]
    return "\n".join(lines), kb(rows)


async def screen_sub(app: AppContext, uid: int, s: dict[str, Any]) -> tuple[str, Any]:
    lang = s["lang"]
    plan = await app.subs.plan_of(uid)
    sub = await app.subs.active_subscription(uid)
    limits = await app.subs.limits(uid)
    lines = [tr(lang, "💎 <b>Подписка</b>", "💎 <b>Obuna</b>"), tr(lang, "Тариф: <b>{p}</b>", "Tarif: <b>{p}</b>", p=plan.upper())]
    if sub and sub.get("expires_at"):
        lines.append(tr(lang, "Действует до {d}", "{d} gacha amal qiladi", d=fmt_dt(sub["expires_at"], s["timezone"])))
    lines.append("")
    lim_names = {"ai_requests_day": ("AI/день", "AI/kun"), "media_jobs_day": ("Медиа/день", "Media/kun"),
                 "autoreply_rules": ("Правил", "Qoidalar"), "automation_rules": ("Автоматизаций", "Avtomatlashtirish")}
    for k, (ru, uz) in lim_names.items():
        v = limits.get(k)
        lines.append(f"• {tr(lang, ru, uz)}: {'∞' if v == -1 else v}")
    lines.append("")
    rows = []
    for pl in app.subs.plans():
        if pl["id"] == "free":
            continue
        lines.append(f"<b>{esc(pl['name'])}</b> — {pl['price_stars']} ⭐️ / {pl['duration_days']} {tr(lang, 'дн.', 'kun')}: {esc(pl['description'] or '')}")
        if app.config.payments_enabled and pl["price_stars"] > 0 and PLAN_RANK.get(pl["id"], 0) >= PLAN_RANK.get(plan, 0):
            rows.append([(tr(lang, "⭐️ Купить {n}", "⭐️ {n} sotib olish", n=pl["name"]), f"sub:buy:{pl['id']}")])
    if not app.config.payments_enabled:
        lines += ["", tr(lang, "ℹ️ Оплата Stars пока не включена владельцем бота. Подписку может выдать администратор или промокод.",
                         "ℹ️ Stars orqali to'lov hali yoqilmagan. Obunani administrator yoki promokod orqali olish mumkin.")]
    rows.append([(tr(lang, "🎁 Промокод", "🎁 Promokod"), "sub:promo"), (tr(lang, "🆓 Пробный 3 дня", "🆓 3 kunlik sinov"), "sub:trial")])
    rows.append(nav(lang))
    return "\n".join(lines), kb(rows)


async def screen_settings(app: AppContext, uid: int, s: dict[str, Any]) -> tuple[str, Any]:
    lang = s["lang"]
    lines = [tr(lang, "⚙️ <b>Настройки</b>", "⚙️ <b>Sozlamalar</b>"), "",
             tr(lang, "Язык: {l} · префикс: <code>{p}</code> · часовой пояс: {tz}", "Til: {l} · prefiks: <code>{p}</code> · vaqt mintaqasi: {tz}",
                l=lang.upper(), p=s["prefix"], tz=s["timezone"]),
             tr(lang, "Пауза после вашего ответа: {m} мин", "Javobingizdan keyin pauza: {m} daq", m=s["owner_pause_minutes"])]
    rows = [[(("▶️ " if lang == "ru" else "") + "🇷🇺 Русский", "st:lang:ru"), (("▶️ " if lang == "uz" else "") + "🇺🇿 O'zbekcha", "st:lang:uz")],
            [(("▶️ " if s["prefix"] == x else "") + x, f"st:prefix:{x}") for x in PREFIXES],
            [(("▶️ " if s["owner_pause_minutes"] == m else "") + f"⏸{m}", f"st:pause:{m}") for m in (0, 5, 15, 30, 60)],
            [toggle(tr(lang, "Важные сообщения", "Muhim xabarlar"), s["notify_important"], "tg:notify_important"),
             toggle(tr(lang, "Новые чаты", "Yangi chatlar"), s["notify_new_chats"], "tg:notify_new_chats")],
            [toggle(tr(lang, "Отключение бота", "Bot uzilishi"), s["notify_disconnect"], "tg:notify_disconnect"),
             toggle(tr(lang, "Удалять команды", "Buyruqlarni o'chirish"), s["delete_commands"], "tg:delete_commands")],
            [(tr(lang, "🌍 Часовой пояс", "🌍 Vaqt mintaqasi"), "st:tzmenu")],
            [(tr(lang, "📱 Приложение и устройства", "📱 Ilova va qurilmalar"), "m:app")],
            nav(lang)]
    return "\n".join(lines), kb(rows)


async def screen_app(app: AppContext, uid: int, s: dict[str, Any]) -> tuple[str, Any]:
    lang = s["lang"]
    sessions = await app.auth.sessions(uid)
    lines = [tr(lang, "📱 <b>Chat helper Control</b>", "📱 <b>Chat helper Control</b>"), "",
             tr(lang, "Android-приложение для управления ботом. Установите APK, запустите backend в Termux и нажмите «Код для входа».",
                "Botni boshqarish uchun Android ilova. APK'ni o'rnating, Termux'da backend'ni ishga tushiring va «Kirish kodi» tugmasini bosing."),
             tr(lang, "Адрес сервера в приложении: <code>http://127.0.0.1:{port}</code>", "Ilovadagi server manzili: <code>http://127.0.0.1:{port}</code>",
                port=app.config.api_port), "",
             tr(lang, "Устройства ({n}):", "Qurilmalar ({n}):", n=len(sessions))]
    rows = [[(tr(lang, "🔑 Код для входа", "🔑 Kirish kodi"), "app:pair")]]
    for ss in sessions[:6]:
        lines.append(f"• {esc(ss['device_name'] or ss['device_id'])} · {fmt_dt(ss['last_used_at'] or ss['created_at'], s['timezone'])}")
        rows.append([(tr(lang, "🚫 Отключить {d}", "🚫 {d} ni uzish", d=clip(ss["device_name"] or ss["device_id"], 18)), f"app:rev:{ss['id']}")])
    rows.append(nav(lang))
    return "\n".join(lines), kb(rows)


async def screen_help(app: AppContext, uid: int, s: dict[str, Any]) -> tuple[str, Any]:
    lang = s["lang"]
    pre = s["prefix"]
    lines = [tr(lang, "❓ <b>Помощь</b>", "❓ <b>Yordam</b>"), "",
             tr(lang, "<b>Как это работает.</b> Chat helper подключается к вашему аккаунту через официальную функцию Telegram "
                      "«Автоматизация чатов» (Secretary Mode, Bot API). Бот видит личные чаты, которые вы выбрали, и может отвечать от вашего имени. "
                      "Пароли, коды входа и файлы сессии не нужны.",
                "<b>Qanday ishlaydi.</b> Chat helper akkauntingizga Telegram'ning rasmiy «Chat automation» funksiyasi (Secretary Mode, Bot API) "
                "orqali ulanadi. Bot siz tanlagan shaxsiy chatlarni ko'radi va sizning nomingizdan javob bera oladi. "
                "Parol, kirish kodi va sessiya fayllari kerak emas."), "",
             tr(lang, "<b>Команды</b> пишите прямо в чате: <code>{p}afk</code>, <code>{p}gpt вопрос</code>, ответом на голосовое — <code>{p}reverse</code>.",
                "<b>Buyruqlarni</b> to'g'ridan-to'g'ri chatda yozing: <code>{p}afk</code>, <code>{p}gpt savol</code>, ovozliga javoban — <code>{p}reverse</code>.", p=pre),
             tr(lang, "Команда заменяется результатом (или удаляется, если есть право удаления).", "Buyruq natija bilan almashtiriladi (yoki o'chirish huquqi bo'lsa o'chiriladi)."), "",
             tr(lang, "<b>Ограничения Telegram</b>: бот отвечает только в чатах, где собеседник писал за последние 24 часа; группы не поддерживаются; "
                      "статус «онлайн» изменить нельзя.",
                "<b>Telegram cheklovlari</b>: bot faqat suhbatdosh so'nggi 24 soatda yozgan chatlarda javob beradi; guruhlar qo'llab-quvvatlanmaydi; "
                "«onlayn» holatini o'zgartirib bo'lmaydi."), "",
             tr(lang, "Полный список: <code>{p}help</code> или раздел «Команды».", "To'liq ro'yxat: <code>{p}help</code> yoki «Buyruqlar» bo'limi.", p=pre)]
    rows = [[(tr(lang, "🔗 Подключение", "🔗 Ulanish"), "m:connect"), (tr(lang, "🖼 Инструкция", "🖼 Yo'riqnoma"), "ob:guide")],
            [(tr(lang, "✉️ Написать в поддержку", "✉️ Qo'llab-quvvatlashga yozish"), "help:support")], nav(lang)]
    return "\n".join(lines), kb(rows)


async def screen_admin(app: AppContext, uid: int, s: dict[str, Any]) -> tuple[str, Any]:
    lang = s["lang"]
    users = await app.users.count()
    conns = await app.connections.counts()
    subs = await app.subs.stats()
    lines = [tr(lang, "🛡 <b>Администрирование</b>", "🛡 <b>Boshqaruv</b>"), "",
             tr(lang, "Пользователей: {u}", "Foydalanuvchilar: {u}", u=users),
             tr(lang, "Активных подключений: {c}", "Faol ulanishlar: {c}", c=conns.get("active", 0)),
             tr(lang, "Подписки: {s}", "Obunalar: {s}", s=", ".join(f"{k}:{v}" for k, v in subs["active_by_plan"].items())),
             tr(lang, "Выручка: {r} ⭐️", "Daromad: {r} ⭐️", r=subs["revenue_stars"]),
             tr(lang, "Аптайм: {u}", "Ishlash vaqti: {u}", u=human_duration(app.uptime, lang)), "",
             tr(lang, "Полное управление — в приложении Chat helper Control.", "To'liq boshqaruv — Chat helper Control ilovasida.")]
    rows = [[toggle(tr(lang, "🛑 Аварийная остановка", "🛑 Favqulodda to'xtatish"), app.runtime.emergency_stop, "adm:es")],
            [toggle(tr(lang, "🛠 Обслуживание", "🛠 Texnik xizmat"), app.runtime.maintenance, "adm:mt")],
            [(tr(lang, "📣 Рассылка", "📣 Xabar tarqatish"), "adm:bc"), (tr(lang, "🩺 Диагностика", "🩺 Diagnostika"), "adm:health")],
            nav(lang)]
    return "\n".join(lines), kb(rows)


for _name, _fn in {
    "home": screen_home, "ai": screen_ai, "autoreply": screen_autoreply, "afk": screen_afk,
    "media": screen_media, "games": screen_games, "commands": screen_commands, "profile": screen_profile,
    "stats": screen_stats, "privacy": screen_privacy, "sub": screen_sub, "settings": screen_settings,
    "app": screen_app, "help": screen_help, "admin": screen_admin,
}.items():
    register_screen(_name, _fn, public=_name in ("help", "app"), admin=_name == "admin")


TOGGLE_SCREEN = {
    "ai_confirm": "ai", "ai_long_memory": "ai", "ai_store_history": "ai", "ai_auto_transcribe": "ai", "ai_daily_summary": "ai",
    "ai_priority_detection": "ai", "welcome_enabled": "autoreply", "automation_paused": "autoreply", "afk_auto_off": "afk",
    "afk_ai": "afk", "afk_notify_summary": "afk", "media_enabled": "media", "delete_commands": "settings", "games_enabled": "games",
    "store_previews": "privacy", "clock_enabled": "profile", "notify_important": "settings", "notify_new_chats": "settings",
    "notify_disconnect": "settings",
}


# ======================================================================================
# helpers
# ======================================================================================

_ensure_user = ensure_user
_render_custom = render


# ======================================================================================
# commands
# ======================================================================================

@router.message(CommandStart())
async def cmd_start(message: Message, command: CommandObject, state: FSMContext, app: AppContext) -> None:
    await state.clear()
    uid = await _ensure_user(app, message)
    arg = (command.args or "").strip()
    if arg.startswith("ref_") and arg[4:].isdigit() and int(arg[4:]) != uid:
        await app.db.execute("INSERT OR IGNORE INTO referrals(referred_id, referrer_id, created_at) VALUES (?,?,?)",
                             (uid, int(arg[4:]), int(time.time())))
    await app.users.set_bot_blocked(uid, False)
    await app.metrics.incr("bot_starts", uid)
    if arg == "pair":
        await _send_pair_code(app, uid, message)
        return
    await show(app, uid, "home", message, edit=False)


@router.message(Command("menu"))
async def cmd_menu(message: Message, state: FSMContext, app: AppContext) -> None:
    await state.clear()
    uid = await _ensure_user(app, message)
    await show(app, uid, "home", message, edit=False)


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext, app: AppContext) -> None:
    uid = await _ensure_user(app, message)
    await state.clear()
    s = await app.settings.all(uid)
    await message.answer(tr(s["lang"], "✖️ Отменено. Меню: /menu", "✖️ Bekor qilindi. Menyu: /menu"))


@router.message(Command("app"))
async def cmd_app(message: Message, app: AppContext) -> None:
    uid = await _ensure_user(app, message)
    await _send_pair_code(app, uid, message)


async def _send_pair_code(app: AppContext, uid: int, target: Message) -> None:
    s = await app.settings.all(uid)
    lang = s["lang"]
    from ..auth.service import AuthError
    try:
        code, expires = await app.auth.create_pairing_code(uid)
    except AuthError as e:
        await target.answer(tr(lang, "⏳ Слишком много кодов. Попробуйте позже ({s} с).", "⏳ Kodlar juda ko'p. Keyinroq urinib ko'ring ({s} s).",
                               s=e.retry_after or 60))
        return
    await target.answer(tr(lang, "🔑 <b>Код для Chat helper Control</b>\n\n<code>{c}</code>\n\nДействует {m} мин, одноразовый. "
                                 "Никому не пересылайте его — код даёт доступ к управлению вашим аккаунтом в Chat helper.",
                           "🔑 <b>Chat helper Control uchun kod</b>\n\n<code>{c}</code>\n\n{m} daqiqa amal qiladi, bir martalik. "
                           "Uni hech kimga yubormang — kod Chat helper'dagi akkauntingizni boshqarishga ruxsat beradi.",
                           c=code, m=max(1, (expires - int(time.time())) // 60)))


# ======================================================================================
# callbacks
# ======================================================================================

@router.callback_query(F.data == "noop")
async def cb_noop(cb: CallbackQuery) -> None:
    await cb.answer()


@router.callback_query(F.data.startswith("m:"))
async def cb_nav(cb: CallbackQuery, state: FSMContext, app: AppContext) -> None:
    await state.clear()
    uid = await _ensure_user(app, cb)
    screen = cb.data.split(":")[1]
    await cb.answer()
    await show(app, uid, screen, cb.message, True)


@router.callback_query(F.data.startswith("tg:"))
async def cb_toggle(cb: CallbackQuery, app: AppContext) -> None:
    uid = await _ensure_user(app, cb)
    key = cb.data[3:]
    if key not in TOGGLE_SCREEN:
        await cb.answer("?", show_alert=False)
        return
    cur = await app.settings.get(uid, key)
    if key == "ai_long_memory" and not cur:
        s = await app.settings.all(uid)
        await cb.answer(tr(s["lang"], "Вы даёте согласие хранить факты для AI. Отключить можно в любой момент.",
                           "Siz AI uchun faktlarni saqlashga rozilik berasiz. Istalgan vaqtda o'chirish mumkin."), show_alert=True)
    else:
        await cb.answer()
    await app.settings.set(uid, key, not cur)
    if key == "clock_enabled" and app.profile:
        await app.profile.on_clock_toggled(uid, not cur)
    await app.audit.log("settings.toggle", actor_id=uid, target_type="setting", target_id=key, value=not cur)
    await show(app, uid, TOGGLE_SCREEN[key], cb.message, True)


@router.callback_query(F.data.startswith("mode:"))
async def cb_mode(cb: CallbackQuery, app: AppContext) -> None:
    uid = await _ensure_user(app, cb)
    mode = cb.data.split(":")[1]
    s = await app.settings.all(uid)
    if mode not in MODES:
        await cb.answer()
        return
    if mode in ("ai", "hybrid") and not app.ai.available():
        await cb.answer(p(s["lang"], "requires_ai"), show_alert=True)
        return
    await app.autoreply.set_mode(uid, mode)
    await cb.answer(mode_title(mode, s["lang"]))
    origin = "ai" if "AI" in (cb.message.text or "")[:30] else "autoreply"
    await show(app, uid, origin, cb.message, True)


@router.callback_query(F.data.startswith("conn:"))
async def cb_conn(cb: CallbackQuery, app: AppContext) -> None:
    uid = await _ensure_user(app, cb)
    parts = cb.data.split(":")
    action = parts[1]
    conns = await app.connections.for_user(uid)
    s = await app.settings.all(uid)
    if action == "refresh":
        for c in conns:
            try:
                bc = await app.bot.get_business_connection(business_connection_id=c.id)
                await app.connections.upsert(bc.id, bc.user.id, bc.user_chat_id, bc.is_enabled, bc.rights)
            except Exception:
                await app.connections.mark_status(c.id, "reconnection_required")
        await cb.answer(p(s["lang"], "done"))
        await show(app, uid, "connect", cb.message, True)
        return
    idx = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0
    if idx >= len(conns):
        await cb.answer()
        return
    if action == "insp":
        await cb.answer()
        text, markup = await screen_inspector(app, uid, s, idx)
        await _render_custom(cb.message, text, markup)
        return
    if action in ("pause", "resume"):
        await app.connections.set_paused(conns[idx].id, uid, action == "pause")
        await app.audit.log(f"connection.{action}", actor_id=uid, target_type="connection", target_id=conns[idx].id)
        await cb.answer(p(s["lang"], "done"))
        await show(app, uid, "connect", cb.message, True)


@router.callback_query(F.data.startswith("afk:"))
async def cb_afk(cb: CallbackQuery, state: FSMContext, app: AppContext) -> None:
    uid = await _ensure_user(app, cb)
    s = await app.settings.all(uid)
    lang = s["lang"]
    parts = cb.data.split(":")
    action = parts[1]
    if action == "on":
        dur = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0
        await app.afk.enable(uid, None, dur or None)
        await cb.answer("💤")
    elif action == "off":
        await app.afk.disable(uid, reason="manual")
        await cb.answer("👋")
    elif action == "sleep":
        from ..core.timeutil import next_occurrence
        await app.afk.enable(uid, tr(lang, "Сон", "Uyqu"), kind="sleep", ends_at=next_occurrence(8, 0, s["timezone"]))
        await cb.answer("🌙")
    elif action == "theme" and len(parts) > 2 and parts[2] in MSG_THEMES:
        await app.settings.set(uid, "msg_theme", parts[2])
        await cb.answer(parts[2])
    elif action == "cd":
        steps = [5, 15, 30, 60, 180]
        cur = s["afk_cooldown_min"]
        nxt = next((x for x in steps if x > cur), steps[0])
        await app.settings.set(uid, "afk_cooldown_min", nxt)
        await cb.answer(f"{nxt} min")
    elif action == "reason":
        await cb.answer()
        await state.set_state(PS.afk_reason)
        await cb.message.answer(tr(lang, "✏️ Напишите причину отсутствия (или /cancel):", "✏️ Yo'qlik sababini yozing (yoki /cancel):"))
        return
    elif action == "preview":
        await cb.answer()
        user = await app.users.get(uid) or {}
        from ..core.timeutil import day_part
        sess = await app.afk.active(uid)
        text = render_afk(s["msg_theme"], lang, name=user.get("first_name") or "Owner", reason=(sess or {}).get("reason") or tr(lang, "Занят делами", "Band"),
                          away=int(time.time() - (sess or {}).get("started_at", time.time() - 8040)), until_ts=(sess or {}).get("ends_at"),
                          tz_name=s["timezone"], part=day_part(s["timezone"]), kind=(sess or {}).get("kind", "afk"))
        await cb.message.answer(tr(lang, "👁 Так увидят собеседники:", "👁 Suhbatdoshlar shunday ko'radi:") + "\n\n" + text)
        return
    await show(app, uid, "afk", cb.message, True)


@router.message(StateFilter(PS.afk_reason), F.text)
async def st_afk_reason(message: Message, state: FSMContext, app: AppContext) -> None:
    uid = await _ensure_user(app, message)
    await state.clear()
    await app.afk.enable(uid, message.text[:300])
    await show(app, uid, "afk", message, False)


@router.callback_query(F.data.startswith("ar:"))
async def cb_autoreply(cb: CallbackQuery, state: FSMContext, app: AppContext) -> None:
    uid = await _ensure_user(app, cb)
    s = await app.settings.all(uid)
    lang = s["lang"]
    parts = cb.data.split(":")
    action = parts[1]
    if action == "add":
        await cb.answer()
        await state.set_state(PS.rule_keyword)
        await cb.message.answer(tr(lang, "🔑 Ключевые слова через запятую (например: <i>цена, прайс, стоимость</i>) или /cancel:",
                                   "🔑 Kalit so'zlarni vergul bilan yozing (masalan: <i>narx, prays</i>) yoki /cancel:"))
        return
    if action == "welcome":
        await cb.answer()
        await state.set_state(PS.welcome_text)
        await cb.message.answer(tr(lang, "👋 Текст приветствия для новых собеседников. Можно {name}, {owner}, {time}. /cancel — отмена.",
                                   "👋 Yangi suhbatdoshlar uchun salomlashish matni. {name}, {owner}, {time} ishlatish mumkin. /cancel — bekor."))
        return
    if action in ("del", "tog") and len(parts) > 2 and parts[2].isdigit():
        rid = int(parts[2])
        if action == "del":
            ok = await app.autoreply.delete_rule(uid, rid)
        else:
            r = await app.autoreply.get_rule(uid, rid)
            ok = r is not None and await app.autoreply.update_rule(uid, rid, {"enabled": not r["enabled"]}) is not None
        await cb.answer(p(lang, "done") if ok else "—")
        await show(app, uid, "autoreply", cb.message, True)
        return
    if action == "list":
        await cb.answer()
        page = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0
        text, markup = await screen_autoreply(app, uid, s, page)
        await _render_custom(cb.message, text, markup)
        return
    await cb.answer()


@router.message(StateFilter(PS.rule_keyword), F.text)
async def st_rule_keyword(message: Message, state: FSMContext, app: AppContext) -> None:
    uid = await _ensure_user(app, message)
    s = await app.settings.all(uid)
    await state.update_data(keyword=message.text[:500])
    await state.set_state(PS.rule_response)
    await message.answer(tr(s["lang"], "💬 Теперь текст ответа:", "💬 Endi javob matnini yozing:"))


@router.message(StateFilter(PS.rule_response), F.text)
async def st_rule_response(message: Message, state: FSMContext, app: AppContext) -> None:
    uid = await _ensure_user(app, message)
    s = await app.settings.all(uid)
    data = await state.get_data()
    await state.clear()
    try:
        rule = await app.autoreply.add_rule(uid, {"trigger_type": "keyword", "pattern": data.get("keyword", ""),
                                                  "response": message.text, "cooldown_sec": s["autoreply_cooldown_sec"]})
        await message.answer(tr(s["lang"], "✅ Правило #{i} создано.", "✅ #{i} qoida yaratildi.", i=rule["id"]))
    except ValueError as e:
        await message.answer(f"⚠️ {esc(str(e))}")
    await show(app, uid, "autoreply", message, False)


@router.message(StateFilter(PS.welcome_text), F.text)
async def st_welcome(message: Message, state: FSMContext, app: AppContext) -> None:
    uid = await _ensure_user(app, message)
    await state.clear()
    await app.settings.update(uid, {"welcome_text": message.text[:1000], "welcome_enabled": True})
    await show(app, uid, "autoreply", message, False)


@router.callback_query(F.data.startswith("cmd:"))
async def cb_commands(cb: CallbackQuery, app: AppContext) -> None:
    uid = await _ensure_user(app, cb)
    s = await app.settings.all(uid)
    parts = cb.data.split(":")
    await cb.answer()
    if parts[1] == "cat" and len(parts) >= 3:
        page = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 0
        text, markup = await screen_cmd_cat(app, uid, s, parts[2], page)
    elif parts[1] == "info" and len(parts) >= 3:
        text, markup = await screen_cmd_info(app, uid, s, parts[2])
    elif parts[1] == "tog" and len(parts) >= 3:
        spec = app.registry.resolve(parts[2])
        if spec is None:
            return
        disabled = list(s.get("disabled_commands") or [])
        if spec.id in disabled:
            disabled.remove(spec.id)
        else:
            disabled.append(spec.id)
        await app.settings.set(uid, "disabled_commands", disabled)
        s = await app.settings.all(uid)
        text, markup = await screen_cmd_info(app, uid, s, spec.id)
    else:
        return
    await _render_custom(cb.message, text, markup)


@router.callback_query(F.data.startswith("ai:"))
async def cb_ai(cb: CallbackQuery, state: FSMContext, app: AppContext) -> None:
    uid = await _ensure_user(app, cb)
    s = await app.settings.all(uid)
    lang = s["lang"]
    parts = cb.data.split(":")
    action = parts[1]
    if action == "style" and len(parts) > 2 and parts[2] in STYLES:
        await app.settings.set(uid, "ai_style", parts[2])
        await cb.answer(parts[2])
        await show(app, uid, "ai", cb.message, True)
    elif action == "clear":
        n = await app.ai.memory.clear_all(uid)
        await cb.answer(tr(lang, "Удалено записей: {n}", "O'chirildi: {n}", n=n), show_alert=True)
        await show(app, uid, "ai", cb.message, True)
    elif action == "mem":
        await cb.answer()
        text, markup = await screen_ai_memory(app, uid, s)
        await _render_custom(cb.message, text, markup)
    elif action == "pg":
        await cb.answer()
        if not app.ai.available():
            await cb.message.answer(p(lang, "requires_ai"))
            return
        await state.set_state(PS.playground)
        await cb.message.answer(tr(lang, "🧪 <b>AI Playground</b>: пишите сообщения — я отвечу с вашими настройками, но никому ничего не отправлю. "
                                         "Сравнить модели: <code>/compare вопрос</code>. Выход: /cancel",
                                   "🧪 <b>AI Playground</b>: xabar yozing — sozlamalaringiz bilan javob beraman, hech kimga yubormayman. "
                                   "Modellarni solishtirish: <code>/compare savol</code>. Chiqish: /cancel"))
    else:
        await cb.answer()


@router.message(StateFilter(PS.playground), F.text)
async def st_playground(message: Message, app: AppContext) -> None:
    uid = await _ensure_user(app, message)
    s = await app.settings.all(uid)
    text = message.text or ""
    await app.sender.action(uid, "typing")
    try:
        if text.startswith("/compare"):
            q = text[len("/compare"):].strip()
            if not q:
                await message.answer(tr(s["lang"], "Напишите вопрос после /compare", "/compare dan keyin savol yozing"))
                return
            results = await app.ai.compare(uid, q, settings=s)
            out = []
            for r in results:
                head = f"<b>{esc(r['provider'])}/{esc(r['model'] or '')}</b> · {r.get('latency_ms', 0)} ms · ~{r.get('tokens', 0)} tok"
                out.append(head + "\n" + esc(r.get("text") or r.get("error") or ""))
            await message.answer("\n\n".join(out)[:4000] or "—")
            return
        res = await app.ai.playground(uid, text, settings=s)
        await message.answer(esc(res.text)[:3900] + f"\n\n<i>{esc(res.provider)}/{esc(res.model or '')} · {res.prompt_tokens}+{res.completion_tokens} tok · ${res.cost:.5f}</i>")
    except Exception as e:
        await message.answer(f"⚠️ {esc(str(e))[:300]}")


@router.callback_query(F.data.startswith("pr:"))
async def cb_profile(cb: CallbackQuery, state: FSMContext, app: AppContext) -> None:
    uid = await _ensure_user(app, cb)
    s = await app.settings.all(uid)
    lang = s["lang"]
    action = cb.data.split(":")[1]
    prompts = {
        "name": (PS.profile_name, tr(lang, "✏️ Новое имя. Формат: <i>Имя | Фамилия</i> (фамилия необязательна). /cancel",
                                     "✏️ Yangi ism. Format: <i>Ism | Familiya</i> (familiya ixtiyoriy). /cancel")),
        "bio": (PS.profile_bio, tr(lang, "✏️ Новое био (до 140 символов, «-» чтобы очистить). /cancel",
                                   "✏️ Yangi bio (140 belgigacha, tozalash uchun «-»). /cancel")),
        "avatar": (PS.profile_avatar, tr(lang, "🖼 Пришлите фото для аватара. /cancel", "🖼 Avatar uchun rasm yuboring. /cancel")),
    }
    if action in prompts:
        await cb.answer()
        st, txt = prompts[action]
        await state.set_state(st)
        await cb.message.answer(txt)
        return
    if action == "backup":
        res = await app.profile.backup(uid)
        await cb.answer(tr(lang, "💾 Сохранено", "💾 Saqlandi") if res else "—", show_alert=False)
        return
    if action == "restore":
        await cb.answer()
        await app.profile.restore_flow(uid, cb.message)
        return
    if action == "hist":
        await cb.answer()
        rows = await app.profile.history(uid, 15)
        lines = [tr(lang, "🕘 <b>История изменений профиля</b>", "🕘 <b>Profil o'zgarishlari tarixi</b>")]
        for r in rows:
            lines.append(f"• {fmt_dt(r['created_at'], s['timezone'])} {r['field']}: {esc(clip(r['old_value'] or '—', 30))} → {esc(clip(r['new_value'] or '—', 30))}")
        if len(rows) == 0:
            lines.append("—")
        await _render_custom(cb.message, "\n".join(lines), kb([nav(lang, "m:profile")]))
        return
    if action == "clockfield":
        new = "last_name" if s["clock_field"] == "bio" else "bio"
        await app.settings.set(uid, "clock_field", new)
        await cb.answer(new)
        await show(app, uid, "profile", cb.message, True)
        return
    if action in ("ok", "no"):
        await app.profile.confirm_callback(uid, cb, action == "ok")
        return
    await cb.answer()


@router.message(StateFilter(PS.profile_name), F.text)
async def st_profile_name(message: Message, state: FSMContext, app: AppContext) -> None:
    uid = await _ensure_user(app, message)
    await state.clear()
    parts = [x.strip() for x in message.text.split("|", 1)]
    await app.profile.propose(uid, "name", {"first_name": parts[0][:64], "last_name": parts[1][:64] if len(parts) > 1 else ""}, message)


@router.message(StateFilter(PS.profile_bio), F.text)
async def st_profile_bio(message: Message, state: FSMContext, app: AppContext) -> None:
    uid = await _ensure_user(app, message)
    await state.clear()
    bio = "" if message.text.strip() == "-" else message.text.strip()[:140]
    await app.profile.propose(uid, "bio", {"bio": bio}, message)


@router.message(StateFilter(PS.profile_avatar), F.photo)
async def st_profile_avatar(message: Message, state: FSMContext, app: AppContext) -> None:
    uid = await _ensure_user(app, message)
    await state.clear()
    await app.profile.propose(uid, "avatar", {"file_id": message.photo[-1].file_id}, message)


@router.callback_query(F.data.startswith("pv:"))
async def cb_privacy(cb: CallbackQuery, app: AppContext) -> None:
    uid = await _ensure_user(app, cb)
    s = await app.settings.all(uid)
    lang = s["lang"]
    parts = cb.data.split(":")
    action = parts[1]
    if action == "ret" and len(parts) > 2 and parts[2].isdigit():
        await app.settings.set(uid, "history_retention_days", int(parts[2]))
        await cb.answer(p(lang, "saved"))
        await show(app, uid, "privacy", cb.message, True)
    elif action == "export":
        await cb.answer()
        data = await app.backups.export_user(uid)
        blob = json.dumps(data, ensure_ascii=False, indent=1, default=str).encode()
        await cb.message.answer_document(BufferedInputFile(blob, filename=f"chat_helper_export_{uid}.json"),
                                         caption=tr(lang, "📦 Ваши данные в Chat helper", "📦 Chat helper'dagi ma'lumotlaringiz"))
        await app.audit.log("privacy.export", actor_id=uid, target_type="user", target_id=uid)
    elif action == "del":
        await cb.answer()
        await _render_custom(cb.message, tr(lang, "⚠️ <b>Удалить все ваши данные?</b>\nНастройки, правила, AI-память, историю, статистику и сессии приложения. "
                                                  "Бизнес-подключение нужно отключить в Telegram отдельно. Действие необратимо.",
                                            "⚠️ <b>Barcha ma'lumotlaringizni o'chirasizmi?</b>\nSozlamalar, qoidalar, AI xotirasi, tarix, statistika va ilova sessiyalari. "
                                            "Biznes ulanishni Telegram'da alohida o'chiring. Qaytarib bo'lmaydi."),
                             kb([[(tr(lang, "🗑 Да, удалить навсегда", "🗑 Ha, butunlay o'chirish"), "pv:del2")], nav(lang, "m:privacy")]))
    elif action == "del2":
        await app.users.delete_user_data(uid)
        app.settings.invalidate(uid)
        app.autoreply._rules_cache.pop(uid, None)
        app.afk._active_cache.pop(uid, None)
        app.connections.invalidate()
        await app.audit.log("privacy.delete_all", actor_id=uid, target_type="user", target_id=uid)
        await cb.answer(p(lang, "done"), show_alert=True)
        await _render_custom(cb.message, tr(lang, "🗑 Данные удалены. /start — начать заново.", "🗑 Ma'lumotlar o'chirildi. /start — qaytadan boshlash."), None)
    else:
        await cb.answer()


@router.callback_query(F.data.startswith("sub:"))
async def cb_sub(cb: CallbackQuery, state: FSMContext, app: AppContext) -> None:
    uid = await _ensure_user(app, cb)
    s = await app.settings.all(uid)
    lang = s["lang"]
    parts = cb.data.split(":")
    action = parts[1]
    if action == "buy" and len(parts) > 2:
        if not app.config.payments_enabled:
            await cb.answer(tr(lang, "Оплата не включена", "To'lov yoqilmagan"), show_alert=True)
            return
        await cb.answer()
        try:
            await app.payments.send_invoice(uid, parts[2], lang)
        except ValueError as e:
            await cb.message.answer(f"⚠️ {esc(str(e))}")
    elif action == "promo":
        await cb.answer()
        await state.set_state(PS.promo)
        await cb.message.answer(tr(lang, "🎁 Введите промокод (или /cancel):", "🎁 Promokodni kiriting (yoki /cancel):"))
    elif action == "trial":
        try:
            await app.subs.start_trial(uid)
            await cb.answer(tr(lang, "🆓 Пробный Plus на 3 дня активирован!", "🆓 3 kunlik Plus sinovi faollashtirildi!"), show_alert=True)
        except ValueError:
            await cb.answer(tr(lang, "Пробный период уже использован или подписка активна.", "Sinov muddati ishlatilgan yoki obuna faol."), show_alert=True)
        await show(app, uid, "sub", cb.message, True)
    else:
        await cb.answer()


@router.message(StateFilter(PS.promo), F.text)
async def st_promo(message: Message, state: FSMContext, app: AppContext) -> None:
    uid = await _ensure_user(app, message)
    s = await app.settings.all(uid)
    await state.clear()
    ok, _ = app.limiter.check(f"promo:{uid}", 5, 600)
    if not ok:
        await message.answer(p(s["lang"], "rate_limited", sec=600))
        return
    try:
        sub = await app.subs.redeem(uid, message.text.strip())
        await message.answer(tr(s["lang"], "🎉 Промокод активирован: {p} до {d}", "🎉 Promokod faollashtirildi: {p} {d} gacha",
                                p=sub["plan_id"].upper(), d=fmt_dt(sub["expires_at"], s["timezone"])))
        await app.audit.log("promo.redeem", actor_id=uid, target_type="promo", target_id=message.text.strip().upper())
    except ValueError as e:
        await message.answer(f"⚠️ {esc(str(e))}")


@router.callback_query(F.data.startswith("st:"))
async def cb_settings(cb: CallbackQuery, app: AppContext) -> None:
    uid = await _ensure_user(app, cb)
    parts = cb.data.split(":", 2)
    action = parts[1]
    val = parts[2] if len(parts) > 2 else ""
    try:
        if action == "lang" and val in ("ru", "uz"):
            await app.settings.set(uid, "lang", val)
            await app.users.set_language(uid, val)
        elif action == "prefix" and val in PREFIXES:
            await app.settings.set(uid, "prefix", val)
        elif action == "pause" and val.isdigit():
            await app.settings.set(uid, "owner_pause_minutes", int(val))
        elif action == "tz" and val.isdigit() and int(val) < len(TIMEZONES):
            await app.settings.set(uid, "timezone", TIMEZONES[int(val)])
        elif action == "tzmenu":
            s = await app.settings.all(uid)
            await cb.answer()
            rows = grid([(("▶️ " if z == s["timezone"] else "") + z, f"st:tz:{i}") for i, z in enumerate(TIMEZONES)], 2)
            rows.append(nav(s["lang"], "m:settings"))
            await _render_custom(cb.message, tr(s["lang"], "🌍 Выберите часовой пояс:", "🌍 Vaqt mintaqasini tanlang:"), kb(rows))
            return
    except ValueError as e:
        await cb.answer(str(e)[:150], show_alert=True)
        return
    await cb.answer("✅")
    await show(app, uid, "settings", cb.message, True)


@router.callback_query(F.data.startswith("app:"))
async def cb_app(cb: CallbackQuery, app: AppContext) -> None:
    uid = await _ensure_user(app, cb)
    parts = cb.data.split(":")
    if parts[1] == "pair":
        await cb.answer()
        await _send_pair_code(app, uid, cb.message)
        return
    if parts[1] == "rev" and len(parts) > 2 and parts[2].isdigit():
        role = await app.users.role(uid)
        try:
            ok = await app.auth.revoke(int(parts[2]), actor_id=uid, actor_role=role, reason="revoked_in_telegram")
        except Exception:
            ok = False
        await cb.answer("🚫" if ok else "—")
        await show(app, uid, "app", cb.message, True)
        return
    await cb.answer()


@router.callback_query(F.data.startswith("help:"))
async def cb_help(cb: CallbackQuery, state: FSMContext, app: AppContext) -> None:
    uid = await _ensure_user(app, cb)
    s = await app.settings.all(uid)
    await cb.answer()
    if cb.data == "help:support":
        await state.set_state(PS.support)
        await cb.message.answer(tr(s["lang"], "✉️ Опишите вопрос одним сообщением (или /cancel):", "✉️ Savolingizni bitta xabarda yozing (yoki /cancel):"))


@router.message(StateFilter(PS.support), F.text)
async def st_support(message: Message, state: FSMContext, app: AppContext) -> None:
    uid = await _ensure_user(app, message)
    s = await app.settings.all(uid)
    await state.clear()
    await app.support_message(uid, message.text)
    await message.answer(tr(s["lang"], "✅ Сообщение отправлено администратору.", "✅ Xabar administratorga yuborildi."))


@router.callback_query(F.data.startswith("adm:"))
async def cb_admin(cb: CallbackQuery, state: FSMContext, app: AppContext) -> None:
    uid = await _ensure_user(app, cb)
    role = await app.users.role(uid)
    s = await app.settings.all(uid)
    if role != "super_admin":
        await cb.answer(p(s["lang"], "not_allowed"), show_alert=True)
        return
    action = cb.data.split(":")[1]
    if action == "es":
        if role != "super_admin":
            await cb.answer(p(s["lang"], "not_allowed"), show_alert=True)
            return
        app.runtime.emergency_stop = not app.runtime.emergency_stop
        await app.runtime.save()
        await app.audit.log("system.emergency_stop", actor_id=uid, enabled=app.runtime.emergency_stop)
        await cb.answer("🛑" if app.runtime.emergency_stop else "▶️", show_alert=True)
    elif action == "mt":
        app.runtime.maintenance = not app.runtime.maintenance
        await app.runtime.save()
        await app.audit.log("system.maintenance", actor_id=uid, enabled=app.runtime.maintenance)
        await cb.answer("🛠")
    elif action == "bc":
        if role != "super_admin":
            await cb.answer(p(s["lang"], "not_allowed"), show_alert=True)
            return
        await cb.answer()
        await state.set_state(PS.broadcast_text)
        await cb.message.answer(tr(s["lang"], "📣 Текст рассылки (HTML). Будет создан черновик — запуск после предпросмотра. /cancel",
                                   "📣 Tarqatma matni (HTML). Qoralama yaratiladi — ko'rib chiqqandan keyin ishga tushadi. /cancel"))
        return
    elif action == "health":
        await cb.answer()
        rep = await app.health.full()
        lines = ["🩺 <b>Health</b> " + ("✅" if rep["ok"] else "⚠️")]
        for k, v in rep["checks"].items():
            lines.append(f"{'✅' if v.get('ok', True) else '❌'} {k}")
        r = rep["resources"]
        lines.append(f"RAM {r['process_rss_mb']} MB · disk free {r['disk'].get('free_mb')} MB · tmp {r['tmp_mb']} MB")
        await _render_custom(cb.message, "\n".join(lines), kb([nav(s["lang"], "m:admin")]))
        return
    await show(app, uid, "admin", cb.message, True)


@router.message(StateFilter(PS.broadcast_text), F.text)
async def st_broadcast(message: Message, state: FSMContext, app: AppContext) -> None:
    uid = await _ensure_user(app, message)
    await state.clear()
    if await app.users.role(uid) != "super_admin":
        return
    bid = await app.broadcast.create(uid, text=message.html_text[:4000])
    await app.broadcast.preview(bid, uid)
    s = await app.settings.all(uid)
    await message.answer(tr(s["lang"], "Черновик #{b} создан. Запустить?", "#{b} qoralama yaratildi. Ishga tushirilsinmi?", b=bid),
                         reply_markup=kb([[(tr(s["lang"], "🚀 Запустить", "🚀 Ishga tushirish"), f"bc:start:{bid}"),
                                           (p(s["lang"], "cancel"), f"bc:cancel:{bid}")]]))


@router.callback_query(F.data.startswith("bc:"))
async def cb_broadcast(cb: CallbackQuery, app: AppContext) -> None:
    uid = await _ensure_user(app, cb)
    if await app.users.role(uid) != "super_admin":
        await cb.answer("⛔", show_alert=True)
        return
    _, action, bid = cb.data.split(":")
    if action == "start":
        res = await app.broadcast.start(int(bid), uid)
        await cb.answer(f"🚀 {res.get('total', 0)}", show_alert=True)
    elif action == "cancel":
        await app.broadcast.cancel(int(bid), uid)
        await cb.answer("✖️")
    try:
        await cb.message.edit_reply_markup(reply_markup=None)
    except TelegramBadRequest:
        pass


@router.callback_query(F.data == "inbox")
async def cb_inbox(cb: CallbackQuery, app: AppContext) -> None:
    uid = await _ensure_user(app, cb)
    s = await app.settings.all(uid)
    await cb.answer()
    text = await app.inbox.digest_text(uid, s["lang"], use_ai=False)
    await _render_custom(cb.message, text, kb([nav(s["lang"], "m:stats")]))


@router.callback_query(F.data.startswith("cmute:"))
async def cb_chat_mute(cb: CallbackQuery, app: AppContext) -> None:
    uid = await _ensure_user(app, cb)
    chat_id = cb.data.split(":")[1]
    if not chat_id.lstrip("-").isdigit():
        await cb.answer()
        return
    row = await app.chats.update(uid, int(chat_id), {"muted_until": int(time.time()) + 7200})
    await cb.answer("🔕" if row else "—")


# ---- fallback in private chat: commands → executor, otherwise AI assistant / hint -----------

@router.message(StateFilter(None))
async def private_fallback(message: Message, app: AppContext) -> None:
    uid = await _ensure_user(app, message)
    s = await app.settings.all(uid)
    if await app.executor.try_handle(message, user_id=uid, source="private", conn=await app.connections.primary_for_user(uid), settings=s):
        return
    if (await access(app, uid)).locked:
        from ..commands.executor import locked_reply
        text, markup = locked_reply(s["lang"])
        await message.answer(text, reply_markup=markup)
        return
    text = message.text or ""
    if text and app.ai.available() and not text.startswith("/"):
        await app.ai_auto.dm_assistant(uid, message, s)
        return
    if message.text or message.caption:
        await message.answer(tr(s["lang"], "Откройте меню: /menu · команды: <code>{p}help</code>", "Menyuni oching: /menu · buyruqlar: <code>{p}help</code>",
                                p=s["prefix"]))
