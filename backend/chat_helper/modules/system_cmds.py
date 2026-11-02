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


@registry.command("help", "system", aliases=["помощь", "h", "yordam", "start_help"], sandbox_safe=True, **SYS)
async def cmd_help(ctx: CommandContext) -> None:
    pre = ctx.prefix
    if ctx.args:
        spec = ctx.app.registry.resolve(ctx.args[0].lstrip(pre).lstrip("./"), admin=ctx.is_super)
        if spec is None:
            raise CommandError(ctx.t("system_cmds.komanda_naydena"))
        d = spec.to_dict(ctx.lang, pre)
        lines = [f"<b>{esc(d['name'])}</b> — {esc(d['description'])}", f"<code>{esc(d['syntax'])}</code>"]
        if d["aliases"]:
            lines.append(ctx.t("system_cmds.aliasy") + esc(", ".join(d["aliases"])))
        lines += [f"• <code>{esc(e.replace('.', pre, 1))}</code>" for e in d["examples"][:3]]
        if d["notes"]:
            lines.append("ℹ️ " + esc(d["notes"]))
        await ctx.answer("\n".join(lines), private=ctx.is_business)
        return
    lines = [ctx.t("system_cmds.chat_helper_komandy_prefiks", p=pre)]
    for cat, specs in ctx.app.registry.by_category(admin=ctx.is_super).items():
        if not specs:
            continue
        emoji, key = CATEGORIES.get(cat, ("•", None))
        names = " ".join(f"{pre}{s.id}" for s in sorted(specs, key=lambda x: x.id))
        lines.append(f"\n{emoji} <b>{ctx.t(key) if key else cat}</b>\n<code>{esc(names)}</code>")
    lines.append(ctx.t("system_cmds.podrobno_help_komanda_menyu_menu", p=pre))
    await ctx.answer("\n".join(lines), private=ctx.is_business)


@registry.command("commands", "system", aliases=["команды", "buyruqlar", "cmds"], sandbox_safe=True, **SYS)
async def cmd_commands(ctx: CommandContext) -> None:
    names = sorted(s.id for s in ctx.app.registry.visible(admin=ctx.is_super))
    await ctx.answer(ctx.t("system_cmds.komand", n=len(names)) + "<code>" + esc(" ".join(ctx.prefix + n for n in names)) + "</code>",
                     private=ctx.is_business)


@registry.command("menu", "system", aliases=["меню", "menyu"], **SYS)
async def cmd_menu(ctx: CommandContext) -> None:
    from ..handlers.panel import screen_home
    text, markup = await screen_home(ctx.app, ctx.user_id, ctx.settings)
    await ctx.app.sender.send_text(ctx.user_id, text, markup=markup)
    await ctx.cleanup_command(fallback_text="📋")


@registry.command("settings", "system", aliases=["настройки", "sozlamalar"], sandbox_safe=True, **SYS)
async def cmd_settings(ctx: CommandContext) -> None:
    s = ctx.settings
    lines = [ctx.t("system_cmds.nastroyki"),
             f"🌐 {s['lang']} · {ctx.t('system_cmds.prefiks')} <code>{esc(s['prefix'])}</code> · 🕒 {esc(s['timezone'])}",
             f"💬 {mode_title(s['mode'], ctx.lang)}",
             f"⏸ {ctx.t('system_cmds.pauza_avtomatiki')}: {on_off(ctx.lang, s['automation_paused'])}",
             f"🧠 AI: {s['ai_style']} · {ctx.t('system_cmds.podtverzhdenie')} {on_off(ctx.lang, s['ai_confirm'])}",
             f"🗑 {ctx.t('system_cmds.udalyat_komandy')}: {on_off(ctx.lang, s['delete_commands'])}",
             ctx.t("system_cmds.izmenit_menu_nastroyki_prilozhenie_chat")]
    await ctx.answer("\n".join(lines), private=ctx.is_business)


