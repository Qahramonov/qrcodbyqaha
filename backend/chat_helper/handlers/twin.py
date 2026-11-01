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


MODE_TITLES = {"auto": ("🤖 Auto — отвечает сам (с пометкой AI)", "🤖 Auto — o'zi javob beradi (AI belgisi bilan)"),
               "manual": ("✋ Manual — черновик с кнопкой «Отправить»", "✋ Manual — «Yuborish» tugmali qoralama"),
               "draft": ("📝 Draft — только подсказка, без отправки", "📝 Draft — faqat maslahat, yuborilmaydi"),
               "disabled": ("⏸ Выключен", "⏸ O'chirilgan")}


def _bar(v: int) -> str:
    n = round(v / 20)
    return "▰" * n + "▱" * (5 - n)


@screen("twin")
async def screen_twin(app: Any, uid: int, s: dict[str, Any]) -> tuple[str, Any]:
    lang = s["lang"]
    p = await app.twin.get(uid)
    t = lambda ru, uz, **kw: tr(lang, ru, uz, **kw)  # noqa: E731
    lines = [t("🤖 <b>AI-двойник</b>", "🤖 <b>AI-egizak</b>"),
             t("Отвечает в ваших чатах в вашем стиле, когда включён режим AI или Hybrid. Автоответы всегда помечаются как AI.",
               "AI yoki Hybrid rejimi yoqilganda chatlaringizda sizning uslubingizda javob beradi. Avtojavoblar doim AI deb belgilanadi."), "",
             t("Режим: {m}", "Rejim: {m}", m=tr(lang, *MODE_TITLES[p["mode"]])),
             t("Имя: {n} · язык: {l} · образ: {p}", "Ism: {n} · til: {l} · obraz: {p}", n=esc(p["name"] or "—"), l=p["language"], p=p["persona"]),
             t("Стиль: {s} · длина: {d}", "Uslub: {s} · uzunlik: {d}", s=p["style"], d=p["length"]),
             t("Формальность {a} · юмор {b}", "Rasmiylik {a} · hazil {b}", a=_bar(p["formality"]), b=_bar(p["humor"])),
             t("Эмодзи {a} · сленг {b} · фильтр мата: {f}", "Emoji {a} · sleng {b} · so'kinish filtri: {f}", a=_bar(p["emoji"]), b=_bar(p["slang"]),
               f="✅" if p["profanity_filter"] else "❌"),
             t("Задержка ответа: {d} с · часы: {h}", "Javob kechikishi: {d} s · soatlar: {h}", d=p["reply_delay_sec"],
               h=(f"{p['active_from']}–{p['active_to']}" if p["active_from"] else t("всегда", "doim"))),
             t("Примеры вашего стиля: {n} (только добровольно добавленные)", "Uslubingiz namunalari: {n} (faqat ixtiyoriy qo'shilgan)",
               n=len(p["examples"]))]
    if p.get("manner"):
        lines.append(t("Манера: {m}", "Uslub tavsifi: {m}", m=esc(clip(p["manner"], 80))))
    if s["mode"] not in ("ai", "hybrid"):
        lines += ["", t("ℹ️ Сейчас режим автоответчика «{m}» — двойник начнёт отвечать в режимах AI или Hybrid.",
                        "ℹ️ Hozir avtojavob rejimi «{m}» — egizak AI yoki Hybrid rejimlarida javob beradi.", m=s["mode"])]
    rows = [[(("✅ " if p["mode"] == m else "") + {"auto": "🤖 Auto", "manual": "✋ Manual", "draft": "📝 Draft", "disabled": "⏸ Off"}[m],
              f"tw:mode:{m}") for m in MODES],
            [(t("🎭 Стиль", "🎭 Uslub"), "tw:cycle:style"), (t("📏 Длина", "📏 Uzunlik"), "tw:cycle:length"),
             (t("👤 Образ", "👤 Obraz"), "tw:cycle:persona")],
            [(t("Формальность −", "Rasmiylik −"), "tw:dec:formality"), (t("Формальность +", "Rasmiylik +"), "tw:inc:formality")],
            [(t("Юмор −", "Hazil −"), "tw:dec:humor"), (t("Юмор +", "Hazil +"), "tw:inc:humor")],
            [(t("Эмодзи −", "Emoji −"), "tw:dec:emoji"), (t("Эмодзи +", "Emoji +"), "tw:inc:emoji")],
            [(t("Сленг −", "Sleng −"), "tw:dec:slang"), (t("Сленг +", "Sleng +"), "tw:inc:slang")],
            [(t("🤬 Фильтр мата", "🤬 So'kinish filtri"), "tw:toggle:profanity_filter"), (t("⏱ Задержка", "⏱ Kechikish"), "tw:cycle:delay")],
            [(t("🏷 Имя", "🏷 Ism"), "tw:ask:name"), (t("🗣 Манера", "🗣 Uslub tavsifi"), "tw:ask:manner"), (t("🕘 Часы", "🕘 Soatlar"), "tw:ask:hours")],
            [(t("📝 Свой промпт", "📝 O'z prompti"), "tw:ask:prompt"), (t("➕ Пример стиля", "➕ Uslub namunasi"), "tw:ask:example")],
            [(t("🧪 Проверить ответ", "🧪 Javobni sinash"), "tw:ask:test"), (t("🗑 Удалить примеры", "🗑 Namunalarni o'chirish"), "tw:clear")],
            [(t("⬅️ AI", "⬅️ AI"), "m:ai"), (t("🏠 Меню", "🏠 Menyu"), "m:home")]]
    return "\n".join(lines), kb(rows)


