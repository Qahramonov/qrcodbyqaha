"""👑 Super Admin panel (bot DM). Only the configured SUPER_ADMIN_ID: checked by PanelGate for every ``ax:`` callback
and AX:* FSM input, again inside each handler, and the «admin» screen is registered as admin-only.

All numbers come from the database / live services — nothing is estimated or invented. Private message contents
of users are never shown here; delegated settings are visible only for scopes the user granted.
"""
from __future__ import annotations

import datetime as dt
import time
from typing import Any

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from ..business.rights import DANGEROUS, RIGHT_FLAGS, RIGHT_TITLES, status_title
from ..commands.registry import CATEGORIES, PLAN_RANK
from ..core.context import MODULES
from ..core.logging import ring_handler
from ..core.timeutil import fmt_dt, human_duration
from ..keyboards import kb, paginate, pager, toggle
from ..localization import tr
from ..security.sanitize import clip, esc
from .ui import PanelGate, ensure_user, register_screen, render

router = Router(name="admin")
router.message.filter(F.chat.type == "private")
router.callback_query.filter(F.message.chat.type == "private")
router.message.middleware(PanelGate())
router.callback_query.middleware(PanelGate())


class AX(StatesGroup):
    user_search = State()


SECTIONS = [
    ("dash", "👑 Dashboard"), ("users", "👥 Users"), ("conns", "🔗 Connections"), ("perms", "🔐 Permissions"),
    ("ctl", "💬 Chat Controls"), ("ai", "🧠 AI Management"), ("twin", "🤖 AI Twin"), ("afk", "💤 AFK"), ("mute", "🔕 Mute Manager"),
    ("media", "🎬 Media Studio"), ("games", "🎮 Games"), ("cmds", "⌨️ Commands"), ("sched", "⏰ Scheduler"), ("mods", "🧩 Modules"),
    ("subs", "💎 Subscriptions"), ("bcast", "📢 Broadcast"), ("analytics", "📈 Analytics"), ("sec", "🛡 Security"), ("logs", "📋 Logs"),
    ("db", "🗄 Database"), ("sys", "⚙️ System"), ("diag", "🩺 Diagnostics"), ("look", "🎨 Appearance"),
]


def _back(lang: str) -> list[tuple[str, str]]:
    return [(tr(lang, "⬅️ Разделы", "⬅️ Bo'limlar"), "ax:menu"), (tr(lang, "🏠 Меню", "🏠 Menyu"), "m:home")]


def _since(days: int) -> str:
    return (dt.datetime.now(dt.timezone.utc).date() - dt.timedelta(days=days - 1)).isoformat()


async def admin_menu(app: Any, uid: int, s: dict[str, Any]) -> tuple[str, Any]:
    lang = s["lang"]
    users = await app.users.count()
    conns = await app.connections.counts()
    text = "\n".join([tr(lang, "👑 <b>Super Admin</b>", "👑 <b>Super Admin</b>"),
                      tr(lang, "Пользователей: {u} · активных подключений: {c}", "Foydalanuvchilar: {u} · faol ulanishlar: {c}",
                         u=users, c=conns.get("active", 0)),
                      tr(lang, "Аварийная остановка: {e} · обслуживание: {m}", "Favqulodda to'xtatish: {e} · texnik xizmat: {m}",
                         e="🔴" if app.runtime.emergency_stop else "🟢", m="🛠" if app.runtime.maintenance else "—")])
    items = [(title, f"ax:{key}") for key, title in SECTIONS]
    rows = [items[i:i + 2] for i in range(0, len(items), 2)]
    rows.append([(tr(lang, "🏠 Меню", "🏠 Menyu"), "m:home")])
    return text, kb(rows)


register_screen("admin", admin_menu, admin=True)