@registry.command("status", "system", aliases=["статус", "holat"], **SYS)
async def cmd_status(ctx: CommandContext) -> None:
    app = ctx.app
    conn = ctx.conn or await app.connections.primary_for_user(ctx.user_id)
    afk = await app.afk.active(ctx.user_id)
    lines = [ctx.t("system_cmds.status_chat_helper"),
             "🔗 " + (status_title(conn.status, ctx.lang) if conn else ctx.t("system_cmds.podklyucheno")),
             "💬 " + mode_title(ctx.settings["mode"], ctx.lang),
             "💤 AFK: " + (human_duration(time.time() - afk["started_at"], ctx.lang) if afk else ctx.t("system_cmds.vykl")),
             f"🧠 AI: {'✅' if app.ai.available() else '—'} · 🎞 FFmpeg: {'✅' if app.health.ffmpeg_ok else '—'}",
             f"🎬 {ctx.t('system_cmds.ochered_media')}: {app.media.queue.status()['queued']}",
             f"💎 {ctx.plan.upper()} · ⏱ {human_duration(app.uptime, ctx.lang)}"]
    if app.runtime.emergency_stop:
        lines.append("🛑 EMERGENCY STOP")
    if app.runtime.paused_modules:
        lines.append("⏸ " + ", ".join(sorted(app.runtime.paused_modules)))
    await ctx.answer("\n".join(lines), private=ctx.is_business)


@registry.command("ping", "system", aliases=["пинг"], **SYS)
async def cmd_ping(ctx: CommandContext) -> None:
    t0 = time.monotonic()
    tg = await ctx.app.health.check_telegram()
    api_ms = int((time.monotonic() - t0) * 1000)
    lag = ""
    if ctx.message is not None and ctx.message.date:
        lag = f" · {ctx.t('system_cmds.dostavka')} ~{max(0, int(time.time() - ctx.message.date.timestamp()))} s"
    await ctx.answer(f"🏓 Pong! Telegram API: <b>{api_ms} ms</b>{'' if tg.get('ok') else ' ⚠️'}{lag}")


@registry.command("uptime", "system", aliases=["аптайм"], sandbox_safe=True, **SYS)
async def cmd_uptime(ctx: CommandContext) -> None:
    await ctx.answer(f"⏱ {human_duration(ctx.app.uptime, ctx.lang, 3)} · v{__version__}")


@registry.command("about", "system", aliases=["оботе", "haqida"], sandbox_safe=True, **SYS)
async def cmd_about(ctx: CommandContext) -> None:
    await ctx.answer(ctx.t("system_cmds.chat_helper_telegram_business_avtomatizatsiya", v=__version__), private=ctx.is_business)


@registry.command("logs", "system", aliases=["логи"], admin_only=True, **SYS)
async def cmd_logs(ctx: CommandContext) -> None:
    n = int(ctx.args[0]) if ctx.args and ctx.args[0].isdigit() else 20
    rows = ring_handler.query(level="WARNING", limit=min(n, 60))
    text = "\n".join(f"{time.strftime('%H:%M:%S', time.localtime(r['ts']))} {r['level'][0]} {r['logger']}: {r['message']}" for r in reversed(rows)) or "—"
    await ctx.answer("<pre>" + esc(text[-3800:]) + "</pre>", private=True)


@registry.command("clear", "system", aliases=["очистить", "tozala"], **SYS)
async def cmd_clear(ctx: CommandContext) -> None:
    if ctx.parsed.first == "all":
        n = await ctx.app.ai.memory.clear_all(ctx.user_id)
        await ctx.app.chats.clear_previews(ctx.user_id)
    else:
        n = await ctx.app.ai.memory.clear_chat(ctx.user_id, ctx.chat_id)
        await ctx.app.db.execute("UPDATE chat_settings SET last_preview=NULL WHERE user_id=? AND chat_id=?", (ctx.user_id, ctx.chat_id))
    await ctx.answer(ctx.t("system_cmds.ochischeno_zapisey", n=n), private=True)


