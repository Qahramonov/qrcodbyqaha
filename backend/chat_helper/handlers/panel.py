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

from ..business.rights import inspect, right_title, status_title
from ..commands.registry import CATEGORIES, PLAN_RANK
from ..core.context import AppContext
from ..core.timeutil import fmt_dt, human_duration
from ..keyboards import grid, kb, nav, paginate, pager, toggle
from ..localization import on_off, p, tr
from ..modules.afk import render_afk
from ..modules.autoreply import mode_title
from ..security.sanitize import clip, esc
from ..services.settings import MODES, MSG_THEMES, STYLES
from ..subscriptions.service import plan_description
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
    acc = await access(app, uid)
    if acc.locked:  # defensive: show() already routes locked users to onboarding
        from .onboarding import screen_welcome
        return await screen_welcome(app, uid, s)
    afk = await app.afk.active(uid)
    plan = await app.subs.plan_of(uid)
    user = await app.users.get(uid) or {}
    name = esc(user.get("first_name") or "")
    active = await app.controls.active(uid)
    mutes = sum(1 for r in active if r["module"] in ("mute", "nogif", "nomute"))
    protects = sum(1 for r in active if r["module"] == "protect")
    reminders = len(await app.reminders.list(uid))
    lines = [tr(lang, "panel.chat_helper_vash_pomoschnik_telegram"), "",
             tr(lang, "panel.privet", n=name or "👤"),
             tr(lang, "panel.podklyuchenie",
                s=status_title(acc.conn.status, lang) if acc.conn else tr(lang, "panel.podklyucheno")),
             tr(lang, "panel.rezhim", m=mode_title(s["mode"], lang))]
    if afk:
        lines.append(tr(lang, "panel.afk", d=human_duration(time.time() - afk["started_at"], lang)))
    if mutes or protects or reminders:
        lines.append(tr(lang, "panel.filtrov_zaschischeno_chatov_napominaniy", m=mutes, p=protects, r=reminders))
    if s.get("automation_paused"):
        lines.append(tr(lang, "panel.avtomatizatsiya_pauze"))
    lines.append(tr(lang, "panel.tarif", p=plan.upper()))
    if app.runtime.emergency_stop:
        lines.append(p(lang, "emergency"))
    items = [
        (tr(lang, "panel.moy_akkaunt"), "m:account"),
        (tr(lang, "panel.moi_chaty"), "m:chats"),
        (tr(lang, "panel.bystrye_komandy"), "m:quick"),
        (tr(lang, "panel.ai_assistant_2"), "m:ai"),
        (tr(lang, "panel.ai_dvoynik"), "m:twin"),
        (tr(lang, "panel.avtootvetchik_2"), "m:autoreply"),
        ("💤 AFK", "m:afk"),
        ("🔕 Mute Manager", "m:mutes"),
        ("🛡 Protect Manager", "m:protects"),
        ("🎬 Media Studio", "m:media"),
        (tr(lang, "panel.igry_2"), "m:games"),
        ("📝 Text Tools", "m:texttools"),
        (tr(lang, "panel.napominaniya"), "m:reminders"),
        (tr(lang, "panel.statistika"), "m:stats"),
        (tr(lang, "panel.podpiska_2"), "m:sub"),
        (tr(lang, "panel.nastroyki_2"), "m:settings"),
        (tr(lang, "panel.pomosch_2"), "m:help"),
        (tr(lang, "panel.profil"), "m:profile"),
    ]
    rows = grid(items, 2)
    if acc.is_super:
        rows.append([(tr(lang, "panel.super_admin"), "m:admin")])
    return "\n".join(lines), kb(rows)