# ---- sections ----------------------------------------------------------------------------------------------------------
async def sec_dash(app: Any, lang: str, args: list[str]) -> tuple[str, list]:
    days = int(args[0]) if args and args[0] in ("1", "7", "30") else 1
    since = _since(days)
    tot = lambda m: app.metrics.total(m, 0, since)  # noqa: E731
    res = app.health.resources()
    subs = await app.subs.stats()
    conns = await app.connections.counts()
    dau = await app.db.fetchval("SELECT COUNT(DISTINCT user_id) FROM user_activity WHERE day>=?", (since,), 0)
    errors = int(await tot("errors"))
    paid = await app.db.fetchval("SELECT COALESCE(SUM(amount),0) FROM payments WHERE status='paid' AND created_at>=?",
                                 (int(time.time()) - days * 86400,), 0)
    disk = res["disk"]
    lines = [f"👑 <b>Dashboard</b> · {tr(lang, 'сегодня', 'bugun') if days == 1 else tr(lang, '{d} дней', '{d} kun', d=days)}", "",
             tr(lang, "👥 Пользователи: {u} · активные: {a}", "👥 Foydalanuvchilar: {u} · faol: {a}", u=await app.users.count(), a=dau),
             tr(lang, "🔗 Business-подключения: {a} активных из {t}", "🔗 Biznes ulanishlar: {t} dan {a} faol", a=conns.get("active", 0), t=conns.get("total", 0)),
             tr(lang, "💬 Сообщения: вход {i} · исход {o}", "💬 Xabarlar: kiruvchi {i} · chiquvchi {o}", i=int(await tot("messages_in")), o=int(await tot("messages_out"))),
             tr(lang, "⌨️ Команды: {c} · 🧠 AI-запросы: {a}", "⌨️ Buyruqlar: {c} · 🧠 AI so'rovlar: {a}", c=int(await tot("commands")), a=int(await tot("ai_requests"))),
             tr(lang, "🎬 Медиа-задачи: {m} · ⚠️ ошибки: {e}", "🎬 Media vazifalar: {m} · ⚠️ xatolar: {e}", m=int(await tot("media_jobs")), e=errors),
             tr(lang, "⭐ Выручка: {p} XTR · 💎 подписки: {s}", "⭐ Daromad: {p} XTR · 💎 obunalar: {s}", p=paid,
                s=sum(v for k, v in subs["active_by_plan"].items() if k != "free")),
             tr(lang, "🖥 RAM процесса: {r} МБ · CPU: {c}%", "🖥 Jarayon RAM: {r} MB · CPU: {c}%", r=res.get("process_rss_mb") or "?",
                c=res.get("cpu_percent") if res.get("cpu_percent") is not None else "?"),
             tr(lang, "💽 Диск: свободно {f} МБ · ⏱ аптайм {u}", "💽 Disk: bo'sh {f} MB · ⏱ ishlash vaqti {u}", f=disk.get("free_mb"),
                u=human_duration(app.uptime, lang))]
    rows = [[(("▶️ " if days == d else "") + label, f"ax:dash:{d}") for d, label in
             ((1, tr(lang, "Сегодня", "Bugun")), (7, tr(lang, "7 дней", "7 kun")), (30, tr(lang, "30 дней", "30 kun")))]]
    return "\n".join(lines), rows


async def sec_users(app: Any, lang: str, args: list[str]) -> tuple[str, list]:
    if args and args[0] == "u" and len(args) > 1 and args[1].isdigit():
        return await user_card(app, lang, int(args[1]))
    page = int(args[0]) if args and args[0].isdigit() else 0
    rows_db = await app.db.fetchall("SELECT id, username, first_name, status, last_seen_at FROM users ORDER BY COALESCE(last_seen_at,0) DESC LIMIT 200")
    chunk, page, pages = paginate(rows_db, page, 8)
    lines = [tr(lang, "👥 <b>Пользователи</b> ({n})", "👥 <b>Foydalanuvchilar</b> ({n})", n=len(rows_db))]
    rows = [[((("⛔ " if u["status"] == "restricted" else "") + clip(u["first_name"] or str(u["id"]), 20) +
               (f" @{u['username']}" if u["username"] else "")), f"ax:users:u:{u['id']}")] for u in chunk]
    if pages > 1:
        rows.append(pager("ax:users", page, pages))
    rows.append([(tr(lang, "🔎 Найти по ID / @username", "🔎 ID / @username bo'yicha topish"), "ax:find")])
    return "\n".join(lines), rows