@registry.command("export", "system", aliases=["экспорт", "eksport"], rate=(3, 3600))
async def cmd_export(ctx: CommandContext) -> None:
    data = await ctx.app.backups.export_user(ctx.user_id)
    blob = json.dumps(data, ensure_ascii=False, indent=1, default=str).encode()
    await ctx.app.bot.send_document(ctx.user_id, BufferedInputFile(blob, f"chat_helper_export_{ctx.user_id}.json"),
                                    caption=ctx.t("system_cmds.vashi_dannye"))
    await ctx.app.audit.log("privacy.export", actor_id=ctx.user_id, target_type="user", target_id=ctx.user_id)
    await ctx.cleanup_command(fallback_text="📦")


_BACKUP_CONFIRM: dict[int, float] = {}


@registry.command("backup", "system", aliases=["бэкап", "zaxira"], rate=(3, 600))
async def cmd_backup(ctx: CommandContext) -> None:
    if not ctx.is_super:
        await cmd_export(ctx)
        return
    _BACKUP_CONFIRM[ctx.user_id] = time.time()
    await ctx.answer(ctx.t("system_cmds.sozdat_rezervnuyu_kopiyu_bazy_prislat"),
                     markup=kb([[("✅ " + ctx.t("system_cmds.sozdat"), "sysbk:ok"), ("✖️", "sysbk:no")]]), private=True)


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


@registry.command("lang", "system", aliases=["язык", "til"], **SYS)
async def cmd_lang(ctx: CommandContext) -> None:
    lang = ctx.parsed.first
    if lang not in ("ru", "uz"):
        raise UsageError()
    await ctx.app.settings.set(ctx.user_id, "lang", lang)
    await ctx.app.users.set_language(ctx.user_id, lang)
    await ctx.answer("🇷🇺 Русский ✅" if lang == "ru" else "🇺🇿 O'zbekcha ✅", private=ctx.is_business)


@registry.command("theme", "system", aliases=["тема", "mavzu"], **SYS)
async def cmd_theme(ctx: CommandContext) -> None:
    t = ctx.parsed.first
    if t not in ("classic", "minimal", "fancy", "emoji"):
        raise UsageError()
    await ctx.app.settings.set(ctx.user_id, "msg_theme", t)
    await ctx.answer(f"🎨 {t} ✅", private=ctx.is_business)


@registry.command("privacy", "system", aliases=["приватность", "maxfiylik"], sandbox_safe=True, **SYS)
async def cmd_privacy(ctx: CommandContext) -> None:
    s = ctx.settings
    await ctx.answer(ctx.t("system_cmds.privatnost_istoriya_ai_hranenie_dn",
                           h=on_off(ctx.lang, s["ai_store_history"]), d=s["history_retention_days"], pv=on_off(ctx.lang, s["store_previews"]),
                           m=on_off(ctx.lang, s["ai_long_memory"]), p=ctx.prefix), private=ctx.is_business)


@registry.command("limits", "system", aliases=["лимиты", "limitlar"], **SYS)
async def cmd_limits(ctx: CommandContext) -> None:
    app = ctx.app
    lim = await app.subs.limits(ctx.user_id)
    used_ai = await app.quotas.used(f"ai:{ctx.user_id}")
    used_media = await app.quotas.used(f"media:{ctx.user_id}")
    f = lambda v: "∞" if v == -1 else str(v)  # noqa: E731
    await ctx.answer(ctx.t("system_cmds.limity_ai_den_media_den",
                           p=ctx.plan.upper(), ua=used_ai, la=f(lim["ai_requests_day"]), um=used_media, lm=f(lim["media_jobs_day"]),
                           mb=app.config.media_max_input_mb, r=f(lim["autoreply_rules"]), a=f(lim["automation_rules"])), private=ctx.is_business)


