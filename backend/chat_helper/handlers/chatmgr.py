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
    return tr(lang, "chatmgr.vkl") if v else tr(lang, "chatmgr.vykl")


async def chat_panel(app: Any, owner: int, chat_id: int) -> tuple[str, Any]:
    s = await app.settings.all(owner)
    lang, tz = s["lang"], s.get("timezone") or app.config.timezone
    row = await app.chats.get(owner, chat_id)
    if row is None:
        return tr(lang, "chatmgr.chat_nayden"), kb([[(tr(lang, "chatmgr.spisku_chatov"), "m:chats")]])
    acc = await access(app, owner)
    ctl = app.controls
    states = {m: await ctl.is_on(owner, chat_id, m) for m in ("mute", "protect", "nogif", "nomute")}
    mute = await ctl.get(owner, chat_id, "mute")
    words = ((await ctl.get(owner, chat_id, "nomute")) or {}).get("state", {}).get("words") or []
    afk = await app.afk.active(owner)
    ai_on = s["mode"] in ("ai", "hybrid") and row.get("ai_enabled") != 0
    name = esc(clip(row.get("title") or str(chat_id), 40)) + (f" (@{esc(row['username'])})" if row.get("username") else "")
    t = lambda key, **kw: tr(lang, key, **kw)  # noqa: E731
    lines = [t("chatmgr.upravlenie_chatom"), "",
             t("chatmgr.sobesednik", n=name),
             t("chatmgr.podklyuchenie", v=t("chatmgr.aktivno") if acc.connected else t("chatmgr.otklyucheno")),
             t("chatmgr.ai", v=_onoff(lang, ai_on) + (f" · {mode_title(s['mode'], lang)}" if s["mode"] in ("ai", "hybrid") else "")),
             t("chatmgr.afk_etom_chate", v=_onoff(lang, bool(afk)),
               c=t("chatmgr.otvechat") if row.get("afk_enabled") != 0 else t("chatmgr.molchat")),
             t("chatmgr.mute", v=_onoff(lang, states["mute"]) + (
                 (" · " + (t("chatmgr.text", x=fmt_dt(mute["until_at"], tz, with_date=False)) if mute.get("until_at")
                           else t("chatmgr.bessrochno")) + t("chatmgr.udaleno", d=mute["state"].get("deleted", 0)))
                 if states["mute"] and mute else "")),
             t("chatmgr.protect", v=_onoff(lang, states["protect"])),
             t("chatmgr.gif_stikery_slova", v=_onoff(lang, states["nogif"]),
               w=(_onoff(lang, states["nomute"]) + f" ({len(words)})")),
             t("chatmgr.media", v=_onoff(lang, bool(s.get("media_enabled", True))))]
    if row.get("muted_until") and row["muted_until"] > time.time():
        lines.append(t("chatmgr.bez_avtootvetov_eschyo", d=human_duration(row["muted_until"] - time.time(), lang)))
    c = f"ch:{chat_id}"
    rows = [[(t("chatmgr.ai_2", x="⏹" if ai_on else "▶️"), f"{c}:ai"), (t("chatmgr.mute_2", x="⏹" if states["mute"] else "▶️"), f"{c}:mute")],
            [(t("chatmgr.protect_2", x="⏹" if states["protect"] else "▶️"), f"{c}:protect"),
             (t("chatmgr.afk_tut", x="⏹" if row.get("afk_enabled") != 0 else "▶️"), f"{c}:afk")],
            [(t("chatmgr.gif_stikery", x="⏹" if states["nogif"] else "▶️"), f"{c}:nogif"),
             (t("chatmgr.slova"), f"{c}:words")],
            [(t("chatmgr.bystrye_komandy"), f"{c}:quick"), (t("chatmgr.rasshirennye"), f"{c}:adv")],
            [(t("chatmgr.moi_chaty_2"), "m:chats"), (t("chatmgr.menyu"), "m:home")]]
    return "\n".join(lines), kb(rows)