async def user_card(app: Any, lang: str, uid: int) -> tuple[str, list]:
    u = await app.users.get(uid)
    if u is None:
        return tr(lang, "Пользователь не найден.", "Foydalanuvchi topilmadi."), [[("⬅️", "ax:users")]]
    plan = await app.subs.plan_of(uid)
    conns = await app.connections.for_user(uid)
    grants = [k for k, v in (await app.delegation.grants(uid)).items() if v["active"]]
    ai_today = await app.metrics.total("ai_requests", uid, _since(1))
    lines = [f"👤 <b>{esc(u.get('first_name') or '—')}</b> " + (f"@{esc(u['username'])}" if u.get("username") else ""),
             f"🆔 <code>{uid}</code> · {u.get('status')} · {u.get('language')}",
             tr(lang, "Тариф: {p} · AI сегодня: {a}", "Tarif: {p} · AI bugun: {a}", p=plan.upper(), a=int(ai_today)),
             tr(lang, "Последняя активность: {t}", "Oxirgi faollik: {t}", t=fmt_dt(u.get("last_seen_at"), "UTC") if u.get("last_seen_at") else "—")]
    for c in conns[:3]:
        lines.append(f"🔗 {status_title(c.status, lang)} · " + tr(lang, "прав: {n}", "huquqlar: {n}", n=sum(1 for v in c.rights.values() if v)))
    lines.append(tr(lang, "🤝 Делегировано: {d}", "🤝 Vakolat: {d}", d=", ".join(grants) if grants else "—"))
    lines.append(tr(lang, "ℹ️ Переписка пользователя здесь не показывается.", "ℹ️ Foydalanuvchi yozishmalari bu yerda ko'rsatilmaydi."))
    rows = [[((tr(lang, "✅ Разблокировать", "✅ Blokdan chiqarish") if u.get("status") == "restricted" else tr(lang, "⛔ Заблокировать", "⛔ Bloklash")),
              f"ax:uact:{uid}:{'unblock' if u.get('status') == 'restricted' else 'block'}")],
            [(f"💎 {p.upper()} 30d", f"ax:uact:{uid}:grant_{p}") for p in ("plus", "pro", "vip")],
            [(tr(lang, "✖️ Снять подписку", "✖️ Obunani bekor qilish"), f"ax:uact:{uid}:revoke")],
            [(tr(lang, "⬅️ Пользователи", "⬅️ Foydalanuvchilar"), "ax:users")]]
    return "\n".join(lines), rows


async def sec_conns(app: Any, lang: str, args: list[str]) -> tuple[str, list]:
    conns = await app.connections.all()
    lines = [tr(lang, "🔗 <b>Business Connections</b> ({n})", "🔗 <b>Biznes ulanishlar</b> ({n})", n=len(conns))]
    for c in conns[:15]:
        mods = await app.db.fetchval("SELECT COUNT(*) FROM chat_control_states WHERE owner_id=? AND enabled=1", (c.user_id,), 0)
        snap = await app.db.fetchone("SELECT created_at FROM permission_snapshots WHERE connection_id=? ORDER BY id DESC LIMIT 1", (c.id,))
        lines.append(f"• <code>{c.user_id}</code> {status_title(c.status, lang)} · "
                     + tr(lang, "прав {r} · модулей {m} · обновлено {t}", "huquq {r} · modul {m} · yangilangan {t}",
                          r=sum(1 for v in c.rights.values() if v), m=mods,
                          t=fmt_dt((snap or {}).get("created_at") or c.connected_at, "UTC")))
    return "\n".join(lines), []


async def sec_perms(app: Any, lang: str, args: list[str]) -> tuple[str, list]:
    conns = await app.connections.all(enabled_only=True)
    lines = [tr(lang, "🔐 <b>Матрица прав</b> (активных подключений: {n})", "🔐 <b>Huquqlar matritsasi</b> (faol ulanishlar: {n})", n=len(conns))]
    for r in RIGHT_FLAGS:
        n = sum(1 for c in conns if c.rights.get(r))
        lines.append(("⚠️ " if r in DANGEROUS and n else "") + f"{tr(lang, *RIGHT_TITLES[r])}: {n}/{len(conns)}")
    lines.append(tr(lang, "Наличие прав у бота не даёт администратору права действовать от имени пользователя.",
                    "Botda huquq borligi administratorga foydalanuvchi nomidan ishlash huquqini bermaydi."))
    return "\n".join(lines), []


async def sec_ctl(app: Any, lang: str, args: list[str]) -> tuple[str, list]:
    counts = await app.controls.counts()
    cards = await app.db.fetchval("SELECT COUNT(*) FROM control_messages WHERE status='active'", default=0)
    since = int(time.time()) - 86400
    deleted = await app.db.fetchval("SELECT COUNT(*) FROM mute_events WHERE result='deleted' AND created_at>=?", (since,), 0)
    lines = [tr(lang, "💬 <b>Chat Controls</b>", "💬 <b>Chat Controls</b>"),
             tr(lang, "Активные режимы: {c}", "Faol rejimlar: {c}", c=", ".join(f"{k}: {v}" for k, v in counts.items()) or "—"),
             tr(lang, "Активных карточек управления: {n}", "Faol boshqaruv kartalari: {n}", n=cards),
             tr(lang, "Удалено фильтрами за 24 ч: {n}", "24 soatda filtrlar o'chirdi: {n}", n=deleted)]
    return "\n".join(lines), []