@registry.command("stats", "system", aliases=["статистика", "statistika"], **SYS)
async def cmd_stats(ctx: CommandContext) -> None:
    from ..handlers.panel import screen_stats
    text, _ = await screen_stats(ctx.app, ctx.user_id, ctx.settings)
    await ctx.answer(text, private=ctx.is_business)


@registry.command("inbox", "system", aliases=["входящие", "kiruvchi"], **SYS)
async def cmd_inbox(ctx: CommandContext) -> None:
    text = await ctx.app.inbox.digest_text(ctx.user_id, ctx.lang, use_ai=ctx.parsed.first == "ai")
    await ctx.answer(text, private=True)


@registry.command("support", "system", aliases=["поддержка", "yordam_so'rov"], rate=(3, 3600))
async def cmd_support(ctx: CommandContext) -> None:
    if not ctx.raw:
        raise UsageError()
    await ctx.app.support_message(ctx.user_id, ctx.raw)
    await ctx.answer(ctx.t("system_cmds.otpravleno_administratoru"), private=True)


@registry.command("timer", "system", aliases=["таймер", "taymer"],
                  where="business", rights=["can_reply"], status=LIMITED_BY_TELEGRAM, rate=(10, 60),
                  )
async def cmd_timer(ctx: CommandContext) -> None:
    if not ctx.args:
        raise UsageError()
    dur = parse_duration(ctx.args[0])
    if not dur or not 5 <= dur <= 7 * 86400:
        raise UsageError(ctx.t("system_cmds.vremya_5_sekund_7_dney"))
    text = ctx.raw.split(None, 1)[1] if len(ctx.raw.split(None, 1)) > 1 else ""
    conn = ctx.conn
    run_at = int(time.time()) + dur
    if text:
        if not conn.can("can_delete_sent_messages") and not conn.can("can_delete_all_messages"):
            raise CommandError(ctx.t("system_cmds.nuzhno_pravo_udalyat_soobscheniya_bota"))
        mid = await ctx.answer(f"⏳ {esc(text)}\n<i>🕒 {human_duration(dur, ctx.lang)}</i>")
        if mid:
            await ctx.app.scheduler.add(ctx.user_id, "timer_delete", {"conn": conn.id, "chat_id": ctx.chat_id, "ids": [mid]}, run_at)
        return
    if ctx.reply is None:
        raise UsageError()
    own = ctx.reply.from_user is not None and ctx.reply.from_user.id == ctx.user_id
    need = "can_delete_all_messages" if own and ctx.reply.sender_business_bot is None else "can_delete_sent_messages"
    if not conn.can(need) and not conn.can("can_delete_all_messages"):
        raise CommandError(ctx.t("system_cmds.hvataet_prava_udalenie_etogo_soobscheniya"))
    if not own and ctx.reply.sender_business_bot is None:
        raise CommandError(ctx.t("system_cmds.mozhno_stavit_taymer_tolko_svoi"))
    await ctx.app.scheduler.add(ctx.user_id, "timer_delete", {"conn": conn.id, "chat_id": ctx.chat_id, "ids": [ctx.reply.message_id]}, run_at)
    await ctx.cleanup_command(fallback_text=f"⏳ {human_duration(dur, ctx.lang)}")
    if not ctx.command_deleted:
        await ctx.app.scheduler.add(ctx.user_id, "timer_delete", {"conn": conn.id, "chat_id": ctx.chat_id, "ids": [ctx.message.message_id]}, run_at)


ACTIONS = {"typing": "typing", "печать": "typing", "voice": "record_voice", "голос": "record_voice", "video": "record_video_note",
           "кружок": "record_video_note", "photo": "upload_photo", "фото": "upload_photo", "doc": "upload_document", "file": "upload_document",
           "location": "find_location", "sticker": "choose_sticker", "videofile": "upload_video"}