async def send_chat_panel(app: Any, owner: int, chat_id: int, focus: str | None = None) -> None:
    text, markup = await chat_panel(app, owner, chat_id)
    await app.sender.send_text(owner, text, markup=markup)


@screen("chats")
async def screen_chats(app: Any, uid: int, s: dict[str, Any], page: int = 0) -> tuple[str, Any]:
    lang = s["lang"]
    data = await app.chats.list(uid, sort="recent", page=1, page_size=200)
    items = data["items"]
    lines = [tr(lang, "chatmgr.moi_chaty"), ""]
    if not items:
        lines.append(tr(lang, "chatmgr.poka_net_chatov_oni_poyavyatsya"))
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
    rows.append([(tr(lang, "chatmgr.nazad"), "m:home")])
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
        text = tr(lang, "chatmgr.udalos_podtverdit_etot_chat_chat")
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
    t = lambda key, **kw: tr(lang, key, **kw)  # noqa: E731
    parts = (cb.data or "").split(":")
    if len(parts) < 3 or not parts[1].lstrip("-").isdigit():
        await cb.answer()
        return
    chat_id, action = int(parts[1]), parts[2]
    arg = parts[3] if len(parts) > 3 else ""
    row = await app.chats.get(uid, chat_id)          # ownership: only chats of this owner exist for him
    if row is None:
        await cb.answer(t("chatmgr.chat_nayden"), show_alert=True)
        return
    acc = await access(app, uid)
    conn = acc.conn
    toast = ""
    if action == "ai":
        if s["mode"] not in ("ai", "hybrid"):
            await cb.answer(t("chatmgr.snachala_vklyuchite_rezhim_ai_hybrid"),
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
            await cb.answer(t("chatmgr.nuzhno_pravo_udalenie_vhodyaschih_nastroykah"), show_alert=True)
            return
        await app.controls.set(uid, chat_id, action, on, connection_id=conn.id if conn else None)
        await refresh_cards(app, uid, chat_id, action)
        toast = "✅" if on else "⏹"
    elif action == "mute":
        if await app.controls.is_on(uid, chat_id, "mute"):
            await set_mute(app, uid, chat_id, False)
            toast = t("chatmgr.mute_otklyuchyon")
        else:
            if not (conn and conn.can("can_delete_all_messages")):
                await cb.answer(t("chatmgr.mute_nuzhno_pravo_udalenie_vhodyaschih"), show_alert=True)
                return
            if not s.get("mute_confirmed") and arg != "ok":
                text = t("chatmgr.vklyuchit_mute_novye_vhodyaschie_soobscheniya")
                markup = kb([[(t("chatmgr.vklyuchit"), f"ch:{chat_id}:mute:ok")],
                             [(t("chatmgr.vklyuchit_sprashivat"), f"ch:{chat_id}:muteall:ok")],
                             [(t("chatmgr.otmena"), f"ch:{chat_id}:open")]])
                await cb.answer()
                await render(cb.message, text, markup)
                return
            await set_mute(app, uid, chat_id, True, conn_id=conn.id if conn else None)
            await app.controls.update_state(uid, chat_id, "mute", confirmed_at=int(time.time()))
            toast = t("chatmgr.mute_vklyuchyon")
    elif action == "muteall":
        await app.settings.set(uid, "mute_confirmed", True)
        await set_mute(app, uid, chat_id, True, conn_id=conn.id if conn else None)
        toast = t("chatmgr.mute_vklyuchyon")
    elif action == "words":
        words = ((await app.controls.get(uid, chat_id, "nomute")) or {}).get("state", {}).get("words") or []
        text = "\n".join([t("chatmgr.filtr_slov"),
                          t("chatmgr.vhodyaschie_soobscheniya_etimi_slovami_udalyayut"), "",
                          ("• " + ", ".join(esc(w) for w in words)) if words else t("chatmgr.slov_poka_net"), "",
                          t("chatmgr.dobavit_etom_chate_napishite_nomute",
                            p=s["prefix"])])
        on = await app.controls.is_on(uid, chat_id, "nomute")
        rows = [[((t("chatmgr.vyklyuchit_filtr") if on else t("chatmgr.vklyuchit_filtr")), f"ch:{chat_id}:nomute")]]
        if words:
            rows.append([(t("chatmgr.ochistit_slova"), f"ch:{chat_id}:wclear")])
        rows.append([(t("chatmgr.nazad_2"), f"ch:{chat_id}:open")])
        await cb.answer()
        await render(cb.message, text, kb(rows))
        return
    elif action == "nomute":
        words = ((await app.controls.get(uid, chat_id, "nomute")) or {}).get("state", {}).get("words") or []
        on = not await app.controls.is_on(uid, chat_id, "nomute")
        if on and not words:
            await cb.answer(t("chatmgr.snachala_dobavte_slova_komandoy_nomute"), show_alert=True)
            return
        await app.controls.set(uid, chat_id, "nomute", on, connection_id=conn.id if conn else None)
        await refresh_cards(app, uid, chat_id, "nomute")
        toast = "✅" if on else "⏹"
    elif action == "wclear":
        await app.controls.set(uid, chat_id, "nomute", False, state={"words": []})
        await refresh_cards(app, uid, chat_id, "nomute")
        toast = "🗑"
    elif action == "quick":
        text = t("chatmgr.bystrye_deystviya_chata")
        rows = [[(t("chatmgr.pereskaz_poslednih_30_soobscheniy"), f"ch:{chat_id}:q:sum")],
                [(t("chatmgr.mute_1_chas"), f"ch:{chat_id}:q:mute1h"), (t("chatmgr.kubik_chat"), f"ch:{chat_id}:q:dice")],
                [(t("chatmgr.sbrosit_ai_kontekst"), f"ch:{chat_id}:q:resetai")],
                [(t("chatmgr.nazad_2"), f"ch:{chat_id}:open")]]
        await cb.answer()
        await render(cb.message, text, kb(rows))
        return
    elif action == "q":
        toast = await _quick(app, uid, chat_id, arg, conn, s)
        if toast is None:
            return await cb.answer()
    elif action == "adv":
        text = "\n".join([t("chatmgr.rasshirennye_nastroyki_chata"), "",
                          t("chatmgr.yazyk_otvetov", l=(row.get("language") or t("chatmgr.kak_nastroykah")).upper()),
                          t("chatmgr.limit_avtootvetov_den", n=row.get("reply_limit") or s["max_auto_replies_per_chat_day"]),
                          t("chatmgr.ignorirovat_chat", v=_onoff(lang, bool(row.get("ignored"))))])
        c = f"ch:{chat_id}"
        rows = [[("RU", f"{c}:lang:ru"), ("UZ", f"{c}:lang:uz"), (t("chatmgr.avto"), f"{c}:lang:auto")],
                [("5/" + t("chatmgr.den"), f"{c}:limit:5"), ("20", f"{c}:limit:20"), ("50", f"{c}:limit:50")],
                [(t("chatmgr.ignor_vkl_vykl"), f"{c}:ignore")],
                [(t("chatmgr.nazad_2"), f"{c}:open")]]
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
            return tr(lang, "chatmgr.nuzhno_pravo_udalenie_vhodyaschih")
        if not s.get("mute_confirmed"):
            return tr(lang, "chatmgr.snachala_vklyuchite_mute_knopkoy_vyshe")
        await set_mute(app, uid, chat_id, True, until_for=3600, conn_id=conn.id)
        return tr(lang, "chatmgr.mute_1_chas")
    if what == "dice":
        if not (conn and conn.can("can_reply")):
            return tr(lang, "chatmgr.net_prava_otvety_soobscheniya")
        res = await app.sender.send_dice(chat_id, "🎲", bc_id=conn.id)
        return "🎲" if res.ok else tr(lang, "chatmgr.udalos", k=res.kind)
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