async def sec_ai(app: Any, lang: str, args: list[str]) -> tuple[str, list]:
    if args and args[0] == "tog" and len(args) > 1 and args[1] in app.ai.providers:
        name = args[1]
        (app.ai.disabled.discard if name in app.ai.disabled else app.ai.disabled.add)(name)
        await app.audit.log("ai.provider_toggle", actor_id=app.config.super_admin_id, target_type="ai_provider", target_id=name)
    usage = await app.ai.usage_summary(None, 1)
    lines = [tr(lang, "🧠 <b>AI Management</b>", "🧠 <b>AI boshqaruvi</b>"),
             tr(lang, "Сегодня: {r} запросов · {t} токенов · ${c}", "Bugun: {r} so'rov · {t} token · ${c}", r=usage["today_requests"],
                t=usage["today_tokens"], c=round(usage["today_cost"], 4)),
             tr(lang, "Бюджет: ${g}/день глобально, ${u}/день на пользователя", "Byudjet: kuniga ${g} global, ${u} foydalanuvchiga",
                g=app.config.ai_global_daily_budget_usd, u=app.config.ai_user_daily_budget_usd), ""]
    rows = []
    for p in app.ai.providers_status():
        if p["name"] == "echo" and not p["configured"]:
            continue
        state = "⏸" if p["disabled"] else ("🟢" if p["configured"] else "⚪️")
        lines.append(f"{state} {p['name']} · {p.get('model') or '—'} · {', '.join(p.get('supports') or [])}")
        if p["configured"]:
            rows.append([toggle(p["name"], not p["disabled"], f"ax:ai:tog:{p['name']}")])
    return "\n".join(lines), rows


async def sec_twin(app: Any, lang: str, args: list[str]) -> tuple[str, list]:
    rows = await app.db.fetchall("SELECT mode, COUNT(*) AS n FROM ai_twin_profiles GROUP BY mode")
    lines = [tr(lang, "🤖 <b>AI Twin</b>", "🤖 <b>AI Twin</b>")] + ([f"• {r['mode']}: {r['n']}" for r in rows] or ["—"])
    return "\n".join(lines), []


async def sec_afk(app: Any, lang: str, args: list[str]) -> tuple[str, list]:
    n = await app.db.fetchval("SELECT COUNT(*) FROM afk_sessions WHERE ended_at IS NULL", default=0)
    replies = await app.metrics.total("auto:afk", 0, _since(1))
    return "\n".join([tr(lang, "💤 <b>AFK</b>", "💤 <b>AFK</b>"), tr(lang, "Активных AFK: {n}", "Faol AFK: {n}", n=n),
                      tr(lang, "AFK-ответов сегодня: {r}", "Bugungi AFK javoblari: {r}", r=int(replies))]), []


async def sec_mute(app: Any, lang: str, args: list[str]) -> tuple[str, list]:
    since = int(time.time()) - 86400
    rows = await app.db.fetchall("SELECT source, result, COUNT(*) AS n FROM mute_events WHERE created_at>=? GROUP BY source, result", (since,))
    active = (await app.controls.counts()).get("mute", 0)
    lines = [tr(lang, "🔕 <b>Mute Manager</b>", "🔕 <b>Mute Manager</b>"), tr(lang, "Активных Mute: {n}", "Faol Mute: {n}", n=active),
             tr(lang, "За 24 ч:", "24 soatda:")] + [f"• {r['source']} · {r['result']}: {r['n']}" for r in rows]
    return "\n".join(lines), []


async def sec_media(app: Any, lang: str, args: list[str]) -> tuple[str, list]:
    q = app.media.queue.status()
    paused = app.runtime.is_module_paused("media")
    if args and args[0] == "tog":
        await _toggle_module(app, "media")
        paused = app.runtime.is_module_paused("media")
    lines = [tr(lang, "🎬 <b>Media Studio</b>", "🎬 <b>Media Studio</b>"),
             tr(lang, "FFmpeg: {f}", "FFmpeg: {f}", f="✅" if app.health.ffmpeg_ok else "❌"),
             tr(lang, "Очередь: {q} · в работе: {a} · обработано: {p} · ошибок: {e}", "Navbat: {q} · ishlanmoqda: {a} · bajarildi: {p} · xato: {e}",
                q=q["queued"], a=q["active"], p=q["processed"], e=q["failed"]),
             tr(lang, "Лимит файла: {m} МБ · длительность до {d} с", "Fayl limiti: {m} MB · davomiylik {d} s gacha",
                m=app.config.media_max_input_mb, d=app.config.media_max_duration)]
    return "\n".join(lines), [[toggle(tr(lang, "Модуль включён", "Modul yoqilgan"), not paused, "ax:media:tog")]]


