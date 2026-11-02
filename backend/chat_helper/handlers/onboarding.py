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
        tr(lang, "onboarding.chat_helper"),
        tr(lang, "onboarding.umnyy_pomoschnik_telegram"), "",
        tr(lang, "onboarding.ai_assistent_ai_dvoynik"),
        tr(lang, "onboarding.avtootvetchik_biznes_chasy"),
        tr(lang, "onboarding.afk_taymerom"),
        tr(lang, "onboarding.mute_protect_otdelnyh_chatov"),
        tr(lang, "onboarding.media_studio_igry_komandy_chatah"), "",
        tr(lang, "onboarding.nachala_podklyuchite_svoy_telegram_akkaunt"),
    ])
    rows = [[(tr(lang, "onboarding.podklyuchit"), "m:connect"), (tr(lang, "onboarding.vozmozhnosti"), "m:features")],
            [(tr(lang, "onboarding.yazyk"), "m:lang"), (tr(lang, "onboarding.pomosch"), "m:help")]]
    if acc.is_super:
        rows.append([(tr(lang, "onboarding.admin_panel"), "m:admin")])
    return text, kb(rows)


def wizard_text(app: Any, lang: str) -> str:
    b = bot_username(app)
    return "\n".join([
        tr(lang, "onboarding.podklyuchenie_chat_helper"), "",
        tr(lang, "onboarding.1_skopiruyte_username_bota", b=b),
        tr(lang, "onboarding.2_otkroyte_nastroyki_telegram_izm"),
        tr(lang, "onboarding.3_naydite_razdel_avtomatizatsiya_chatov"),
        tr(lang, "onboarding.4_nazhmite_dobavit_vstavte", b=b),
        tr(lang, "onboarding.5_vyberite_chaty_vse_lichnye"),
        tr(lang, "onboarding.6_prava_otvety_soobscheniya_obyazatelno"),
        tr(lang, "onboarding.7_vernites_syuda_nazhmite_proverit"), "",
        tr(lang, "onboarding.premium_not_needed"),
        tr(lang, "onboarding.bot_rabotaet_cherez_ofitsialnyy_telegram"),
    ])


def wizard_rows(app: Any, lang: str) -> list[list[tuple[str, str]]]:
    b = bot_username(app)
    return [[(tr(lang, "onboarding.skopirovat", b=b), f"copy:@{b}")],
            [(tr(lang, "onboarding.otkryt_nastroyki_telegram"), "url:" + SETTINGS_LINK)],
            [(tr(lang, "onboarding.instruktsiya_kartinke"), "ob:guide")],
            [(tr(lang, "onboarding.proverit_podklyuchenie"), "ob:check")],
            [(tr(lang, "onboarding.nazad"), "m:home")]]


@screen("connect", public=True)
async def screen_connect(app: Any, uid: int, s: dict[str, Any]) -> tuple[str, Any]:
    lang = s["lang"]
    acc = await access(app, uid)
    if not acc.connected:
        conns = await app.connections.for_user(uid)
        text = wizard_text(app, lang)
        if conns:  # known but disabled connection
            text += "\n\n" + tr(lang, "onboarding.ranee_podklyuchenie_bylo_otklyucheno_dobavte")
        return text, kb(wizard_rows(app, lang))
    return await connection_status_screen(app, uid, s)


async def connection_status_screen(app: Any, uid: int, s: dict[str, Any]) -> tuple[str, Any]:
    from ..core.timeutil import fmt_dt
    lang = s["lang"]
    conns = await app.connections.for_user(uid)
    lines = [tr(lang, "onboarding.podklyuchenie_akkaunta"), ""]
    rows: list[list[tuple[str, str]]] = []
    for i, c in enumerate(conns[:5]):
        rep = inspect(c.rights, c.is_enabled, lang, c.paused)
        granted = sum(1 for v in c.rights.values() if v)
        lines.append(f"{status_title(c.status, lang)} · {fmt_dt(c.connected_at, s['timezone'])}"
                     + (tr(lang, "onboarding.pauza") if c.paused else ""))
        lines.append(tr(lang, "onboarding.prava_vozmozhnostey",
                        g=granted, n=len(c.rights), a=sum(1 for cap in rep["capabilities"] if cap["available"])))
        rows.append([(tr(lang, "onboarding.prava"), f"conn:insp:{i}"),
                     ((tr(lang, "onboarding.vozobnovit") if c.paused else tr(lang, "onboarding.pauza_2")),
                      f"conn:{'resume' if c.paused else 'pause'}:{i}")])
    lines += ["", tr(lang, "onboarding.otklyuchit_bota_nastroyki_izm_avtomatizatsiya")]
    rows.append([(tr(lang, "onboarding.obnovit_status"), "ob:check")])
    rows.append([(tr(lang, "onboarding.nazad"), "m:home")])
    return "\n".join(lines), kb(rows)