async def screen_inspector(app: AppContext, uid: int, s: dict[str, Any], idx: int) -> tuple[str, Any]:
    lang = s["lang"]
    conns = await app.connections.for_user(uid)
    if idx >= len(conns):
        from .onboarding import screen_connect
        return await screen_connect(app, uid, s)
    c = conns[idx]
    from ..business.rights import command_dependencies
    rep = inspect(c.rights, c.is_enabled, lang, c.paused)
    deps = command_dependencies(app.registry)
    snap = await app.db.fetchone("SELECT created_at FROM permission_snapshots WHERE connection_id=? ORDER BY id DESC LIMIT 1", (c.id,))
    lines = [tr(lang, "panel.permission_inspector"), rep["status_title"],
             tr(lang, "panel.poslednee_obnovlenie_prav",
                t=fmt_dt((snap or {}).get("created_at") or c.connected_at, s["timezone"])), "",
             tr(lang, "panel.prava")]
    for right in ("can_reply", "can_read_messages", "can_delete_sent_messages", "can_delete_all_messages", "can_edit_name",
                  "can_edit_bio", "can_edit_profile_photo", "can_edit_username", "can_manage_stories"):
        cmds = deps.get(right) or []
        tail = (" · " + ", ".join(s["prefix"] + x for x in cmds[:6]) + ("…" if len(cmds) > 6 else "")) if cmds else ""
        lines.append(("✅ " if c.rights.get(right) else "❌ ") + right_title(right, lang) + esc(tail))
    lines += ["", tr(lang, "panel.vozmozhnosti")]
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
    lines = [tr(lang, "panel.ai_assistant"), "",
             tr(lang, "panel.provaydery", p=", ".join(provs) if provs else tr(lang, "panel.nastroeny")),
             tr(lang, "panel.stil", s=s["ai_style"]),
             tr(lang, "panel.segodnya_zaprosov", r=usage["today_requests"], c=f"{usage['today_cost']:.4f}"),
             tr(lang, "panel.limit_den", l=usage["daily_limit"] if usage["daily_limit"] is not None else "∞"), "",
             tr(lang, "panel.pishite_mne_lyuboy_vopros_otvechu", p=s["prefix"])]
    rows = [
        [toggle(tr(lang, "panel.ai_avtootvet"), s["mode"] in ("ai", "hybrid"), "mode:" + ("manual" if s["mode"] in ("ai", "hybrid") else "ai")),
         toggle(tr(lang, "panel.gibrid"), s["mode"] == "hybrid", "mode:hybrid")],
        [toggle(tr(lang, "panel.podtverzhdat_otvety"), s["ai_confirm"], "tg:ai_confirm")],
        [toggle(tr(lang, "panel.dolgaya_pamyat"), s["ai_long_memory"], "tg:ai_long_memory"),
         toggle(tr(lang, "panel.istoriya"), s["ai_store_history"], "tg:ai_store_history")],
        [toggle(tr(lang, "panel.rasshifrovka_golosovyh"), s["ai_auto_transcribe"], "tg:ai_auto_transcribe")],
        [toggle(tr(lang, "panel.dnevnaya_svodka"), s["ai_daily_summary"], "tg:ai_daily_summary"),
         toggle(tr(lang, "panel.prioritety"), s["ai_priority_detection"], "tg:ai_priority_detection")],
        [(f"{'▶️ ' if st == s['ai_style'] else ''}{st}", f"ai:style:{st}") for st in STYLES[:4]],
        [(f"{'▶️ ' if st == s['ai_style'] else ''}{st}", f"ai:style:{st}") for st in STYLES[4:]],
        [(tr(lang, "panel.playground"), "ai:pg"), (tr(lang, "panel.pamyat"), "ai:mem")],
        [(tr(lang, "panel.ochistit_pamyat"), "ai:clear")],
        nav(lang),
    ]
    return "\n".join(lines), kb(rows)


async def screen_ai_memory(app: AppContext, uid: int, s: dict[str, Any]) -> tuple[str, Any]:
    lang = s["lang"]
    facts = await app.ai.memory.list(uid, limit=30)
    lines = [tr(lang, "panel.sohranyonnye_fakty")]
    if not facts:
        lines.append(tr(lang, "panel.pusto_dobavit_remember_fakt", p=s["prefix"]))
    for f in facts:
        lines.append(f"• #{f['id']} {esc(clip(f['content'], 120))}")
    if not s["ai_long_memory"]:
        lines += ["", tr(lang, "panel.dolgaya_pamyat_vyklyuchena_novye_fakty")]
    return "\n".join(lines), kb([[(tr(lang, "panel.ochistit_vsyo"), "ai:clear")], nav(lang, "m:ai")])