async def sec_games(app: Any, lang: str, args: list[str]) -> tuple[str, list]:
    if args and args[0] == "tog":
        await _toggle_module(app, "games")
    active = await app.db.fetchval("SELECT COUNT(*) FROM game_sessions WHERE status IN ('pending','active')", default=0)
    played = await app.db.fetchval("SELECT COUNT(*) FROM game_results WHERE created_at>=?", (int(time.time()) - 86400,), 0)
    return "\n".join([tr(lang, "🎮 <b>Games</b>", "🎮 <b>O'yinlar</b>"), tr(lang, "Активных сессий: {a} · сыграно за 24 ч: {p}",
                                                                           "Faol seanslar: {a} · 24 soatda o'ynaldi: {p}", a=active, p=played)]), \
        [[toggle(tr(lang, "Модуль включён", "Modul yoqilgan"), not app.runtime.is_module_paused("games"), "ax:games:tog")]]


async def sec_cmds(app: Any, lang: str, args: list[str]) -> tuple[str, list]:
    if args and args[0] == "tog" and len(args) > 1 and args[1] in app.registry.commands:
        enabled, _ = app.executor._global_state(app.registry.commands[args[1]])  # noqa: SLF001
        await app.executor.set_global(args[1], enabled=not enabled)
        args = ["cat", app.registry.commands[args[1]].category]
    if args and args[0] == "cat" and len(args) > 1 and args[1] in CATEGORIES:
        cat = args[1]
        specs = sorted((sp for sp in app.registry.commands.values() if sp.category == cat), key=lambda sp: sp.id)
        rows = []
        for sp in specs[:24]:
            enabled, plan = app.executor._global_state(sp)  # noqa: SLF001
            rows.append([toggle(f".{sp.id} · {plan}", enabled, f"ax:cmds:tog:{sp.id}")])
        rows.append([("⬅️", "ax:cmds")])
        return f"⌨️ <b>{CATEGORIES[cat][0]} {tr(lang, CATEGORIES[cat][1], CATEGORIES[cat][2])}</b>", rows
    items = [(f"{CATEGORIES[c][0]} {tr(lang, CATEGORIES[c][1], CATEGORIES[c][2])}", f"ax:cmds:cat:{c}") for c in CATEGORIES]
    off = sum(1 for sp in app.registry.commands.values() if not app.executor._global_state(sp)[0])  # noqa: SLF001
    return tr(lang, "⌨️ <b>Command Manager</b>\nКоманд: {n} · отключено глобально: {o}", "⌨️ <b>Buyruqlar</b>\nBuyruqlar: {n} · global o'chirilgan: {o}",
              n=len(app.registry), o=off), [items[i:i + 2] for i in range(0, len(items), 2)]


async def sec_sched(app: Any, lang: str, args: list[str]) -> tuple[str, list]:
    rows = await app.db.fetchall("SELECT kind, COUNT(*) AS n FROM scheduled_tasks WHERE status='pending' GROUP BY kind")
    lines = [tr(lang, "⏰ <b>Scheduler</b>", "⏰ <b>Rejalashtiruvchi</b>"), tr(lang, "Ожидают: {x}", "Kutmoqda: {x}",
                                                                              x=", ".join(f"{r['kind']} {r['n']}" for r in rows) or "—"), ""]
    for j in app.scheduler.periodic:
        mark = "⚠️" if j.get("last_error") else "✅"
        lines.append(f"{mark} {j['name']} · {tr(lang, 'каждые', 'har')} {j['interval']}s · runs {j['runs']}")
    return "\n".join(lines), []


async def _toggle_module(app: Any, module: str) -> None:
    if module in app.runtime.paused_modules:
        app.runtime.paused_modules.discard(module)
    else:
        app.runtime.paused_modules.add(module)
    await app.runtime.save()
    await app.audit.log("system.module_toggle", actor_id=app.config.super_admin_id, target_type="module", target_id=module)