MAD_SEQUENCE = ["typing", "record_voice", "upload_photo", "record_video_note", "upload_document", "choose_sticker", "upload_video"]
_ACTIVE_MAD: dict[tuple[int, int], asyncio.Task] = {}


@registry.command("mad", "system", aliases=["action", "печатает", "актив"],
                  where="business", rights=["can_reply"], rate=(4, 60))
async def cmd_mad(ctx: CommandContext) -> None:
    key = (ctx.user_id, ctx.chat_id)
    old = _ACTIVE_MAD.pop(key, None)
    if old and not old.done():
        old.cancel()
    await ctx.cleanup_command()
    if ctx.parsed.first in ("stop", "стоп", "off"):
        return
    secs, chosen = 15, []
    for a in ctx.args:
        if a.isdigit():
            secs = max(5, min(int(a), 60))
        elif a.lower() in ACTIONS:
            chosen.append(ACTIONS[a.lower()])
    seq = chosen or MAD_SEQUENCE

    async def loop() -> None:
        end = time.monotonic() + secs
        i = 0
        try:
            while time.monotonic() < end:
                res = await ctx.app.sender.action(ctx.chat_id, seq[i % len(seq)], bc_id=ctx.bc_id)
                if not res.ok:
                    break
                i += 1
                await asyncio.sleep(min(4.5, max(0.5, end - time.monotonic())))
        finally:
            if _ACTIVE_MAD.get(key) is asyncio.current_task():
                _ACTIVE_MAD.pop(key, None)
    _ACTIVE_MAD[key] = asyncio.create_task(loop())


def _parse_when(ctx: CommandContext) -> tuple[int, str]:
    if len(ctx.args) < 2:
        raise UsageError()
    dur = parse_duration(ctx.args[0])
    if not dur or not 30 <= dur <= 365 * 86400:
        raise UsageError(ctx.t("system_cmds.vremya_30_sekund_goda_10m"))
    return int(time.time()) + dur, ctx.raw.split(None, 1)[1]


async def _reminder_list(ctx: CommandContext) -> None:
    rows = await ctx.app.reminders.list(ctx.user_id)
    tz_name = ctx.settings.get("timezone") or ctx.app.config.timezone
    lines = [ctx.t("system_cmds.napominaniya")]
    for r in rows:
        where = ctx.t("system_cmds.chat") if r["kind"] == "chat" else ctx.t("system_cmds.lichku")
        lines.append(f"#{r['id']} · {fmt_dt(r['run_at'], tz_name)} · {where} · {esc(clip(r['text'], 50))}")
    if not rows:
        lines.append(ctx.t("system_cmds.net_aktivnyh_napominaniy"))
    lines.append(ctx.t("system_cmds.otmenit_remind_del_id", p=ctx.prefix))
    await ctx.answer("\n".join(lines), private=True)


@registry.command("remind", "system", aliases=["напомни", "eslat"], rate=(10, 60))
async def cmd_remind(ctx: CommandContext) -> None:
    sub = ctx.parsed.first
    if sub in ("list", "список", "ro'yxat"):
        await _reminder_list(ctx)
        return
    if sub in ("del", "cancel", "удалить", "o'chir"):
        rid = ctx.args[1] if len(ctx.args) > 1 else ""
        ok = rid.isdigit() and await ctx.app.reminders.cancel(ctx.user_id, int(rid))
        await ctx.answer(ctx.t("system_cmds.otmeneno") if ok else ctx.t("system_cmds.naydeno"), private=True)
        return
    run_at, text = _parse_when(ctx)
    try:
        await ctx.app.reminders.create(ctx.user_id, text, run_at, kind="dm")
    except ValueError as e:
        raise CommandError(ctx.t("system_cmds.udalos_sozdat_napominanie", e=esc(str(e)))) from None
    tz_name = ctx.settings.get("timezone") or ctx.app.config.timezone
    await ctx.answer(ctx.t("system_cmds.napomnyu", t=fmt_dt(run_at, tz_name)), private=True)