async def screen_autoreply(app: AppContext, uid: int, s: dict[str, Any], page: int = 0) -> tuple[str, Any]:
    lang = s["lang"]
    rules = await app.autoreply.rules(uid)
    part, page, pages = paginate(rules, page, 6)
    lines = [tr(lang, "panel.avtootvetchik"), tr(lang, "panel.rezhim_2", m=mode_title(s["mode"], lang)), "",
             tr(lang, "panel.pravila", n=len(rules))]
    rows: list[list[tuple[str, str]]] = []
    for m in MODES:
        pass
    rows += grid([(("▶️ " if m == s["mode"] else "") + mode_title(m, lang).split(" — ")[0], f"mode:{m}") for m in MODES], 2)
    for r in part:
        lines.append(f"{'🟢' if r['enabled'] else '⚪️'} #{r['id']} {esc(clip(r['pattern'] or r['trigger_type'], 30))} → {esc(clip(r['response'], 40))}")
        rows.append([(("⏸ " if r["enabled"] else "▶️ ") + f"#{r['id']}", f"ar:tog:{r['id']}"), (f"🗑 #{r['id']}", f"ar:del:{r['id']}")])
    if pager("ar:list", page, pages):
        rows.append(pager("ar:list", page, pages))
    rows.append([(tr(lang, "panel.pravilo"), "ar:add"), (tr(lang, "panel.privetstvie"), "ar:welcome")])
    rows.append([toggle(tr(lang, "panel.privetstvie_2"), s["welcome_enabled"], "tg:welcome_enabled"),
                 toggle(tr(lang, "panel.pauza"), s["automation_paused"], "tg:automation_paused")])
    lines += ["", tr(lang, "panel.rabochie_chasy_rezhim_biznes_izmenit",
                     a=s["work_start"], b=s["work_end"], p=s["prefix"])]
    rows.append(nav(lang))
    return "\n".join(lines), kb(rows)


async def screen_afk(app: AppContext, uid: int, s: dict[str, Any]) -> tuple[str, Any]:
    lang = s["lang"]
    sess = await app.afk.active(uid)
    st = await app.afk.stats(uid)
    lines = ["💤 <b>AFK</b>", ""]
    if sess:
        lines.append(tr(lang, "panel.status_vklyuchyon", d=human_duration(time.time() - sess["started_at"], lang)))
        if sess.get("reason"):
            lines.append(tr(lang, "panel.prichina", r=esc(sess["reason"])))
        if sess.get("ends_at"):
            lines.append(tr(lang, "panel.text", t=fmt_dt(sess["ends_at"], s["timezone"])))
        lines.append(tr(lang, "panel.soobscheniy_otvetov", m=sess["messages_received"], r=sess["replies_sent"]))
    else:
        lines.append(tr(lang, "panel.status_vyklyuchen"))
    lines += ["", tr(lang, "panel.vsego_sessiy_vremeni",
                     n=st.get("sessions", 0), t=human_duration(st.get("total_sec", 0) or 0, lang))]
    rows = []
    if sess:
        rows.append([(tr(lang, "panel.vyklyuchit_afk"), "afk:off")])
    else:
        rows.append([(tr(lang, "panel.vklyuchit"), "afk:on:0"), ("30m", "afk:on:1800"), ("1h", "afk:on:3600"), ("3h", "afk:on:10800")])
        rows.append([(tr(lang, "panel.utra"), "afk:sleep")])
    rows.append([(tr(lang, "panel.prichina_2"), "afk:reason"), (tr(lang, "panel.predprosmotr"), "afk:preview")])
    rows.append([(("▶️ " if t == s["msg_theme"] else "") + t, f"afk:theme:{t}") for t in MSG_THEMES])
    rows.append([toggle(tr(lang, "panel.avto_vykl"), s["afk_auto_off"], "tg:afk_auto_off"),
                 toggle("AI", s["afk_ai"], "tg:afk_ai")])
    rows.append([toggle(tr(lang, "panel.svodka"), s["afk_notify_summary"], "tg:afk_notify_summary"),
                 (tr(lang, "panel.interval_m", m=s["afk_cooldown_min"]), "afk:cd")])
    lines += ["", tr(lang, "panel.isklyuchenie_chata_napishite_nyom_ignore", p=s["prefix"])]
    rows.append(nav(lang))
    return "\n".join(lines), kb(rows)