async def sec_mods(app: Any, lang: str, args: list[str]) -> tuple[str, list]:
    if args and args[0] == "tog" and len(args) > 1 and args[1] in MODULES:
        await _toggle_module(app, args[1])
    rows = [[toggle(m, not app.runtime.is_module_paused(m), f"ax:mods:tog:{m}") for m in MODULES[i:i + 2]] for i in range(0, len(MODULES), 2)]
    return tr(lang, "🧩 <b>Модули</b>\nВыключенный модуль перестаёт работать для всех пользователей.",
              "🧩 <b>Modullar</b>\nO'chirilgan modul barcha foydalanuvchilar uchun ishlamaydi."), rows


async def sec_subs(app: Any, lang: str, args: list[str]) -> tuple[str, list]:
    st = await app.subs.stats()
    plans = await app.db.fetchall("SELECT id, name, price_stars, duration_days FROM subscription_plans ORDER BY sort")
    lines = [tr(lang, "💎 <b>Subscriptions</b>", "💎 <b>Obunalar</b>"),
             tr(lang, "Активные: {x}", "Faol: {x}", x=", ".join(f"{k} {v}" for k, v in st["active_by_plan"].items())),
             tr(lang, "Выручка всего: {r} XTR · истекают за 3 дня: {e}", "Jami daromad: {r} XTR · 3 kunda tugaydi: {e}", r=st["revenue_stars"], e=st["expiring_3d"]),
             tr(lang, "Платежи Stars: {v}", "Stars to'lovlari: {v}", v="✅" if app.config.payments_enabled else tr(lang, "выключены (.env)", "o'chirilgan (.env)")), ""]
    lines += [f"• {p['name']}: {p['price_stars']}⭐ / {p['duration_days'] or '∞'} d" for p in plans]
    lines.append(tr(lang, "Выдать или снять подписку — в карточке пользователя.", "Obuna berish yoki olish — foydalanuvchi kartasida."))
    return "\n".join(lines), []


async def sec_bcast(app: Any, lang: str, args: list[str]) -> tuple[str, list]:
    rows = await app.db.fetchall("SELECT id, status, total, sent, failed, created_at FROM broadcasts ORDER BY id DESC LIMIT 5")
    lines = [tr(lang, "📢 <b>Broadcast</b>", "📢 <b>Tarqatma</b>"),
             tr(lang, "Рассылка идёт только пользователям, которые запустили бота, и только в личку бота — никогда через бизнес-аккаунты.",
                "Tarqatma faqat botni ishga tushirgan foydalanuvchilarga va faqat bot chatiga yuboriladi — hech qachon biznes akkauntlar orqali emas."), ""]
    lines += [f"#{r['id']} · {r['status']} · {r['sent']}/{r['total']} · ✖️{r['failed']}" for r in rows] or [tr(lang, "Рассылок пока не было.", "Hali tarqatma bo'lmagan.")]
    return "\n".join(lines), [[(tr(lang, "✍️ Новая рассылка", "✍️ Yangi tarqatma"), "adm:bc")]]


async def sec_analytics(app: Any, lang: str, args: list[str]) -> tuple[str, list]:
    today = dt.datetime.now(dt.timezone.utc).date()
    wau = await app.db.fetchval("SELECT COUNT(DISTINCT user_id) FROM user_activity WHERE day>=?", (_since(7),), 0)
    mau = await app.db.fetchval("SELECT COUNT(DISTINCT user_id) FROM user_activity WHERE day>=?", (_since(30),), 0)
    dau = await app.db.fetchval("SELECT COUNT(DISTINCT user_id) FROM user_activity WHERE day=?", (today.isoformat(),), 0)
    ret = await app.analytics.retention(today - dt.timedelta(days=30), today)
    lines = ["📈 <b>Analytics</b>", f"DAU {dau} · WAU {wau} · MAU {mau}",
             tr(lang, "Удержание D1: {a} · D7: {b} (когорта {c})", "Saqlanish D1: {a} · D7: {b} (kogorta {c})",
                a=f"{ret['d1'] * 100:.0f}%" if ret.get("d1") is not None else "—", b=f"{ret['d7'] * 100:.0f}%" if ret.get("d7") is not None else "—",
                c=ret.get("cohort", 0)),
             tr(lang, "Подробные графики и экспорт CSV/PDF — в приложении Chat helper Control.",
                "Batafsil grafiklar va CSV/PDF eksport — Chat helper Control ilovasida.")]
    return "\n".join(lines), []