@screen("features", public=True)
async def screen_features(app: Any, uid: int, s: dict[str, Any]) -> tuple[str, Any]:
    lang = s["lang"]
    p = s["prefix"]
    text = "\n".join([
        tr(lang, "onboarding.vozmozhnosti_chat_helper"), "",
        tr(lang, "onboarding.komandy_pryamo_chatah_pishite_afk", p=p),
        tr(lang, "onboarding.knopki_upravleniya_pod_soobscheniyami_vyklyuchit"),
        tr(lang, "onboarding.ai_otvety_perevod_pereskaz_podskazki"),
        tr(lang, "onboarding.mute_novye_vhodyaschie_vybrannom_chate"),
        tr(lang, "onboarding.media_studio_kruzhki_revers_skorost"),
        tr(lang, "onboarding.igry_duel_krestiki_noliki_viktorina"),
        tr(lang, "onboarding.chat_helper_control_prilozhenie_android"), "",
        tr(lang, "onboarding.ogranicheniya_telegram_tolko_lichnye_chaty"),
    ])
    rows = [[(tr(lang, "onboarding.podklyuchit"), "m:connect")], [(tr(lang, "onboarding.nazad"), "m:home")]]
    return text, kb(rows)


@screen("lang", public=True)
async def screen_lang(app: Any, uid: int, s: dict[str, Any]) -> tuple[str, Any]:
    lang = s["lang"]
    text = tr(lang, "onboarding.yazyk_interfeysa_vyberite_yazyk_menyu")
    rows = [[(("✅ " if lang == "ru" else "") + "🇷🇺 Русский", "ob:lang:ru"), (("✅ " if lang == "uz" else "") + "🇺🇿 O'zbekcha", "ob:lang:uz")],
            [(tr(lang, "onboarding.nazad"), "m:home")]]
    return text, kb(rows)


# ---------------------------------------------------------------------------------------------------------
async def send_wizard(app: Any, uid: int, target: Message, edit: bool = False) -> None:
    s = await app.settings.all(uid)
    text, markup = await screen_connect(app, uid, s)
    try:
        await render(target, text, markup, edit)
    except TelegramBadRequest as e:
        log.warning("wizard keyboard rejected (%s) — retrying without tg:// link", str(e)[:120])
        await target.answer(text + "\n\n" + tr(s["lang"], "onboarding.otkroyte_nastroyki_telegram_vruchnuyu"),
                            reply_markup=without_tg_links(markup), disable_web_page_preview=True)


async def send_infographic(app: Any, uid: int, target: Message) -> None:
    s = await app.settings.all(uid)
    lang = s["lang"]
    caption = tr(lang, "onboarding.kak_podklyuchit_chat_helper_6", b=bot_username(app))
    markup = kb(wizard_rows(app, lang)[:2] + [[(tr(lang, "onboarding.proverit_podklyuchenie"), "ob:check")]])
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
        lines = [tr(lang, "onboarding.podklyuchenie_aktivno"), rep["status_title"], ""]
        if ok:
            lines.append(tr(lang, "onboarding.dostupno", n=len(ok)))
        if missing:
            lines.append(tr(lang, "onboarding.bez_prav_nedostupno_podrobnee_prava",
                            n=len(missing)))
        rows = [[(tr(lang, "onboarding.otkryt_menyu"), "m:home")],
                [(tr(lang, "onboarding.prava"), "conn:insp:0")]]
        return True, "\n".join(lines), kb(rows)
    conns = await app.connections.for_user(uid)
    if conns:
        text = tr(lang, "onboarding.podklyuchenie_naydeno_no_vyklyucheno_otkroyte")
    else:
        text = "\n".join([
            tr(lang, "onboarding.podklyuchenie_poka_naydeno"), "",
            tr(lang, "onboarding.proverte"),
            tr(lang, "onboarding.bot_dobavlen_avtomatizatsiya_chatov_username", b=bot_username(app)),
            tr(lang, "onboarding.vybran_hotya_by_odin_chat"),
            tr(lang, "onboarding.bot_postavlen_pauzu"), "",
            tr(lang, "onboarding.esli_vy_tolko_chto_podklyuchili"),
        ])
    return False, text, kb(wizard_rows(app, lang)[:2] + [[(tr(lang, "onboarding.proverit_eschyo_raz"), "ob:check")],
                                                          [(tr(lang, "onboarding.instruktsiya_kartinke"), "ob:guide")]])


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
            await cb.answer(tr(s["lang"], "onboarding.podozhdite", s=retry), show_alert=True)
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
    text = tr(lang, "onboarding.gotovo_otkroyte_menyu_chtoby_nastroit")
    return text, kb([[(tr(lang, "onboarding.otkryt_menyu"), "m:home")]])