async def screen_media(app: AppContext, uid: int, s: dict[str, Any]) -> tuple[str, Any]:
    lang = s["lang"]
    used = await app.quotas.used(f"media:{uid}")
    lim = await app.subs.limit(uid, "media_jobs_day")
    pre = s["prefix"]
    lines = ["🎬 <b>Media Studio</b>", "",
             tr(lang, "panel.otvette_komandoy_media_lyubom_chate"),
             f"<code>{pre}reverse</code> · <code>{pre}speed 2</code> · <code>{pre}ld 25</code> · <code>{pre}ramka gold</code>",
             f"<code>{pre}{esc(tr(lang, 'panel.meme_example'))}</code> · <code>{pre}blur</code> · <code>{pre}circle</code> · <code>{pre}gif</code>",
             f"<code>{pre}mp3</code> · <code>{pre}voice</code> · <code>{pre}sticker</code> · <code>{pre}trim 0:05 0:15</code>", "",
             tr(lang, "panel.ffmpeg", f="✅" if app.health.ffmpeg_ok else "❌ pkg install ffmpeg"),
             tr(lang, "panel.segodnya_zadach_maks_mb",
                u=used, l=lim if lim is not None else "∞", mb=app.config.media_max_input_mb)]
    rows = [[toggle(tr(lang, "panel.modul_vklyuchyon"), s["media_enabled"], "tg:media_enabled")],
            [toggle(tr(lang, "panel.udalyat_komandy_chata"), s["delete_commands"], "tg:delete_commands")],
            [(tr(lang, "panel.vse_media_komandy"), "cmd:cat:media:0")],
            nav(lang)]
    return "\n".join(lines), kb(rows)


async def screen_games(app: AppContext, uid: int, s: dict[str, Any]) -> tuple[str, Any]:
    lang = s["lang"]
    top = await app.games.leaderboard(uid, None, limit=5)
    lines = [tr(lang, "panel.igry"), "",
             tr(lang, "panel.zapuskayte_chate_sobesednikom_zdes_so"),
             " · ".join(f"<code>{s['prefix']}{g}</code>" for g in ("duel", "revo", "ttt", "rps", "quiz", "dice", "slot", "coin", "guess",
                                                                   "mathgame", "wordgame", "reaction", "challenge", "rd")), "",
             tr(lang, "panel.lidery")]
    if not top:
        lines.append(tr(lang, "panel.poka_net_rezultatov"))
    for i, r in enumerate(top, 1):
        lines.append(f"{i}. {esc(r['name'] or r['player_id'])} — {r['wins']}W/{r['losses']}L · {r['rating']}")
    lines += ["", tr(lang, "panel.vse_igry_razvlekatelnye_bez_stavok")]
    rows = [[toggle(tr(lang, "panel.igry_vklyucheny"), s["games_enabled"], "tg:games_enabled")],
            [(tr(lang, "panel.komandy_igr"), "cmd:cat:games:0")], nav(lang)]
    return "\n".join(lines), kb(rows)


async def screen_commands(app: AppContext, uid: int, s: dict[str, Any]) -> tuple[str, Any]:
    lang = s["lang"]
    cats = app.registry.by_category()
    lines = [tr(lang, "panel.komandy", n=len(app.registry)),
             tr(lang, "panel.prefiks_pishite_lyubom_chate_biznes", p=s["prefix"])]
    items = [(f"{CATEGORIES[c][0]} {tr(lang, CATEGORIES[c][1])} ({len(v)})", f"cmd:cat:{c}:0")
             for c, v in cats.items() if v and c in CATEGORIES]
    rows = grid(items, 2)
    rows.append(nav(lang))
    return "\n".join(lines), kb(rows)


async def screen_cmd_cat(app: AppContext, uid: int, s: dict[str, Any], cat: str, page: int) -> tuple[str, Any]:
    lang = s["lang"]
    specs = sorted(app.registry.by_category().get(cat, []), key=lambda x: x.id)
    part, page, pages = paginate(specs, page, 8)
    disabled = set(s.get("disabled_commands") or [])
    emoji, key = CATEGORIES.get(cat, ("•", None))
    lines = [f"{emoji} <b>{tr(lang, key) if key else cat}</b>", ""]
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
             tr(lang, "panel.sintaksis", x=esc(d["syntax"]))]
    if d["aliases"]:
        lines.append(tr(lang, "panel.aliasy", a=esc(", ".join(d["aliases"]))))
    for ex in d["examples"][:3]:
        lines.append(f"• <code>{esc(ex.replace('.', s['prefix'], 1))}</code>")
    lines.append(tr(lang, "panel.tarif_status", p=d["min_plan"].upper(), st=d["status"]))
    if d["rights"]:
        lines.append(tr(lang, "panel.prava_2", r=", ".join(d["rights"])))
    if d["notes"]:
        lines.append("ℹ️ " + esc(d["notes"]))
    rows = [[toggle(tr(lang, "panel.komanda_vklyuchena"), on, f"cmd:tog:{sp.id}")], nav(lang, f"cmd:cat:{sp.category}:0")]
    return "\n".join(lines), kb(rows)