PROMPTS = {
    "name": ("🏷 Как зовут двойника? (до 60 символов, «-» — убрать)", "🏷 Egizakning ismi? (60 belgigacha, «-» — olib tashlash)"),
    "manner": ("🗣 Опишите свою манеру общения (например: «коротко, на ты, без официоза»). «-» — убрать.",
               "🗣 Muloqot uslubingizni tasvirlang (masalan: «qisqa, sen deb, rasmiyatsiz»). «-» — olib tashlash."),
    "prompt": ("📝 Пришлите свои инструкции для двойника (до 2000 символов). «-» — убрать.",
               "📝 Egizak uchun ko'rsatmalaringizni yuboring (2000 belgigacha). «-» — olib tashlash."),
    "hours": ("🕘 Часы работы двойника в формате 09:00-21:00. «-» — всегда.", "🕘 Egizak ish soatlari 09:00-21:00 formatida. «-» — doim."),
    "example": ("➕ Пришлите пример того, как вы обычно пишете (ваше собственное сообщение). Он будет использоваться только как образец стиля.",
                "➕ Odatda qanday yozishingiz namunasini yuboring (o'z xabaringiz). U faqat uslub namunasi sifatida ishlatiladi."),
    "test": ("🧪 Напишите сообщение, как будто вам пишет собеседник, — покажу ответ двойника (ничего не отправляется).",
             "🧪 Suhbatdosh yozgandek xabar yozing — egizak javobini ko'rsataman (hech narsa yuborilmaydi)."),
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
                await cb.answer(tr(lang, "🧠 AI-провайдер не настроен.", "🧠 AI provayderi sozlanmagan."), show_alert=True)
                return
            await state.set_state(getattr(TW, arg))
            await cb.answer()
            await cb.message.answer(tr(lang, *PROMPTS[arg]) + "\n" + tr(lang, "Отмена: /cancel", "Bekor qilish: /cancel"))
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
        await message.answer(tr(s["lang"], "Формат: 09:00-21:00", "Format: 09:00-21:00"))
        return
    await _finish(app, uid, message, state)


@router.message(TW.example, F.text)
async def st_example(message: Message, state: FSMContext, app: Any) -> None:
    uid = await ensure_user(app, message)
    s = await app.settings.all(uid)
    try:
        n = await app.twin.add_example(uid, message.text)
    except ValueError:
        await message.answer(tr(s["lang"], "Пример должен быть от 2 до 500 символов.", "Namuna 2 dan 500 belgigacha bo'lishi kerak."))
        return
    await message.answer(tr(s["lang"], "✅ Пример сохранён ({n}).", "✅ Namuna saqlandi ({n}).", n=n))
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
    await message.answer(tr(s["lang"], "🧪 Двойник ответил бы так:\n\n{o}", "🧪 Egizak shunday javob berardi:\n\n{o}", o=esc(out)),
                         reply_markup=kb([[(tr(s["lang"], "⬅️ К настройкам", "⬅️ Sozlamalarga"), "m:twin")]]))


async def _render_twin(app: Any, uid: int, target: Message) -> None:  # used by the .twin command
    s = await app.settings.all(uid)
    text, markup = await screen_twin(app, uid, s)
    await render(target, text, markup, False)
