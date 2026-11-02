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
TEXT_TOOLS = ["calc", "fix", "r", "morse", "ball", "upper", "translate", "base64", "hash", "password", "qr", "uuid", "time", "geo"]


class AC(StatesGroup):
    reminder = State()
    whitelist = State()


def _t(lang: str):
    return lambda key, **kw: tr(lang, key, **kw)


@screen("account")
async def screen_account(app: Any, uid: int, s: dict[str, Any]) -> tuple[str, Any]:
    lang = s["lang"]
    t = _t(lang)
    u = await app.users.get(uid) or {}
    acc = await access(app, uid)
    plan = await app.subs.plan_of(uid)
    grants = [k for k, v in (await app.delegation.grants(uid)).items() if v["active"]]
    lines = [t("account.moy_akkaunt"), "",
             f"🆔 <code>{uid}</code>" + (f" · @{esc(u['username'])}" if u.get("username") else ""),
             t("account.imya", n=esc(u.get("first_name") or "—")),
             t("account.podklyuchenie", s=status_title(acc.conn.status, lang) if acc.conn else t("account.net")),
             t("account.tarif_yazyk", p=plan.upper(), l=lang.upper()),
             t("account.delegirovanie_administratoru", d=", ".join(grants) if grants else t("account.net_2"))]
    rows = [[(t("account.podklyuchenie_prava"), "m:connect")],
            [(t("account.delegirovanie_2"), "m:delegation"), (t("account.privatnost_dannye"), "m:privacy")],
            [(t("account.prilozhenie_ustroystva"), "m:app"), (t("account.podpiska"), "m:sub")],
            [(t("account.yazyk"), "m:lang"), (t("account.menyu"), "m:home")]]
    return "\n".join(lines), kb(rows)


@screen("delegation")
async def screen_delegation(app: Any, uid: int, s: dict[str, Any]) -> tuple[str, Any]:
    lang = s["lang"]
    t = _t(lang)
    grants = await app.delegation.grants(uid)
    lines = [t("account.delegirovanie"),
             t("account.vy_mozhete_dobrovolno_razreshit_administratoru"), ""]
    rows = []
    for scope, title in SCOPES.items():
        on = bool(grants.get(scope, {}).get("active"))
        lines.append(("🟢 " if on else "⚪️ ") + tr(lang, title))
        rows.append([(("⏹ " if on else "▶️ ") + tr(lang, title).split(" ", 1)[1][:30], f"dg:{scope}")])
    rows.append([(t("account.moy_akkaunt_2"), "m:account")])
    return "\n".join(lines), kb(rows)


@screen("quick")
async def screen_quick(app: Any, uid: int, s: dict[str, Any]) -> tuple[str, Any]:
    lang = s["lang"]
    t = _t(lang)
    fav = s.get("favorite_commands") or QUICK_DEFAULT
    lines = [t("account.bystrye_komandy"),
             t("account.nazhmite_chtoby_skopirovat_komandu_vstavte"), ""]
    rows = []
    for cid in fav[:12]:
        spec = app.registry.get(cid, admin=app.users.is_super_id(uid))
        if spec is None:
            continue
        lines.append(f"<code>{s['prefix']}{cid}</code> — {esc(clip(spec.describe(lang), 70))}")
        rows.append((f"{s['prefix']}{cid}", f"copy:{s['prefix']}{cid} "))
    grid_rows = [rows[i:i + 3] for i in range(0, len(rows), 3)]
    grid_rows += [[(t("account.afk_vkl_vykl"), "qk:afk"), (t("account.pauza_avtomatiki"), "qk:pause")],
                  [(t("account.studiya_animatsiy"), "qk:anim"), (t("account.vse_komandy"), "m:commands")],
                  [(t("account.izmenit_izbrannoe"), "qk:fav"), (t("account.menyu"), "m:home")]]
    return "\n".join(lines), kb(grid_rows)