async def screen_profile(app: AppContext, uid: int, s: dict[str, Any]) -> tuple[str, Any]:
    lang = s["lang"]
    info = await app.profile.current(uid)
    conn = await app.connections.primary_for_user(uid)
    lines = [tr(lang, "panel.profil_biznes_akkaunta"), "",
             tr(lang, "panel.imya", n=esc(info.get("first_name") or "—")),
             tr(lang, "panel.familiya", n=esc(info.get("last_name") or "—")),
             tr(lang, "panel.bio", b=esc(info.get("bio") or "—")),
             tr(lang, "panel.chasy", c=on_off(lang, s["clock_enabled"]))]
    if conn is None:
        lines += ["", tr(lang, "panel.podklyuchite_biznes_akkaunt_chtoby_menyat")]
    else:
        for r, t in (("can_edit_name", tr(lang, "panel.imya_2")), ("can_edit_bio", "bio"), ("can_edit_profile_photo", tr(lang, "panel.foto"))):
            if not conn.can(r):
                lines.append(tr(lang, "panel.net_prava_menyat", t=t))
    rows = [[(tr(lang, "panel.imya_3"), "pr:name"), ("✏️ Bio", "pr:bio"), (tr(lang, "panel.avatar"), "pr:avatar")],
            [(tr(lang, "panel.bekap"), "pr:backup"), (tr(lang, "panel.vosstanovit"), "pr:restore"),
             (tr(lang, "panel.istoriya_2"), "pr:hist")],
            [toggle(tr(lang, "panel.chasy_profile"), s["clock_enabled"], "tg:clock_enabled"),
             ((f"→ {s['clock_field']}"), "pr:clockfield")],
            nav(lang)]
    lines += ["", tr(lang, "panel.postoyannyy_status_onlayn_nedostupen_bot")]
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
    lines = [tr(lang, "panel.statistika_segodnya_7_dney"), ""]
    for k, (a, b) in vals.items():
        lines.append(f"{tr(lang, 'panel.stat.' + k)}: <b>{a}</b> / {b}")
    chats = await app.chats.list(uid, page_size=1)
    unanswered = await app.inbox.unanswered(uid, 100)
    lines += ["", tr(lang, "panel.chatov_zhdut_otveta", c=chats["total"], u=len(unanswered))]
    return "\n".join(lines), kb([[(tr(lang, "panel.smart_inbox"), "inbox")], nav(lang)])


async def screen_privacy(app: AppContext, uid: int, s: dict[str, Any]) -> tuple[str, Any]:
    lang = s["lang"]
    lines = [tr(lang, "panel.privatnost"), "",
             tr(lang, "panel.my_hranim_polnuyu_perepisku_ai",
                d=s["history_retention_days"])]
    rows = [[(("▶️ " if s["history_retention_days"] == d else "") + tr(lang, "panel.dn", d=d), f"pv:ret:{d}") for d in (0, 1, 7, 30)],
            [toggle(tr(lang, "panel.istoriya_ai"), s["ai_store_history"], "tg:ai_store_history"),
             toggle(tr(lang, "panel.prevyu"), s["store_previews"], "tg:store_previews")],
            [toggle(tr(lang, "panel.dolgaya_pamyat_soglasie"), s["ai_long_memory"], "tg:ai_long_memory")],
            [(tr(lang, "panel.eksport_dannyh"), "pv:export")],
            [(tr(lang, "panel.udalit_vse_moi_dannye"), "pv:del")],
            nav(lang)]
    return "\n".join(lines), kb(rows)


