"""«🤖 AI-двойник» screen in the bot DM: mode, style knobs, examples (voluntary), playground."""
from __future__ import annotations

from typing import Any

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from ..ai.service import AIError
from ..ai.twin import LENGTHS, MODES, PERSONAS, STYLES
from ..keyboards import kb
from ..localization import tr
from ..security.sanitize import clip, esc
from .ui import PanelGate, ensure_user, render, screen, show

router = Router(name="twin")
router.message.filter(F.chat.type == "private")
router.callback_query.filter(F.message.chat.type == "private")
router.message.middleware(PanelGate())
router.callback_query.middleware(PanelGate())


class TW(StatesGroup):
    name = State()
    manner = State()
    prompt = State()
    hours = State()
    example = State()
    test = State()


MODE_TITLES = {"auto": ("twin.mode_titles.auto_otvechaet_sam_pometkoy_ai"),
               "manual": ("twin.mode_titles.manual_chernovik_knopkoy_otpravit"),
               "draft": ("twin.mode_titles.draft_tolko_podskazka_bez_otpravki"),
               "disabled": ("twin.mode_titles.vyklyuchen")}


def _bar(v: int) -> str:
    n = round(v / 20)
    return "▰" * n + "▱" * (5 - n)


@screen("twin")
async def screen_twin(app: Any, uid: int, s: dict[str, Any]) -> tuple[str, Any]:
    lang = s["lang"]
    p = await app.twin.get(uid)
    t = lambda key, **kw: tr(lang, key, **kw)  # noqa: E731
    lines = [t("twin.ai_dvoynik"),
             t("twin.otvechaet_vashih_chatah_vashem_stile"), "",
             t("twin.rezhim", m=tr(lang, MODE_TITLES[p["mode"]])),
             t("twin.imya_yazyk_obraz", n=esc(p["name"] or "—"), l=p["language"], p=p["persona"]),
             t("twin.stil_dlina", s=p["style"], d=p["length"]),
             t("twin.formalnost_yumor", a=_bar(p["formality"]), b=_bar(p["humor"])),
             t("twin.emodzi_sleng_filtr_mata", a=_bar(p["emoji"]), b=_bar(p["slang"]),
               f="✅" if p["profanity_filter"] else "❌"),
             t("twin.zaderzhka_otveta_chasy", d=p["reply_delay_sec"],
               h=(f"{p['active_from']}–{p['active_to']}" if p["active_from"] else t("twin.vsegda"))),
             t("twin.primery_vashego_stilya_tolko_dobrovolno",
               n=len(p["examples"]))]
    if p.get("manner"):
        lines.append(t("twin.manera", m=esc(clip(p["manner"], 80))))
    if s["mode"] not in ("ai", "hybrid"):
        lines += ["", t("twin.seychas_rezhim_avtootvetchika_dvoynik_nachnyot", m=s["mode"])]
    rows = [[(("✅ " if p["mode"] == m else "") + {"auto": "🤖 Auto", "manual": "✋ Manual", "draft": "📝 Draft", "disabled": "⏸ Off"}[m],
              f"tw:mode:{m}") for m in MODES],
            [(t("twin.stil"), "tw:cycle:style"), (t("twin.dlina"), "tw:cycle:length"),
             (t("twin.obraz"), "tw:cycle:persona")],
            [(t("twin.formalnost"), "tw:dec:formality"), (t("twin.formalnost_2"), "tw:inc:formality")],
            [(t("twin.yumor"), "tw:dec:humor"), (t("twin.yumor_2"), "tw:inc:humor")],
            [(t("twin.emodzi"), "tw:dec:emoji"), (t("twin.emodzi_2"), "tw:inc:emoji")],
            [(t("twin.sleng"), "tw:dec:slang"), (t("twin.sleng_2"), "tw:inc:slang")],
            [(t("twin.filtr_mata"), "tw:toggle:profanity_filter"), (t("twin.zaderzhka"), "tw:cycle:delay")],
            [(t("twin.imya"), "tw:ask:name"), (t("twin.manera_2"), "tw:ask:manner"), (t("twin.chasy"), "tw:ask:hours")],
            [(t("twin.svoy_prompt"), "tw:ask:prompt"), (t("twin.primer_stilya"), "tw:ask:example")],
            [(t("twin.proverit_otvet"), "tw:ask:test"), (t("twin.udalit_primery"), "tw:clear")],
            [(t("twin.ai"), "m:ai"), (t("twin.menyu"), "m:home")]]
    return "\n".join(lines), kb(rows)


PROMPTS = {
    "name": ("twin.prompts.kak_zovut_dvoynika_60_simvolov"),
    "manner": ("twin.prompts.opishite_svoyu_maneru_obscheniya_naprimer"),
    "prompt": ("twin.prompts.prishlite_svoi_instruktsii_dvoynika_2000"),
    "hours": ("twin.prompts.chasy_raboty_dvoynika_formate_09"),
    "example": ("twin.prompts.prishlite_primer_togo_kak_vy"),
    "test": ("twin.prompts.napishite_soobschenie_kak_budto_vam"),
}


