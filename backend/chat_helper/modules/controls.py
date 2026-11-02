"""Chat Control Framework: control cards with owner-only inline buttons + per-chat module commands.

A *card* is a message with buttons that controls one module of one chat (🔕 mute, 🛡 protect, 🚫 nogif, 🧹 word filter,
💤 AFK, 💬 auto-reply, ℹ️ online). Cards live in the business chat (default — the owner's command message is turned into
the card, or the bot posts it on the owner's behalf) or in the private chat with the bot (``controls_place = dm`` or as a
fallback). Callback data = ``cc:<token>:<action>:<version>[:<arg>]``; see :mod:`handlers.controls` for the checks.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from ..business import sender as S
from ..commands.context import CommandContext, CommandError, UsageError
from ..commands.registry import LIMITED_BY_TELEGRAM, registry
from ..core.timeutil import fmt_dt, human_duration, parse_duration
from ..localization import tr
from ..security.sanitize import clip, esc
from .chat_filters import MUTE_TYPES, NOGIF_TYPES, normalize_type, type_title

if TYPE_CHECKING:  # pragma: no cover
    from ..business.connections import Conn
    from ..core.context import AppContext

log = logging.getLogger(__name__)

TIME_PRESETS = ((600, ("controls.time_presets.10_min")), (3600, ("controls.time_presets.1_ch")), (8 * 3600, ("controls.time_presets.8_ch")), (86400, ("controls.time_presets.1_den")))
AFK_PRESETS = ((1800, ("controls.afk_presets.30_min")), (3600, ("controls.afk_presets.1_ch")), (2 * 3600, ("controls.afk_presets.2_ch")), (8 * 3600, ("controls.afk_presets.8_ch")))


@dataclass
class View:
    text: str
    buttons: list[list[tuple[str, str, str]]] = field(default_factory=list)   # (label, action, arg)


def build_markup(card: dict[str, Any], buttons: list[list[tuple[str, str, str]]]) -> InlineKeyboardMarkup | None:
    rows = []
    for row in buttons:
        btns = []
        for label, action, arg in row:
            data = f"cc:{card['token']}:{action}:{card['version']}" + (f":{arg}" if arg else "")
            btns.append(InlineKeyboardButton(text=label, callback_data=data[:64]))
        if btns:
            rows.append(btns)
    return InlineKeyboardMarkup(inline_keyboard=rows) if rows else None


async def chat_title(app: "AppContext", owner_id: int, chat_id: int) -> str:
    row = await app.chats.get(owner_id, chat_id)
    if row and (row.get("title") or row.get("username")):
        return row.get("title") or ("@" + row["username"])
    return str(chat_id)


def _until_line(lang: str, until_at: int | None, tz: str) -> str:
    if not until_at:
        return tr(lang, "controls.dlitelnost_bessrochno")
    left = max(0, until_at - int(time.time()))
    return tr(lang, "controls.eschyo", t=fmt_dt(until_at, tz, with_date=left > 86400),
              d=human_duration(left, lang))


# =====================================================================================================================
# renderers
# =====================================================================================================================
async def render_view(app: "AppContext", card: dict[str, Any], view: str | None = None) -> View:
    owner, chat_id, module = card["owner_id"], card["chat_id"], card["module"]
    s = await app.settings.all(owner)
    lang, tz = s["lang"], s.get("timezone") or app.config.timezone
    private = card["location"] == "dm"
    name = esc(clip(await chat_title(app, owner, chat_id), 40))
    row = await app.controls.get(owner, chat_id, module) if module not in ("afk", "auto", "online") else None
    on = await app.controls.is_on(owner, chat_id, module) if row else False
    t = lambda key, **kw: tr(lang, key, **kw)  # noqa: E731
    back = [(t("controls.nazad"), "back", "")]

    if module == "mute":
        if view == "confirm":
            pending = (row or {}).get("state", {})
            types = pending.get("pending_types") or (await app.filters.mute_settings(owner, chat_id))["types"]
            until = pending.get("pending_for")
            return View("\n".join([
                t("controls.vklyuchit_mute_chata", n=name), "",
                t("controls.chat_helper_budet_udalyat_novye"),
                t("controls.udalenie_neobratimo"),
                t("controls.vashi_soobscheniya_staraya_perepiska_zatragivayu"),
                t("controls.sobesednik_mozhet_uspet_uvidet_uvedomlenie"),
                t("controls.tipy_2", x=", ".join(type_title(x, lang) for x in types),
                  d=human_duration(until, lang) if until else t("controls.bessrochno_2")),
            ]), [[(t("controls.vklyuchit_2"), "confirm", "")],
                 [(t("controls.vklyuchit_bolshe_sprashivat"), "confirm", "always")],
                 [(t("controls.otmena"), "cancel", "")]])
        if view == "time":
            presets = [(t(key), "set", str(sec)) for sec, key in TIME_PRESETS]
            return View(t("controls.vremya_mute_vyberite_dlitelnost", n=name),
                        [presets[:2], presets[2:], [(t("controls.bessrochno"), "set", "0")], back])
        if on:
            lines = [t("controls.rezhim_mute_vklyuchyon"),
                     t("controls.chat", n=name), _until_line(lang, row.get("until_at"), tz),
                     t("controls.novye_vhodyaschie_soobscheniya_budut_udalyatsya")]
            if private:
                ms = await app.filters.mute_settings(owner, chat_id)
                lines.append(t("controls.tipy", x=", ".join(type_title(x, lang) for x in ms["types"])))
                lines.append(t("controls.udaleno", n=row["state"].get("deleted", 0)))
            return View("\n".join(lines), [[(t("controls.snyat_mute"), "off", "")],
                                           [(t("controls.ustanovit_vremya"), "time", ""),
                                            (t("controls.nastroyki"), "settings", "")]])
        lines = [t("controls.mute_otklyuchyon"), t("controls.chat", n=name)]
        if private and row:
            lines.append(t("controls.udaleno_seans", n=row["state"].get("deleted", 0)))
        return View("\n".join(lines), [[(t("controls.vklyuchit_snova"), "on", "")]])

    if module == "protect":
        if on:
            return View("\n".join([
                t("controls.zaschita_vklyuchena"), t("controls.chat", n=name),
                t("controls.soobscheniya_kotorye_chat_helper_otpravlyaet")]),
                [[(t("controls.otklyuchit_zaschitu"), "off", ""), (t("controls.nastroit"), "settings", "")]])
        return View(t("controls.zaschita_otklyuchena_chat", n=name),
                    [[(t("controls.vklyuchit_zaschitu"), "on", "")]])

    if module == "nogif":
        types = (row or {}).get("state", {}).get("types") or ["gif", "sticker"]
        if view == "types":
            btns = [[((("✅ " if x in types else "⬜️ ") + type_title(x, lang)), "tt", x)] for x in NOGIF_TYPES]
            return View(t("controls.kakie_tipy_udalyat"), btns + [back])
        if on:
            return View("\n".join([
                t("controls.filtr_gif_stikerov_vklyuchyon"), t("controls.chat", n=name),
                t("controls.udalyayutsya_vhodyaschie_esli_telegram_razreshae",
                  x=", ".join(type_title(x, lang) for x in types))]),
                [[(t("controls.otklyuchit_filtr"), "off", ""), (t("controls.tipy_media"), "types", "")]])
        return View(t("controls.filtr_gif_stikerov_otklyuchyon"),
                    [[(t("controls.vklyuchit_filtr"), "on", "")]])

    if module == "nomute":
        words = (row or {}).get("state", {}).get("words") or []
        if on:
            lines = [t("controls.filtr_slov_vklyuchyon"), t("controls.chat", n=name),
                     t("controls.vhodyaschie_soobscheniya_vybrannymi_slovami_udal",
                       k=len(words))]
            if private and words:
                lines.append("• " + ", ".join(esc(w) for w in words[:20]))
            return View("\n".join(lines), [[(t("controls.vyklyuchit_filtr"), "off", ""),
                                           (t("controls.slova"), "settings", "")]])
        return View(t("controls.filtr_slov_vyklyuchen"),
                    [[(t("controls.vklyuchit"), "on", "")]])

    if module == "afk":
        sess = await app.afk.active(owner)
        if view == "time":
            presets = [(t(key), "set", str(sec)) for sec, key in AFK_PRESETS]
            return View(t("controls.taymer_afk_afk_vyklyuchitsya_avtomaticheski"),
                        [presets[:2], presets[2:], [(t("controls.bez_taymera"), "set", "0")], back])
        if sess:
            lines = [t("controls.afk_vklyuchyon")]
            if sess.get("reason"):
                lines.append("📝 " + esc(clip(sess["reason"], 200)))
            lines.append(_until_line(lang, sess.get("ends_at"), tz) if sess.get("ends_at") else
                         t("controls.ruchnogo_vyklyucheniya"))
            return View("\n".join(lines), [[(t("controls.vyklyuchit_afk"), "off", "")],
                                           [(t("controls.izmenit_tekst"), "text", ""),
                                            (t("controls.taymer"), "time", "")]])
        return View(t("controls.afk_vyklyuchen"), [[(t("controls.vklyuchit_snova_2"), "on", "")]])

    if module == "auto":
        from .autoreply import mode_title
        mode = s["mode"]
        if mode not in ("manual", "silent"):
            return View(t("controls.avtootvet_vklyuchyon_rezhim", m=mode_title(mode, lang)),
                        [[(t("controls.otklyuchit_avtootvet"), "off", "")],
                         [(t("controls.nastroit_ai"), "settings", "")]])
        return View(t("controls.avtootvet_vyklyuchen_rezhim", m=mode_title(mode, lang)),
                    [[(t("controls.vklyuchit_avtootvet"), "on", "")]])

    if module == "online":
        act = bool(s.get("chat_activity"))
        return View("\n".join([
            t("controls.status_seti_nedostupen"),
            t("controls.ofitsialnyy_telegram_bot_api_pozvolyaet"),
            t("controls.vmesto_etogo_afk_otvet_chat"),
            t("controls.chat_activity", v=t("controls.vkl") if act else t("controls.vykl")),
        ]), [[((t("controls.vyklyuchit_chat_activity") if act else
                t("controls.vklyuchit_chat_activity")), "activity", "0" if act else "1")],
             [(t("controls.vklyuchit_afk"), "afk", "")]])

    if module == "re":
        job = await app.db.fetchone("SELECT * FROM repetition_jobs WHERE owner_id=? AND chat_id=? ORDER BY id DESC LIMIT 1", (owner, chat_id))
        if job and job["status"] == "running":
            left = max(0, job["ends_at"] - int(time.time()))
            return View(t("controls.povtor_soobscheniya_ostalos", d=human_duration(left, lang)),
                        [[(t("controls.ostanovit"), "stop", "")]])
        return View(t("controls.povtor_ostanovlen"), [])
    return View("—", [])


# =====================================================================================================================
# posting & refreshing cards
# =====================================================================================================================
async def post_card(app: "AppContext", owner_id: int, chat_id: int, module: str, *, conn: "Conn | None",
                    ctx: CommandContext | None = None, location: str | None = None, view: str | None = None) -> dict[str, Any] | None:
    s = await app.settings.all(owner_id)
    place = location or s.get("controls_place") or "chat"
    if conn is None or not conn.is_enabled or not conn.can("can_reply"):
        place = "dm"
    token = await app.controls.create_card(owner_id, chat_id, module, location=place,
                                           host_chat_id=chat_id if place == "chat" else owner_id, message_id=None,
                                           connection_id=conn.id if conn else None)
    card = await app.controls.card(token)
    if place == "chat":
        v = await render_view(app, card, view)
        markup = build_markup(card, v.buttons)
        mid = None
        if ctx is not None and ctx.message is not None and not ctx._edited_in_place:
            res = await app.sender.edit_text(chat_id, ctx.message.message_id, v.text, bc_id=conn.id, markup=markup)
            if res.ok and (markup is None or getattr(res.message, "reply_markup", None) is not None):
                mid = ctx.message.message_id
                ctx._edited_in_place = True
                ctx.result_message_id = mid
        if mid is None:
            res = await app.sender.send_text(chat_id, v.text, bc_id=conn.id, markup=markup)
            if res.ok:
                mid = res.message_id
                if ctx is not None:
                    await ctx.cleanup_command()
        if mid is not None:
            await app.controls.set_card_message(token, mid)
            return await app.controls.card(token)
        await app.db.execute("UPDATE control_messages SET location='dm', host_chat_id=? WHERE token=?", (owner_id, token))
        card = await app.controls.card(token)
    v = await render_view(app, card, view)
    res = await app.sender.send_text(owner_id, v.text, markup=build_markup(card, v.buttons))
    if not res.ok:
        await app.controls.close_card(token, "failed")
        return None
    await app.controls.set_card_message(token, res.message_id, location="dm", host_chat_id=owner_id)
    if ctx is not None and ctx.is_business:
        await ctx.cleanup_command(fallback_text="✅")
    return await app.controls.card(token)


async def edit_card(app: "AppContext", card: dict[str, Any], view: str | None = None, *, buttons: bool = True) -> bool:
    if not card.get("message_id"):
        return False
    v = await render_view(app, card, view)
    markup = build_markup(card, v.buttons) if buttons else None
    bc = card["connection_id"] if card["location"] == "chat" else None
    res = await app.sender.edit_text(card["host_chat_id"], card["message_id"], v.text, bc_id=bc, markup=markup)
    if not res.ok and res.kind not in (S.NOT_MODIFIED,):
        await app.controls.close_card(card["token"], "orphan")
        return False
    return True


async def refresh_cards(app: "AppContext", owner_id: int, chat_id: int, module: str) -> int:
    """State changed: bump versions (old buttons become stale) and re-render every active card."""
    await app.controls.bump(owner_id, chat_id, module)
    n = 0
    for card in await app.controls.cards(owner_id, chat_id, module):
        n += await edit_card(app, card)
    return n


async def refresh_owner_module(app: "AppContext", owner_id: int, module: str) -> None:
    """Account-level modules (AFK, auto) have cards in several chats."""
    rows = await app.db.fetchall("SELECT DISTINCT chat_id FROM control_messages WHERE owner_id=? AND module=? AND status='active'",
                                 (owner_id, module))
    for r in rows:
        await refresh_cards(app, owner_id, r["chat_id"], module)


# =====================================================================================================================
# actions (shared by buttons, commands, panel and API)
# =====================================================================================================================
async def set_mute(app: "AppContext", owner_id: int, chat_id: int, on: bool, *, until_for: int | None = None,
                   types: list[str] | None = None, conn_id: str | None = None) -> dict[str, Any]:
    if on:
        if types:
            await app.filters.set_mute_settings(owner_id, chat_id, types=types)
        until = int(time.time()) + until_for if until_for else None
        row = await app.controls.set(owner_id, chat_id, "mute", True, until_at=until, connection_id=conn_id,
                                     state={"deleted": 0, "since": int(time.time()), "pending_for": None, "pending_types": None})
        await app.audit.log("mute.enabled", actor_id=owner_id, target_type="chat", target_id=chat_id, until=until)
    else:
        row = await app.controls.set(owner_id, chat_id, "mute", False)
        await app.audit.log("mute.disabled", actor_id=owner_id, target_type="chat", target_id=chat_id)
    await refresh_cards(app, owner_id, chat_id, "mute")
    return row


async def apply_action(app: "AppContext", card: dict[str, Any], action: str, arg: str) -> tuple[str, str | None]:
    """Execute a button action. Returns (toast text, view to show on this card or None)."""
    owner, chat_id, module = card["owner_id"], card["chat_id"], card["module"]
    s = await app.settings.all(owner)
    lang = s["lang"]
    t = lambda key, **kw: tr(lang, key, **kw)  # noqa: E731
    if action in ("time", "types") or (action == "back"):
        return "", (None if action == "back" else action)
    if action == "settings":
        from ..handlers.chatmgr import send_chat_panel
        await send_chat_panel(app, owner, chat_id, focus=module)
        return t("controls.nastroyki_otpravleny_vam_lichku_botom"), None

    if module == "mute":
        if action == "off":
            await set_mute(app, owner, chat_id, False)
            return t("controls.mute_otklyuchyon_3"), None
        if action == "on":
            row = await app.controls.get(owner, chat_id, "mute")
            if not s.get("mute_confirmed") and not (row and row["state"].get("confirmed_at")):
                return "", "confirm"
            await set_mute(app, owner, chat_id, True, conn_id=card["connection_id"])
            return t("controls.mute_vklyuchyon"), None
        if action == "confirm":
            row = await app.controls.get(owner, chat_id, "mute")
            st = (row or {}).get("state", {})
            if arg == "always":
                await app.settings.set(owner, "mute_confirmed", True)
            await set_mute(app, owner, chat_id, True, until_for=st.get("pending_for"), types=st.get("pending_types"),
                           conn_id=card["connection_id"])
            await app.controls.update_state(owner, chat_id, "mute", confirmed_at=int(time.time()))
            await post_chat_card_after_confirm(app, card)
            return t("controls.mute_vklyuchyon"), None
        if action == "cancel":
            await app.controls.close_card(card["token"])
            return t("controls.otmeneno_2"), "__closed__"
        if action == "set":
            sec = int(arg) if arg.isdigit() else 0
            row = await app.controls.get(owner, chat_id, "mute")
            if not row or not row["enabled"]:
                return t("controls.mute_seychas_vyklyuchen"), None
            await app.controls.set(owner, chat_id, "mute", True, until_at=int(time.time()) + sec if sec else None)
            await refresh_cards(app, owner, chat_id, "mute")
            return (t("controls.mute", d=human_duration(sec, lang)) if sec else t("controls.mute_bessrochno")), None

    if module in ("protect", "nogif", "nomute"):
        if action in ("on", "off"):
            await app.controls.set(owner, chat_id, module, action == "on", connection_id=card["connection_id"])
            await app.audit.log(f"{module}.{'enabled' if action == 'on' else 'disabled'}", actor_id=owner, target_type="chat", target_id=chat_id)
            await refresh_cards(app, owner, chat_id, module)
            return ("✅" if action == "on" else "⏹"), None
        if module == "nogif" and action == "tt" and arg in NOGIF_TYPES:
            row = await app.controls.get(owner, chat_id, "nogif")
            types = list((row or {}).get("state", {}).get("types") or ["gif", "sticker"])
            types = [x for x in types if x != arg] if arg in types else types + [arg]
            if not types:
                return t("controls.nuzhen_hotya_by_odin_tip"), "types"
            await app.controls.set(owner, chat_id, "nogif", bool(row and row["enabled"]), state={"types": types}, keep_until=True)
            await app.controls.bump(owner, chat_id, "nogif")
            for c in await app.controls.cards(owner, chat_id, "nogif"):
                if c["token"] != card["token"]:
                    await edit_card(app, c)
            return "✅", "types"

    if module == "afk":
        if action == "off":
            await app.afk.disable(owner, reason="button")
            await refresh_owner_module(app, owner, "afk")
            return t("controls.afk_vyklyuchen_2"), None
        if action == "on":
            await app.afk.enable(owner, None, None)
            await refresh_owner_module(app, owner, "afk")
            return t("controls.afk_vklyuchyon_2"), None
        if action == "set":
            sess = await app.afk.active(owner)
            sec = int(arg) if arg.isdigit() else 0
            await app.afk.enable(owner, (sess or {}).get("reason"), sec or None)
            await refresh_owner_module(app, owner, "afk")
            return t("controls.taymer_ustanovlen") if sec else t("controls.bez_taymera"), None
        if action == "text":
            await ask_afk_text(app, owner)
            return t("controls.prishlite_novyy_tekst_lichku_botom"), None

    if module == "auto":
        if action == "off":
            if s["mode"] not in ("manual", "silent"):
                await app.settings.set(owner, "auto_prev_mode", s["mode"])
            await app.settings.set(owner, "mode", "manual")
            await refresh_owner_module(app, owner, "auto")
            return t("controls.avtootvet_vyklyuchen"), None
        if action == "on":
            prev = s.get("auto_prev_mode") or "auto"
            await app.settings.set(owner, "mode", prev if prev not in ("manual", "silent") else "auto")
            await refresh_owner_module(app, owner, "auto")
            return t("controls.avtootvet_vklyuchyon"), None

    if module == "online":
        if action == "activity":
            await app.settings.set(owner, "chat_activity", arg == "1")
            await app.controls.bump(owner, chat_id, "online")
            return "✅", None
        if action == "afk":
            await app.afk.enable(owner, None, None)
            await refresh_owner_module(app, owner, "afk")
            return t("controls.afk_vklyuchyon_2"), None

    if module == "re" and action == "stop":
        from .repeat import stop_repeat
        await stop_repeat(app, owner, chat_id, reason="button")
        return t("controls.ostanovleno"), None
    return t("controls.neizvestnoe_deystvie"), None


async def post_chat_card_after_confirm(app: "AppContext", dm_card: dict[str, Any]) -> None:
    """After confirming in the DM, show the regular card in the chat as well (if the owner prefers chat cards)."""
    s = await app.settings.all(dm_card["owner_id"])
    if s.get("controls_place", "chat") != "chat" or not dm_card.get("connection_id"):
        return
    conn = await app.connections.get(dm_card["connection_id"])
    if conn and conn.is_enabled and conn.can("can_reply"):
        await post_card(app, dm_card["owner_id"], dm_card["chat_id"], "mute", conn=conn, location="chat")


async def ask_afk_text(app: "AppContext", owner_id: int) -> None:
    from aiogram.fsm.storage.base import StorageKey
    s = await app.settings.all(owner_id)
    storage = getattr(app, "fsm_storage", None)
    if storage is not None and app.bot is not None:
        await storage.set_state(StorageKey(bot_id=app.bot.id, chat_id=owner_id, user_id=owner_id), "PS:afk_reason")
    await app.sender.send_text(owner_id, tr(s["lang"], "controls.prishlite_novyy_tekst_prichinu_afk"))


# =====================================================================================================================
# commands
# =====================================================================================================================
CTL = dict(where="business", rate=(20, 60))


def _split_duration_and_words(args: list[str]) -> tuple[int | None, list[str]]:
    dur, rest = None, []
    for a in args:
        d = parse_duration(a) if dur is None else None
        if d:
            dur = d
        else:
            rest.append(a)
    return dur, rest


@registry.command("mute", "chat", aliases=["мьют", "заглушить", "jim"],
                  rights=["can_reply", "can_delete_all_messages"], status=LIMITED_BY_TELEGRAM,
                  **CTL)
async def cmd_mute(ctx: CommandContext) -> None:
    app, owner, chat_id = ctx.app, ctx.user_id, ctx.chat_id
    first = ctx.parsed.first
    if first in ("off", "выкл", "stop", "o'chir"):
        await cmd_unmute(ctx)
        return
    if first in ("status", "статус", "holat"):
        row = await app.controls.get(owner, chat_id, "mute")
        on = await app.controls.is_on(owner, chat_id, "mute")
        st = await app.filters.stats(owner, chat_id, (row or {}).get("state", {}).get("since"))
        await ctx.answer(ctx.t("controls.mute_udaleno_oshibok",
                               v=ctx.t("controls.vklyuchyon") if on else ctx.t("controls.vyklyuchen"), d=st["deleted"], f=st["failed"]),
                         private=True)
        return
    dur, words = _split_duration_and_words(ctx.args)
    if dur is not None and not 60 <= dur <= 30 * 86400:
        raise UsageError(ctx.t("controls.vremya_1_minuty_30_dney"))
    types = []
    for w in words:
        t = normalize_type(w)
        if t is None:
            raise UsageError(ctx.t("controls.neizvestnyy_tip_tipy", w=esc(w), x=", ".join(MUTE_TYPES)))
        types.append(t)
    await app.chats.touch(owner, chat_id)
    if not ctx.settings.get("mute_confirmed"):
        await app.controls.set(owner, chat_id, "mute", False, connection_id=ctx.conn.id,
                               state={"pending_for": dur, "pending_types": types or None})
        card = await post_card(app, owner, chat_id, "mute", conn=ctx.conn, location="dm", view="confirm")
        await ctx.cleanup_command(fallback_text="🔕")
        if card is None:
            raise CommandError(ctx.t("controls.udalos_otpravit_podtverzhdenie_lichku_otkroyte"))
        return
    await set_mute(app, owner, chat_id, True, until_for=dur, types=types or None, conn_id=ctx.conn.id)
    await post_card(app, owner, chat_id, "mute", conn=ctx.conn, ctx=ctx)


@registry.command("unmute", "chat", aliases=["анмьют", "размьют", "unjim"], **CTL)
async def cmd_unmute(ctx: CommandContext) -> None:
    app, owner, chat_id = ctx.app, ctx.user_id, ctx.chat_id
    row = await app.controls.get(owner, chat_id, "mute")
    deleted = (row or {}).get("state", {}).get("deleted", 0)
    await set_mute(app, owner, chat_id, False)
    await ctx.answer(ctx.t("controls.mute_otklyuchyon_2"))
    if deleted:
        await app.sender.send_text(owner, ctx.t("controls.mute_chate_udaleno_soobscheniy",
                                                n=esc(await chat_title(app, owner, chat_id)), d=deleted))


@registry.command("quiet", "chat", aliases=["тихо", "jimlik"],
                  **CTL)
async def cmd_quiet(ctx: CommandContext) -> None:
    arg = ctx.parsed.first
    if arg in ("off", "выкл"):
        await ctx.app.chats.update(ctx.user_id, ctx.chat_id, {"muted_until": None})
        await ctx.answer(ctx.t("controls.avtootvety_etom_chate_snova_rabotayut"), private=True)
        return
    dur = parse_duration(arg) if arg else 3600 * 24 * 365
    if not dur:
        raise UsageError()
    await ctx.app.chats.touch(ctx.user_id, ctx.chat_id)
    until = int(time.time()) + dur
    await ctx.app.chats.update(ctx.user_id, ctx.chat_id, {"muted_until": until})
    tz_name = ctx.settings.get("timezone") or ctx.app.config.timezone
    await ctx.answer(ctx.t("controls.bez_avtootvetov", t=fmt_dt(until, tz_name)), private=True)


@registry.command("protect", "chat", aliases=["защита", "himoya"],
                  rights=["can_reply"], status=LIMITED_BY_TELEGRAM,
                  **CTL)
async def cmd_protect(ctx: CommandContext) -> None:
    on = ctx.parsed.first not in ("off", "выкл", "o'chir")
    await ctx.app.chats.touch(ctx.user_id, ctx.chat_id)
    await ctx.app.controls.set(ctx.user_id, ctx.chat_id, "protect", on, connection_id=ctx.conn.id)
    await ctx.app.audit.log(f"protect.{'enabled' if on else 'disabled'}", actor_id=ctx.user_id, target_type="chat", target_id=ctx.chat_id)
    await refresh_cards(ctx.app, ctx.user_id, ctx.chat_id, "protect")
    await post_card(ctx.app, ctx.user_id, ctx.chat_id, "protect", conn=ctx.conn, ctx=ctx)


@registry.command("unprotect", "chat", aliases=["снятьзащиту"], **CTL)
async def cmd_unprotect(ctx: CommandContext) -> None:
    await ctx.app.controls.set(ctx.user_id, ctx.chat_id, "protect", False)
    await refresh_cards(ctx.app, ctx.user_id, ctx.chat_id, "protect")
    await ctx.answer(ctx.t("controls.zaschita_otklyuchena"))


@registry.command("g", "chat", aliases=["защищённо", "secret"],
                  rights=["can_reply"], status=LIMITED_BY_TELEGRAM,
                  **CTL)
async def cmd_g(ctx: CommandContext) -> None:
    app, bc = ctx.app, ctx.bc_id
    text = ctx.raw.strip()
    r = ctx.reply
    sent: S.SendResult | None = None
    if text:
        sent = await app.sender.send_text(ctx.chat_id, esc(text), bc_id=bc, protect=True)
    elif r is not None:
        for kind, attr in (("photo", "photo"), ("video", "video"), ("animation", "animation"), ("voice", "voice"),
                           ("video_note", "video_note"), ("document", "document"), ("audio", "audio")):
            obj = getattr(r, attr, None)
            if obj:
                fid = obj[-1].file_id if isinstance(obj, list) else obj.file_id
                sent = await app.sender.send_media(ctx.chat_id, kind, fid, bc_id=bc, protect=True, caption=r.caption)
                break
        if sent is None and (r.text or r.caption):
            sent = await app.sender.send_text(ctx.chat_id, esc(r.text or r.caption), bc_id=bc, protect=True)
    else:
        raise UsageError()
    if sent is None or not sent.ok:
        raise CommandError(ctx.t("controls.udalos_otpravit_zaschischyonnoe_soobschenie",
                                 k=sent.kind if sent else "—"))
    await ctx.cleanup_command(fallback_text="🔒")
    if not ctx.command_deleted:
        await app.sender.send_text(ctx.user_id, ctx.t(
            "controls.zaschischyonnoe_soobschenie_otpravleno_no_ishodn"))


@registry.command("nogif", "chat", aliases=["безгиф", "gifsiz"],
                  rights=["can_reply", "can_delete_all_messages"], status=LIMITED_BY_TELEGRAM, **CTL)
async def cmd_nogif(ctx: CommandContext) -> None:
    app = ctx.app
    if ctx.parsed.first in ("off", "выкл", "o'chir"):
        await app.controls.set(ctx.user_id, ctx.chat_id, "nogif", False)
        await refresh_cards(app, ctx.user_id, ctx.chat_id, "nogif")
        await ctx.answer(ctx.t("controls.filtr_gif_stikerov_otklyuchyon_2"))
        return
    types = [x for x in (normalize_type(a) for a in ctx.args) if x in NOGIF_TYPES] or ["gif", "sticker"]
    await app.chats.touch(ctx.user_id, ctx.chat_id)
    await app.controls.set(ctx.user_id, ctx.chat_id, "nogif", True, state={"types": types, "deleted": 0}, connection_id=ctx.conn.id)
    await refresh_cards(app, ctx.user_id, ctx.chat_id, "nogif")
    await post_card(app, ctx.user_id, ctx.chat_id, "nogif", conn=ctx.conn, ctx=ctx)


@registry.command("nomute", "chat", aliases=["фильтрслов", "sozfiltr"],
                  rights=["can_reply", "can_delete_all_messages"], status=LIMITED_BY_TELEGRAM,
                  **CTL)
async def cmd_nomute(ctx: CommandContext) -> None:
    app, owner, chat_id = ctx.app, ctx.user_id, ctx.chat_id
    sub = ctx.parsed.first or "list"
    row = await app.controls.get(owner, chat_id, "nomute")
    words = list((row or {}).get("state", {}).get("words") or [])
    rest = [w.strip().lower() for w in ctx.args[1:] if w.strip()]
    if sub in ("add", "добавить", "qo'sh"):
        if not rest:
            raise UsageError()
        words = list(dict.fromkeys(words + [w[:40] for w in rest]))[:50]
        await app.chats.touch(owner, chat_id)
        await app.controls.set(owner, chat_id, "nomute", True, state={"words": words}, connection_id=ctx.conn.id)
    elif sub in ("del", "удалить", "o'chir"):
        words = [w for w in words if w not in rest]
        await app.controls.set(owner, chat_id, "nomute", bool(words) and bool(row and row["enabled"]), state={"words": words})
    elif sub in ("on", "вкл"):
        if not words:
            raise CommandError(ctx.t("controls.snachala_dobavte_slova_nomute_add", p=ctx.prefix))
        await app.controls.set(owner, chat_id, "nomute", True, connection_id=ctx.conn.id)
    elif sub in ("off", "выкл"):
        await app.controls.set(owner, chat_id, "nomute", False)
    elif sub not in ("list", "список", "ro'yxat"):
        raise UsageError()
    await refresh_cards(app, owner, chat_id, "nomute")
    if sub in ("list", "список", "ro'yxat"):
        await ctx.answer("🧹 " + (", ".join(esc(w) for w in words) or ctx.t("controls.slov_net")), private=True)
        return
    await post_card(app, owner, chat_id, "nomute", conn=ctx.conn, ctx=ctx, location="dm")


@registry.command("chat", "chat", aliases=["панель", "cp", "chatpanel"], **CTL)
async def cmd_chat(ctx: CommandContext) -> None:
    from ..handlers.chatmgr import send_chat_panel
    await ctx.app.chats.touch(ctx.user_id, ctx.chat_id)
    await send_chat_panel(ctx.app, ctx.user_id, ctx.chat_id)
    await ctx.cleanup_command(fallback_text="⚙️")