async def screen_sub(app: AppContext, uid: int, s: dict[str, Any]) -> tuple[str, Any]:
    lang = s["lang"]
    plan = await app.subs.plan_of(uid)
    sub = await app.subs.active_subscription(uid)
    limits = await app.subs.limits(uid)
    lines = [tr(lang, "panel.podpiska"), tr(lang, "panel.tarif_2", p=plan.upper())]
    if sub and sub.get("expires_at"):
        lines.append(tr(lang, "panel.deystvuet", d=fmt_dt(sub["expires_at"], s["timezone"])))
    lines.append("")
    for k in ("ai_requests_day", "media_jobs_day", "autoreply_rules", "automation_rules"):
        v = limits.get(k)
        lines.append(f"• {tr(lang, 'panel.limit.' + k)}: {'∞' if v == -1 else v}")
    lines.append("")
    rows = []
    for pl in app.subs.plans():
        if pl["id"] == "free":
            continue
        lines.append(f"<b>{esc(pl['name'])}</b> — {pl['price_stars']} ⭐️ / {pl['duration_days']} {tr(lang, 'panel.dn_2')}: {esc(plan_description(pl, lang))}")
        if app.config.payments_enabled and pl["price_stars"] > 0 and PLAN_RANK.get(pl["id"], 0) >= PLAN_RANK.get(plan, 0):
            rows.append([(tr(lang, "panel.kupit", n=pl["name"]), f"sub:buy:{pl['id']}")])
    if not app.config.payments_enabled:
        lines += ["", tr(lang, "panel.oplata_stars_poka_vklyuchena_vladeltsem")]
    rows.append([(tr(lang, "panel.promokod"), "sub:promo"), (tr(lang, "panel.probnyy_3_dnya"), "sub:trial")])
    rows.append(nav(lang))
    return "\n".join(lines), kb(rows)


async def screen_settings(app: AppContext, uid: int, s: dict[str, Any]) -> tuple[str, Any]:
    lang = s["lang"]
    lines = [tr(lang, "panel.nastroyki"), "",
             tr(lang, "panel.yazyk_prefiks_chasovoy_poyas",
                l=lang.upper(), p=s["prefix"], tz=s["timezone"]),
             tr(lang, "panel.pauza_posle_vashego_otveta_min", m=s["owner_pause_minutes"])]
    rows = [[(("▶️ " if lang == "ru" else "") + "🇷🇺 Русский", "st:lang:ru"), (("▶️ " if lang == "uz" else "") + "🇺🇿 O'zbekcha", "st:lang:uz")],
            [(("▶️ " if s["prefix"] == x else "") + x, f"st:prefix:{x}") for x in PREFIXES],
            [(("▶️ " if s["owner_pause_minutes"] == m else "") + f"⏸{m}", f"st:pause:{m}") for m in (0, 5, 15, 30, 60)],
            [toggle(tr(lang, "panel.vazhnye_soobscheniya"), s["notify_important"], "tg:notify_important"),
             toggle(tr(lang, "panel.novye_chaty"), s["notify_new_chats"], "tg:notify_new_chats")],
            [toggle(tr(lang, "panel.otklyuchenie_bota"), s["notify_disconnect"], "tg:notify_disconnect"),
             toggle(tr(lang, "panel.udalyat_komandy"), s["delete_commands"], "tg:delete_commands")],
            [(tr(lang, "panel.chasovoy_poyas"), "st:tzmenu")],
            [(tr(lang, "panel.prilozhenie_ustroystva"), "m:app")],
            nav(lang)]
    return "\n".join(lines), kb(rows)


async def screen_app(app: AppContext, uid: int, s: dict[str, Any]) -> tuple[str, Any]:
    lang = s["lang"]
    sessions = await app.auth.sessions(uid)
    lines = [tr(lang, "panel.chat_helper_control"), "",
             tr(lang, "panel.android_prilozhenie_upravleniya_botom_ustanovite"),
             tr(lang, "panel.adres_servera_prilozhenii_http_127",
                port=app.config.api_port), "",
             tr(lang, "panel.ustroystva", n=len(sessions))]
    rows = [[(tr(lang, "panel.kod_vhoda"), "app:pair")]]
    for ss in sessions[:6]:
        lines.append(f"• {esc(ss['device_name'] or ss['device_id'])} · {fmt_dt(ss['last_used_at'] or ss['created_at'], s['timezone'])}")
        rows.append([(tr(lang, "panel.otklyuchit", d=clip(ss["device_name"] or ss["device_id"], 18)), f"app:rev:{ss['id']}")])
    rows.append(nav(lang))
    return "\n".join(lines), kb(rows)