async def sec_sec(app: Any, lang: str, args: list[str]) -> tuple[str, list]:
    sessions = await app.db.fetchval("SELECT COUNT(*) FROM admin_sessions WHERE revoked_at IS NULL", default=0)
    since = int(time.time()) - 86400
    failed = await app.db.fetchval("SELECT COUNT(*) FROM login_events WHERE success=0 AND created_at>=?", (since,), 0)
    denied = await app.db.fetchval("SELECT COUNT(*) FROM audit_logs WHERE action LIKE 'security.%' AND created_at>=?", (since,), 0)
    foreign = await app.db.fetchval("SELECT COUNT(*) FROM audit_logs WHERE action='controls.foreign_press' AND created_at>=?", (since,), 0)
    deleg = await app.db.fetchval("SELECT COUNT(*) FROM delegated_permissions WHERE revoked_at IS NULL", default=0)
    lines = ["🛡 <b>Security</b>",
             tr(lang, "Сессий приложения: {s} · неудачных входов за 24 ч: {f}", "Ilova seanslari: {s} · 24 soatda muvaffaqiyatsiz kirish: {f}", s=sessions, f=failed),
             tr(lang, "Отказов в доступе: {d} · нажатий чужих кнопок: {x}", "Kirish rad etildi: {d} · begona tugma bosishlar: {x}", d=denied, x=foreign),
             tr(lang, "Активных делегирований: {n}", "Faol vakolatlar: {n}", n=deleg)]
    rows = [[toggle(tr(lang, "🛑 Аварийная остановка", "🛑 Favqulodda to'xtatish"), app.runtime.emergency_stop, "adm:es")],
            [toggle(tr(lang, "🛠 Обслуживание", "🛠 Texnik xizmat"), app.runtime.maintenance, "adm:mt")]]
    return "\n".join(lines), rows


async def sec_logs(app: Any, lang: str, args: list[str]) -> tuple[str, list]:
    items = ring_handler.query(level="WARNING", limit=12)
    lines = [tr(lang, "📋 <b>Последние предупреждения и ошибки</b>", "📋 <b>So'nggi ogohlantirish va xatolar</b>")]
    for it in items:
        lines.append(f"<code>{fmt_dt(it['ts'], 'UTC', with_date=False)}</code> {it['level'][0]} {esc(clip(it['message'], 120))}")
    if not items:
        lines.append(tr(lang, "Нет предупреждений 👍", "Ogohlantirishlar yo'q 👍"))
    return "\n".join(lines), [[(tr(lang, "🔄 Обновить", "🔄 Yangilash"), "ax:logs")]]


async def sec_db(app: Any, lang: str, args: list[str]) -> tuple[str, list]:
    note = ""
    if args and args[0] == "backup":
        path = await app.backups.create("admin")
        note = tr(lang, "✅ Бэкап создан: {p}", "✅ Zaxira yaratildi: {p}", p=esc(path.name))
        await app.audit.log("system.backup", actor_id=app.config.super_admin_id, target_type="backup", target_id=path.name)
    if args and args[0] == "check":
        ok = (await app.db.integrity_check())["ok"]
        note = "✅ integrity ok" if ok else "❌ integrity FAILED"
    size = await app.db.size_info()
    from ..database.migrations import current_version
    lines = ["🗄 <b>Database</b>", tr(lang, "Размер: {s} МБ · схема v{v} · бэкапов: {b}", "Hajmi: {s} MB · sxema v{v} · zaxiralar: {b}",
                                      s=round(size["bytes"] / 1048576, 2), v=await current_version(app.db), b=len(app.backups.list()))]
    if note:
        lines.append(note)
    return "\n".join(lines), [[(tr(lang, "💾 Бэкап сейчас", "💾 Hozir zaxira"), "ax:db:backup"), (tr(lang, "🔍 Проверка", "🔍 Tekshiruv"), "ax:db:check")]]


async def sec_sys(app: Any, lang: str, args: list[str]) -> tuple[str, list]:
    from .. import __version__
    lines = ["⚙️ <b>System</b>", f"Chat helper v{__version__} · uptime {human_duration(app.uptime, lang)}",
             f"Telegram polling: {'✅' if app.polling_active else '❌'} · FFmpeg: {'✅' if app.health.ffmpeg_ok else '❌'} · "
             f"AI: {'✅' if app.ai.available() else '—'} · scheduler: {'✅' if app.scheduler.running else '❌'}",
             f"API: {app.config.api_host}:{app.config.api_port}"]
    return "\n".join(lines), [[(tr(lang, "🩺 Полная диагностика", "🩺 To'liq diagnostika"), "ax:diag")]]