@registry.command("remindf", "system", aliases=["напомнивчат", "eslatchat"],
                  where="business",
                  rights=["can_reply"], status=LIMITED_BY_TELEGRAM, rate=(10, 60))
async def cmd_remindf(ctx: CommandContext) -> None:
    run_at, text = _parse_when(ctx)
    try:
        await ctx.app.reminders.create(ctx.user_id, text, run_at, kind="chat", chat_id=ctx.chat_id, connection_id=ctx.conn.id)
    except ValueError as e:
        raise CommandError(ctx.t("system_cmds.udalos_sozdat_napominanie", e=esc(str(e)))) from None
    tz_name = ctx.settings.get("timezone") or ctx.app.config.timezone
    await ctx.cleanup_command(fallback_text="⏰")
    await ctx.app.sender.send_text(ctx.user_id, ctx.t("system_cmds.napominanie_chata",
                                                      c=esc(clip((await ctx.app.chats.get(ctx.user_id, ctx.chat_id) or {}).get("title") or "", 40)),
                                                      t=fmt_dt(run_at, tz_name)))


@registry.command("tpl", "autoreply", aliases=["шаблон", "template", "shablon"], **SYS)
async def cmd_tpl(ctx: CommandContext) -> None:
    db = ctx.app.db
    sub = ctx.parsed.first
    if sub in ("", "list", "список"):
        rows = await db.fetchall("SELECT name, text FROM reply_templates WHERE user_id=? ORDER BY name", (ctx.user_id,))
        body = "\n".join(f"• <b>{esc(r['name'])}</b>: {esc(clip(r['text'], 60))}" for r in rows) or ctx.t("system_cmds.shablonov_net")
        await ctx.answer("📑 " + body, private=ctx.is_business)
        return
    if sub in ("save", "сохранить", "add"):
        parts = split_pipe(ctx.raw.split(None, 1)[1] if len(ctx.raw.split(None, 1)) > 1 else "")
        if len(parts) < 2 or not parts[0] or not parts[1]:
            raise UsageError()
        n = await db.fetchval("SELECT COUNT(*) FROM reply_templates WHERE user_id=?", (ctx.user_id,), 0)
        if n >= 100:
            raise CommandError(ctx.t("system_cmds.maksimum_100_shablonov"))
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
        raise CommandError(ctx.t("system_cmds.shablon_nayden"))
    await ctx.answer(esc(row["text"]))


@registry.command("fav", "system", aliases=["избранное", "sevimli"], sandbox_safe=True, rate=(10, 60))
async def cmd_fav(ctx: CommandContext) -> None:
    from ..handlers.account import QUICK_DEFAULT
    if ctx.parsed.first == "reset":
        await ctx.app.settings.set(ctx.user_id, "favorite_commands", [])
        await ctx.answer(ctx.t("system_cmds.izbrannoe_sbrosheno"), private=ctx.is_business)
        return
    if not ctx.args:
        fav = ctx.settings.get("favorite_commands") or QUICK_DEFAULT
        await ctx.answer("⭐ " + " ".join(f"<code>{ctx.prefix}{c}</code>" for c in fav), private=ctx.is_business)
        return
    ids, unknown = [], []
    for a in ctx.args[:12]:
        spec = ctx.app.registry.resolve(a.lstrip(ctx.prefix).lstrip("."), admin=ctx.is_super)
        (ids if spec else unknown).append(spec.id if spec else a)
    ids = list(dict.fromkeys(ids))
    await ctx.app.settings.set(ctx.user_id, "favorite_commands", ids)
    msg = "⭐ " + " ".join(f"<code>{ctx.prefix}{c}</code>" for c in ids)
    if unknown:
        msg += "\n" + ctx.t("system_cmds.naydeny", u=esc(", ".join(unknown)))
    await ctx.answer(msg, private=ctx.is_business)