@router.callback_query(F.data.startswith("tw:"))
async def cb_twin(cb: CallbackQuery, state: FSMContext, app: Any) -> None:
    uid = await ensure_user(app, cb)
    s = await app.settings.all(uid)
    lang = s["lang"]
    parts = (cb.data or "").split(":")
    action = parts[1] if len(parts) > 1 else ""
    arg = parts[2] if len(parts) > 2 else ""
    p = await app.twin.get(uid)
    try:
        if action == "mode" and arg in MODES:
            await app.twin.update(uid, mode=arg)
        elif action == "cycle" and arg in ("style", "length", "persona", "delay"):
            if arg == "delay":
                seq = [0, 10, 30, 60, 120]
                cur = p["reply_delay_sec"]
                await app.twin.update(uid, reply_delay_sec=seq[(seq.index(cur) + 1) % len(seq)] if cur in seq else 0)
            else:
                seq = {"style": STYLES, "length": LENGTHS, "persona": PERSONAS}[arg]
                await app.twin.update(uid, **{arg: seq[(seq.index(p[arg]) + 1) % len(seq)]})
        elif action in ("inc", "dec") and arg in ("formality", "humor", "emoji", "slang"):
            await app.twin.update(uid, **{arg: p[arg] + (20 if action == "inc" else -20)})
        elif action == "toggle" and arg == "profanity_filter":
            await app.twin.update(uid, profanity_filter=not p["profanity_filter"])
        elif action == "clear":
            await app.twin.clear_examples(uid)
        elif action == "ask" and arg in PROMPTS:
            if arg == "test" and not app.ai.available():
                await cb.answer(tr(lang, "twin.ai_provayder_nastroen"), show_alert=True)
                return
            await state.set_state(getattr(TW, arg))
            await cb.answer()
            await cb.message.answer(tr(lang, PROMPTS[arg]) + "\n" + tr(lang, "twin.otmena_cancel"))
            return
    except ValueError as e:
        await cb.answer(str(e), show_alert=True)
        return
    await cb.answer("✅")
    await show(app, uid, "twin", cb.message, True)


async def _finish(app: Any, uid: int, message: Message, state: FSMContext) -> None:
    await state.clear()
    await show(app, uid, "twin", message, False)


@router.message(TW.name, F.text)
async def st_name(message: Message, state: FSMContext, app: Any) -> None:
    uid = await ensure_user(app, message)
    await app.twin.update(uid, name=None if message.text.strip() == "-" else message.text)
    await _finish(app, uid, message, state)


@router.message(TW.manner, F.text)
async def st_manner(message: Message, state: FSMContext, app: Any) -> None:
    uid = await ensure_user(app, message)
    await app.twin.update(uid, manner=None if message.text.strip() == "-" else message.text)
    await _finish(app, uid, message, state)


@router.message(TW.prompt, F.text)
async def st_prompt(message: Message, state: FSMContext, app: Any) -> None:
    uid = await ensure_user(app, message)
    await app.twin.update(uid, custom_prompt=None if message.text.strip() == "-" else message.text)
    await _finish(app, uid, message, state)


@router.message(TW.hours, F.text)
async def st_hours(message: Message, state: FSMContext, app: Any) -> None:
    uid = await ensure_user(app, message)
    s = await app.settings.all(uid)
    txt = message.text.strip()
    try:
        if txt == "-":
            await app.twin.update(uid, active_from=None, active_to=None)
        else:
            a, _, b = txt.replace("–", "-").partition("-")
            await app.twin.update(uid, active_from=a.strip(), active_to=b.strip())
    except ValueError:
        await message.answer(tr(s["lang"], "twin.format_09_00_21_00"))
        return
    await _finish(app, uid, message, state)


@router.message(TW.example, F.text)
async def st_example(message: Message, state: FSMContext, app: Any) -> None:
    uid = await ensure_user(app, message)
    s = await app.settings.all(uid)
    try:
        n = await app.twin.add_example(uid, message.text)
    except ValueError:
        await message.answer(tr(s["lang"], "twin.primer_dolzhen_byt_2_500"))
        return
    await message.answer(tr(s["lang"], "twin.primer_sohranyon", n=n))
    await _finish(app, uid, message, state)


@router.message(TW.test, F.text)
async def st_test(message: Message, state: FSMContext, app: Any) -> None:
    uid = await ensure_user(app, message)
    s = await app.settings.all(uid)
    await state.clear()
    try:
        out = await app.twin.preview(uid, message.text[:1000], s)
    except AIError as e:
        from ..ai.auto import ai_error_text
        out = ai_error_text(s["lang"], e)
    await message.answer(tr(s["lang"], "twin.dvoynik_otvetil_by_tak", o=esc(out)),
                         reply_markup=kb([[(tr(s["lang"], "twin.nastroykam"), "m:twin")]]))


async def _render_twin(app: Any, uid: int, target: Message) -> None:  # used by the .twin command
    s = await app.settings.all(uid)
    text, markup = await screen_twin(app, uid, s)
    await render(target, text, markup, False)