async def sec_diag(app: Any, lang: str, args: list[str]) -> tuple[str, list]:
    rep = await app.health.full(include_remote=False)
    lines = ["🩺 <b>Diagnostics</b> " + ("✅" if rep["ok"] else "⚠️")]
    for k, v in rep["checks"].items():
        lines.append(("✅ " if v.get("ok", True) else "❌ ") + k)
    return "\n".join(lines), [[(tr(lang, "🔄 Повторить", "🔄 Takrorlash"), "ax:diag")]]


async def sec_look(app: Any, lang: str, args: list[str]) -> tuple[str, list]:
    from ..modules.afk import render_afk
    theme = args[0] if args and args[0] in ("classic", "minimal", "fancy", "emoji") else "fancy"
    preview = render_afk(theme, lang, name="Chat helper", reason=tr(lang, "встреча", "uchrashuv"), away=1800, until_ts=None,
                         tz_name=app.config.timezone, part="day")
    lines = ["🎨 <b>Appearance</b>", tr(lang, "Стили AFK-сообщений (каждый пользователь выбирает свой в настройках AFK):",
                                       "AFK xabar uslublari (har bir foydalanuvchi AFK sozlamalarida o'zinikini tanlaydi):"), "", preview]
    return "\n".join(lines), [[(("▶️ " if t == theme else "") + t, f"ax:look:{t}") for t in ("classic", "minimal", "fancy", "emoji")]]


HANDLERS = {"dash": sec_dash, "users": sec_users, "conns": sec_conns, "perms": sec_perms, "ctl": sec_ctl, "ai": sec_ai, "twin": sec_twin,
            "afk": sec_afk, "mute": sec_mute, "media": sec_media, "games": sec_games, "cmds": sec_cmds, "sched": sec_sched, "mods": sec_mods,
            "subs": sec_subs, "bcast": sec_bcast, "analytics": sec_analytics, "sec": sec_sec, "logs": sec_logs, "db": sec_db, "sys": sec_sys,
            "diag": sec_diag, "look": sec_look}


# ---- callbacks ----------------------------------------------------------------------------------------------------------
@router.callback_query(F.data.startswith("ax:"))
async def cb_admin_x(cb: CallbackQuery, state: FSMContext, app: Any) -> None:
    uid = await ensure_user(app, cb)
    if not app.users.is_super_id(uid):  # defence in depth (PanelGate already refuses)
        await cb.answer("⛔", show_alert=True)
        return
    s = await app.settings.all(uid)
    lang = s["lang"]
    parts = (cb.data or "").split(":")[1:]
    section, args = (parts[0] if parts else "menu"), parts[1:]
    if section == "menu":
        await cb.answer()
        text, markup = await admin_menu(app, uid, s)
        await render(cb.message, text, markup)
        return
    if section == "find":
        await state.set_state(AX.user_search)
        await cb.answer()
        await cb.message.answer(tr(lang, "🔎 Пришлите Telegram ID или @username.", "🔎 Telegram ID yoki @username yuboring."))
        return
    if section == "uact" and len(args) == 2 and args[0].isdigit():
        target, act = int(args[0]), args[1]
        if act == "block" and not app.users.is_super_id(target):
            await app.users.restrict(target, "admin panel")
        elif act == "unblock":
            await app.users.restore(target)
        elif act.startswith("grant_") and act[6:] in PLAN_RANK:
            await app.subs.grant(target, act[6:], 30, source="admin", granted_by=uid)
        elif act == "revoke":
            await app.subs.revoke(target, by=uid)
        await app.audit.log(f"admin.user_{act}", actor_id=uid, target_type="user", target_id=target)
        section, args = "users", ["u", str(target)]
    handler = HANDLERS.get(section)
    if handler is None:
        await cb.answer()
        return
    text, rows = await handler(app, lang, args)
    await cb.answer()
    await render(cb.message, text, kb(rows + [_back(lang)]))


@router.message(AX.user_search, F.text)
async def st_user_search(message: Message, state: FSMContext, app: Any) -> None:
    uid = await ensure_user(app, message)
    if not app.users.is_super_id(uid):
        await state.clear()
        return
    s = await app.settings.all(uid)
    q = message.text.strip().lstrip("@")
    row = None
    if q.isdigit():
        row = await app.users.get(int(q))
    else:
        row = await app.db.fetchone("SELECT * FROM users WHERE LOWER(username)=?", (q.lower(),))
    await state.clear()
    if row is None:
        await message.answer(tr(s["lang"], "Пользователь не найден.", "Foydalanuvchi topilmadi."), reply_markup=kb([_back(s["lang"])]))
        return
    text, rows = await user_card(app, s["lang"], int(row["id"]))
    await message.answer(text, reply_markup=kb(rows + [_back(s["lang"])]))