@screen("mutes")
async def screen_mutes(app: Any, uid: int, s: dict[str, Any]) -> tuple[str, Any]:
    lang = s["lang"]
    t = _t(lang)
    tz = s.get("timezone") or app.config.timezone
    ms = await app.filters.mute_settings(uid, 0)
    lines = [t("account.mute_manager"),
             t("account.mute_udalyaet_novye_vhodyaschie_soobscheniya", p=s["prefix"]), ""]
    rows = []
    active = [r for r in await app.controls.active(uid) if r["module"] in ("mute", "nogif", "nomute")]
    if not active:
        lines.append(t("account.seychas_net_aktivnyh_filtrov"))
    for r in active[:10]:
        title = esc(clip(((await app.chats.get(uid, r["chat_id"])) or {}).get("title") or str(r["chat_id"]), 28))
        icon = {"mute": "🔕", "nogif": "🚫", "nomute": "🧹"}[r["module"]]
        until = fmt_dt(r["until_at"], tz, with_date=False) if r.get("until_at") else "∞"
        lines.append(f"{icon} {title} · {until} · " + t("account.udaleno", d=r["state"].get("deleted", 0)))
        rows.append([(f"⏹ {icon} {clip(title, 22)}", f"mm:off:{r['module']}:{r['chat_id']}")])
    lines += ["", t("account.nastroyki_umolchaniyu"),
              t("account.udalyat", x=", ".join(type_title(x, lang) for x in ms["types"])),
              t("account.udalyat_soobscheniya_so_slovami", w=esc(", ".join(ms["whitelist"])) or "—"),
              t("account.podtverzhdenie_pered_vklyucheniem", v=t("account.da") if not s.get("mute_confirmed") else t("account.net_2")),
              t("account.gde_pokazyvat_knopki", v=t("account.chate") if s.get("controls_place") == "chat" else t("account.lichke"))]
    type_btns = [(("✅ " if x in ms["types"] else "") + type_title(x, lang), f"mm:type:{x}") for x in ("all", "text", "media", "voice", "circle", "gif", "sticker")]
    rows += [type_btns[i:i + 4] for i in range(0, len(type_btns), 4)]
    rows += [[(t("account.slova_isklyucheniya"), "mm:wl"), (t("account.sprashivat_podtverzhdenie"), "mm:confirm")],
             [(t("account.knopki_chate_lichke"), "mm:place")],
             [(t("account.menyu"), "m:home")]]
    return "\n".join(lines), kb(rows)


@screen("protects")
async def screen_protects(app: Any, uid: int, s: dict[str, Any]) -> tuple[str, Any]:
    lang = s["lang"]
    t = _t(lang)
    lines = [t("account.protect_manager"),
             t("account.zaschischyonnyh_chatah_vsyo_chto_otpravlyaet", p=s["prefix"]), ""]
    rows = []
    active = [r for r in await app.controls.active(uid, module="protect")]
    if not active:
        lines.append(t("account.net_zaschischyonnyh_chatov_vklyuchit_protect",
                       p=s["prefix"]))
    for r in active[:12]:
        title = esc(clip(((await app.chats.get(uid, r["chat_id"])) or {}).get("title") or str(r["chat_id"]), 28))
        lines.append(f"🛡 {title}")
        rows.append([(f"🔓 {clip(title, 26)}", f"pp:off:{r['chat_id']}")])
    rows.append([(t("account.menyu"), "m:home")])
    return "\n".join(lines), kb(rows)


@screen("texttools")
async def screen_texttools(app: Any, uid: int, s: dict[str, Any]) -> tuple[str, Any]:
    lang = s["lang"]
    t = _t(lang)
    lines = [t("account.text_tools"),
             t("account.rabotayut_lyubom_chate_zdes_nazhmite"), ""]
    btns = []
    for cid in TEXT_TOOLS:
        spec = app.registry.get(cid, admin=app.users.is_super_id(uid))
        if spec is None:
            continue
        example = next(iter(spec.examples_for(lang)), "")    # localized catalog example, e.g. ".r Salom 👋🏽"
        args = example.split(maxsplit=1)[1] if example.startswith("." + cid) and " " in example else ""
        cmd = f"{s['prefix']}{cid} {args}".strip()
        lines.append(f"<code>{esc(cmd)}</code> — {esc(clip(spec.describe(lang), 60))}")
        btns.append((f"{s['prefix']}{cid}", f"copy:{cmd}"))
    rows = [btns[i:i + 4] for i in range(0, len(btns), 4)]
    rows.append([(t("account.vse_komandy"), "cmd:cat:text:0"), (t("account.menyu"), "m:home")])
    return "\n".join(lines), kb(rows)


@screen("reminders")
async def screen_reminders(app: Any, uid: int, s: dict[str, Any]) -> tuple[str, Any]:
    lang = s["lang"]
    t = _t(lang)
    tz = s.get("timezone") or app.config.timezone
    rows_db = await app.reminders.list(uid)
    lines = [t("account.napominaniya"), ""]
    rows = []
    if not rows_db:
        lines.append(t("account.net_aktivnyh_napominaniy"))
    for r in rows_db[:12]:
        where = t("account.chat") if r["kind"] == "chat" else t("account.lichku")
        lines.append(f"#{r['id']} · {fmt_dt(r['run_at'], tz)} · {where} · {esc(clip(r['text'], 40))}")
        rows.append([(f"🗑 #{r['id']} {clip(r['text'], 24)}", f"rm:del:{r['id']}")])
    lines += ["", t("account.chate_remindf_1h_tekst_napomnit",
                    p=s["prefix"])]
    rows.append([(t("account.novoe_napominanie"), "rm:new")])
    rows.append([(t("account.menyu"), "m:home")])
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
            await cb.message.answer(t("account.prishlite_slova_cherez_zapyatuyu_soobscheniya"))
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
            await cb.message.answer(t("account.kogda_chyom_napomnit_format_30m"))
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
            await cb.answer(t("account.izbrannoe_otpravte_fav_komanda1_komanda2",
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
    await cb.answer({"applied": tr(lang, "account.primeneno"), "rejected": tr(lang, "account.otkloneno")}.get(res, res),
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
        await message.answer(tr(s["lang"], "account.format_30m_tekst"))
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