async def screen_help(app: AppContext, uid: int, s: dict[str, Any]) -> tuple[str, Any]:
    lang = s["lang"]
    pre = s["prefix"]
    lines = [tr(lang, "panel.pomosch"), "",
             tr(lang, "panel.kak_rabotaet_chat_helper_podklyuchaetsya"), "",
             tr(lang, "panel.komandy_pishite_pryamo_chate_afk", p=pre),
             tr(lang, "panel.komanda_zamenyaetsya_rezultatom_udalyaetsya_esli"), "",
             tr(lang, "panel.ogranicheniya_telegram_bot_otvechaet_tolko"), "",
             tr(lang, "panel.polnyy_spisok_help_razdel_komandy", p=pre)]
    rows = [[(tr(lang, "panel.podklyuchenie_2"), "m:connect"), (tr(lang, "panel.instruktsiya"), "ob:guide")],
            [(tr(lang, "panel.napisat_podderzhku"), "help:support")], nav(lang)]
    return "\n".join(lines), kb(rows)


for _name, _fn in {
    "home": screen_home, "ai": screen_ai, "autoreply": screen_autoreply, "afk": screen_afk,
    "media": screen_media, "games": screen_games, "commands": screen_commands, "profile": screen_profile,
    "stats": screen_stats, "privacy": screen_privacy, "sub": screen_sub, "settings": screen_settings,
    "app": screen_app, "help": screen_help,
}.items():
    register_screen(_name, _fn, public=_name in ("help", "app"))


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
    if arg.startswith("bizChat"):
        from .chatmgr import open_from_deeplink
        await open_from_deeplink(app, uid, arg, message)
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
    await message.answer(tr(s["lang"], "panel.otmeneno_menyu_menu"))


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
        await target.answer(tr(lang, "panel.slishkom_mnogo_kodov_poprobuyte_pozzhe",
                               s=e.retry_after or 60))
        return
    await target.answer(tr(lang, "panel.kod_chat_helper_control_deystvuet",
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
        await cb.answer(tr(s["lang"], "panel.vy_dayote_soglasie_hranit_fakty"), show_alert=True)
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
        await app.afk.enable(uid, tr(lang, "panel.son"), kind="sleep", ends_at=next_occurrence(8, 0, s["timezone"]))
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
        await cb.message.answer(tr(lang, "panel.napishite_prichinu_otsutstviya_cancel"))
        return
    elif action == "preview":
        await cb.answer()
        user = await app.users.get(uid) or {}
        from ..core.timeutil import day_part
        sess = await app.afk.active(uid)
        text = render_afk(s["msg_theme"], lang, name=user.get("first_name") or "Owner", reason=(sess or {}).get("reason") or tr(lang, "panel.zanyat_delami"),
                          away=int(time.time() - (sess or {}).get("started_at", time.time() - 8040)), until_ts=(sess or {}).get("ends_at"),
                          tz_name=s["timezone"], part=day_part(s["timezone"]), kind=(sess or {}).get("kind", "afk"))
        await cb.message.answer(tr(lang, "panel.tak_uvidyat_sobesedniki") + "\n\n" + text)
        return
    await show(app, uid, "afk", cb.message, True)


@router.message(StateFilter(PS.afk_reason), F.text)
async def st_afk_reason(message: Message, state: FSMContext, app: AppContext) -> None:
    uid = await _ensure_user(app, message)
    await state.clear()
    sess = await app.afk.active(uid)
    await app.afk.enable(uid, message.text[:300], ends_at=(sess or {}).get("ends_at"))   # keeps an existing timer
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
        await cb.message.answer(tr(lang, "panel.klyuchevye_slova_cherez_zapyatuyu_naprimer"))
        return
    if action == "welcome":
        await cb.answer()
        await state.set_state(PS.welcome_text)
        await cb.message.answer(tr(lang, "panel.tekst_privetstviya_novyh_sobesednikov_mozhno"))
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
    await message.answer(tr(s["lang"], "panel.teper_tekst_otveta"))


@router.message(StateFilter(PS.rule_response), F.text)
async def st_rule_response(message: Message, state: FSMContext, app: AppContext) -> None:
    uid = await _ensure_user(app, message)
    s = await app.settings.all(uid)
    data = await state.get_data()
    await state.clear()
    try:
        rule = await app.autoreply.add_rule(uid, {"trigger_type": "keyword", "pattern": data.get("keyword", ""),
                                                  "response": message.text, "cooldown_sec": s["autoreply_cooldown_sec"]})
        await message.answer(tr(s["lang"], "panel.pravilo_sozdano", i=rule["id"]))
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
        await cb.answer(tr(lang, "panel.udaleno_zapisey", n=n), show_alert=True)
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
        await cb.message.answer(tr(lang, "panel.ai_playground_pishite_soobscheniya_ya"))
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
                await message.answer(tr(s["lang"], "panel.napishite_vopros_posle_compare"))
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
        "name": (PS.profile_name, tr(lang, "panel.novoe_imya_format_imya_familiya")),
        "bio": (PS.profile_bio, tr(lang, "panel.novoe_bio_140_simvolov_chtoby")),
        "avatar": (PS.profile_avatar, tr(lang, "panel.prishlite_foto_avatara_cancel")),
    }
    if action in prompts:
        await cb.answer()
        st, txt = prompts[action]
        await state.set_state(st)
        await cb.message.answer(txt)
        return
    if action == "backup":
        res = await app.profile.backup(uid)
        await cb.answer(tr(lang, "panel.sohraneno") if res else "—", show_alert=False)
        return
    if action == "restore":
        await cb.answer()
        await app.profile.restore_flow(uid, cb.message)
        return
    if action == "hist":
        await cb.answer()
        rows = await app.profile.history(uid, 15)
        lines = [tr(lang, "panel.istoriya_izmeneniy_profilya")]
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
                                         caption=tr(lang, "panel.vashi_dannye_chat_helper"))
        await app.audit.log("privacy.export", actor_id=uid, target_type="user", target_id=uid)
    elif action == "del":
        await cb.answer()
        await _render_custom(cb.message, tr(lang, "panel.udalit_vse_vashi_dannye_nastroyki"),
                             kb([[(tr(lang, "panel.da_udalit_navsegda"), "pv:del2")], nav(lang, "m:privacy")]))
    elif action == "del2":
        await app.users.delete_user_data(uid)
        app.settings.invalidate(uid)
        app.autoreply._rules_cache.pop(uid, None)
        app.afk._active_cache.pop(uid, None)
        app.connections.invalidate()
        await app.audit.log("privacy.delete_all", actor_id=uid, target_type="user", target_id=uid)
        await cb.answer(p(lang, "done"), show_alert=True)
        await _render_custom(cb.message, tr(lang, "panel.dannye_udaleny_start_nachat_zanovo"), None)
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
            await cb.answer(tr(lang, "panel.oplata_vklyuchena"), show_alert=True)
            return
        await cb.answer()
        try:
            await app.payments.send_invoice(uid, parts[2], lang)
        except ValueError as e:
            await cb.message.answer(f"⚠️ {esc(str(e))}")
    elif action == "promo":
        await cb.answer()
        await state.set_state(PS.promo)
        await cb.message.answer(tr(lang, "panel.vvedite_promokod_cancel"))
    elif action == "trial":
        try:
            await app.subs.start_trial(uid)
            await cb.answer(tr(lang, "panel.probnyy_plus_3_dnya_aktivirovan"), show_alert=True)
        except ValueError:
            await cb.answer(tr(lang, "panel.probnyy_period_ispolzovan_podpiska_aktivna"), show_alert=True)
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
        await message.answer(tr(s["lang"], "panel.promokod_aktivirovan",
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
            await _render_custom(cb.message, tr(s["lang"], "panel.vyberite_chasovoy_poyas"), kb(rows))
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
        await cb.message.answer(tr(s["lang"], "panel.opishite_vopros_odnim_soobscheniem_cancel"))


@router.message(StateFilter(PS.support), F.text)
async def st_support(message: Message, state: FSMContext, app: AppContext) -> None:
    uid = await _ensure_user(app, message)
    s = await app.settings.all(uid)
    await state.clear()
    await app.support_message(uid, message.text)
    await message.answer(tr(s["lang"], "panel.soobschenie_otpravleno_administratoru"))


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
        await cb.message.answer(tr(s["lang"], "panel.tekst_rassylki_html_budet_sozdan"))
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
    await message.answer(tr(s["lang"], "panel.chernovik_sozdan_zapustit", b=bid),
                         reply_markup=kb([[(tr(s["lang"], "panel.zapustit"), f"bc:start:{bid}"),
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
        await message.answer(tr(s["lang"], "panel.otkroyte_menyu_menu_komandy_help",
                                p=s["prefix"]))
