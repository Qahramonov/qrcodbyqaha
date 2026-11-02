"""AI and Voice Studio commands."""
from __future__ import annotations

import io
import re
import secrets
import time
from typing import Any

from aiogram import F, Router
from aiogram.types import BufferedInputFile, CallbackQuery

from ..ai.auto import ai_error_text
from ..ai.prompts import TASK_PROMPTS
from ..ai.providers.base import ImageInput
from ..ai.service import AIError
from ..commands.context import CommandContext, CommandError, UsageError
from ..commands.registry import REQUIRES_API_KEY, registry
from ..keyboards import kb
from ..security.sanitize import clip, esc, wrap_untrusted
from .media_util import require_media

router = Router(name="ai_cmds")

LANGS = {
    "en": "English", "ru": "Russian", "uz": "Uzbek", "tr": "Turkish", "de": "German", "fr": "French", "es": "Spanish",
    "it": "Italian", "ar": "Arabic", "zh": "Chinese", "ja": "Japanese", "ko": "Korean", "kk": "Kazakh", "tg": "Tajik",
    "ky": "Kyrgyz", "uk": "Ukrainian", "pl": "Polish", "pt": "Portuguese", "hi": "Hindi", "fa": "Persian", "az": "Azerbaijani",
}
LANG_ALIASES = {"англ": "en", "английский": "en", "рус": "ru", "русский": "ru", "узб": "uz", "узбекский": "uz", "ingliz": "en",
                "rus": "ru", "o'zbek": "uz", "турецкий": "tr", "немецкий": "de", "китайский": "zh"}
_CYR = re.compile(r"[а-яёўқғҳ]", re.IGNORECASE)

AI_COMMON = dict(deps=["ai"], status=REQUIRES_API_KEY, rate=(10, 60))


def _target_lang(word: str) -> str | None:
    w = word.lower().strip()
    if w in LANGS:
        return w
    return LANG_ALIASES.get(w)


async def _run(ctx: CommandContext, task: str, text: str, *, max_tokens: int = 700, system_extra: str = "", **fmt: Any) -> str:
    await ctx.require_ai()
    lang_name = LANGS.get(fmt.pop("lang_code", None) or ctx.lang, "Russian")
    instruction = TASK_PROMPTS[task].format(lang=lang_name, **fmt) + (("\n" + system_extra) if system_extra else "")
    try:
        await ctx.typing()
        res = await ctx.app.ai.ask(ctx.user_id, wrap_untrusted(text, "text"), ctx.settings, task_system=instruction,
                                   kind=task, max_tokens=max_tokens)
    except AIError as e:
        raise CommandError(ai_error_text(ctx.lang, e)) from None
    return res.text


def _need_text(ctx: CommandContext, text: str) -> str:
    text = (text or "").strip()
    if not text:
        raise UsageError()
    if len(text) > 8000:
        raise CommandError(ctx.t("ai_cmds.tekst_slishkom_dlinnyy_maks_8000"))
    return text


@registry.command("ai", "ai", aliases=["gpt", "ask", "гпт", "спроси", "ии"],
                  **AI_COMMON)
async def cmd_gpt(ctx: CommandContext) -> None:
    await ctx.require_ai()
    question = ctx.raw.strip()
    reply_text = ctx.reply_text()
    if not question and not reply_text:
        raise UsageError()
    prompt = question or ctx.t("ai_cmds.otvet_soobschenie")
    context = []
    if reply_text:
        context = [{"role": "user", "content": "Context message:\n" + wrap_untrusted(clip(reply_text, 4000))},
                   {"role": "assistant", "content": "OK."}]
    await ctx.typing()
    try:
        res = await ctx.app.ai.ask(ctx.user_id, prompt, ctx.settings, context=context, kind="gpt")
    except AIError as e:
        raise CommandError(ai_error_text(ctx.lang, e)) from None
    head = f"🧠 <b>{esc(clip(question, 200))}</b>\n\n" if question else "🧠 "
    await ctx.answer(head + esc(res.text)[:3600])


@registry.command("translate", "ai", aliases=["tr", "перевод", "переведи", "tarjima"],
                  **AI_COMMON)
async def cmd_translate(ctx: CommandContext) -> None:
    args = ctx.raw.split(None, 1)
    target = _target_lang(args[0]) if args else None
    text = (args[1] if target and len(args) > 1 else ("" if target else ctx.raw)) or ctx.reply_text()
    text = _need_text(ctx, text)
    if not target:
        target = "en" if _CYR.search(text) else ctx.lang
    out = await _run(ctx, "translate", text, lang_code=target)
    await ctx.answer(esc(out))


async def chat_history_text(app: Any, owner: int, chat_id: int, n: int) -> str:
    """Last *n* stored messages of the chat (only this owner's data; requires history storage to be enabled)."""
    rows = await app.db.fetchall("SELECT outgoing, msg_type, text, created_at FROM chat_messages WHERE owner_id=? AND chat_id=? "
                                 "ORDER BY id DESC LIMIT ?", (owner, chat_id, n))
    lines = [f"{'Me' if r['outgoing'] else 'Them'}: {r['text'] or '[' + (r['msg_type'] or 'message') + ']'}" for r in reversed(rows)]
    if not lines:  # older installs: fall back to the AI conversation history
        hist = await app.ai.memory.history(owner, chat_id, n)
        lines = [f"{'Them' if h['role'] == 'user' else 'Me'}: {h['content']}" for h in hist]
    return "\n".join(lines)


async def summarize_chat(app: Any, owner: int, chat_id: int, n: int, lang: str) -> str:
    from ..localization import tr as _tr
    if not app.ai.available():
        return _tr(lang, "ai_cmds.sum_no_ai")
    history = await chat_history_text(app, owner, chat_id, n)
    if not history:
        return _tr(lang, "ai_cmds.sum_no_history")
    s = await app.settings.all(owner)
    try:
        res = await app.ai.ask(owner, wrap_untrusted(history, "conversation"), s,
                               task_system=TASK_PROMPTS["summary_chat"].format(lang=LANGS.get(lang, "Russian")), kind="summary_chat",
                               max_tokens=900)
    except AIError as e:
        return ai_error_text(lang, e)
    title = (await app.chats.get(owner, chat_id) or {}).get("title") or str(chat_id)
    return _tr(lang, "ai_cmds.sum_result", t=esc(title), n=history.count("\n") + 1, x=esc(res.text))


@registry.command("sum", "ai", aliases=["пересказ", "qaytaaytish"],
                  where="business", **AI_COMMON)
async def cmd_sum(ctx: CommandContext) -> None:
    n = 30
    if ctx.args:
        if not ctx.parsed.first.isdigit() or not 10 <= int(ctx.parsed.first) <= 100:
            raise UsageError(ctx.t("ai_cmds.chislo_soobscheniy_10_100"))
        n = int(ctx.parsed.first)
    await ctx.require_ai()
    await ctx.cleanup_command(fallback_text="📝")
    await ctx.app.sender.send_text(ctx.user_id, await summarize_chat(ctx.app, ctx.user_id, ctx.chat_id, n, ctx.lang))


@registry.command("summary", "ai", aliases=["кратко", "резюме", "xulosa"],
                  **AI_COMMON)
async def cmd_summary(ctx: CommandContext) -> None:
    text = ctx.raw or ctx.reply_text()
    task = "summary"
    if not text and ctx.is_business:
        hist = await ctx.app.ai.memory.history(ctx.user_id, ctx.chat_id, 40)
        if not hist:
            raise CommandError(ctx.t("ai_cmds.net_sohranyonnoy_istorii_etogo_chata"))
        text = "\n".join(f"{'Them' if h['role'] == 'user' else 'Assistant'}: {h['content']}" for h in hist)
        task = "summary_chat"
    out = await _run(ctx, task, _need_text(ctx, text))
    await ctx.answer("📝 " + esc(out), private=task == "summary_chat")


@registry.command("rewrite", "ai", aliases=["перефразируй", "rw", "qaytayoz"],
                  **AI_COMMON)
async def cmd_rewrite(ctx: CommandContext) -> None:
    styles = {"formal": "formal and polite", "friendly": "friendly", "short": "shorter", "funny": "funny", "polite": "very polite",
              "официально": "formal and polite", "коротко": "shorter", "вежливо": "very polite", "смешно": "funny"}
    args = ctx.raw.split(None, 1)
    style = styles.get(args[0].lower()) if args else None
    text = (args[1] if style and len(args) > 1 else ("" if style else ctx.raw)) or ctx.reply_text()
    out = await _run(ctx, "rewrite", _need_text(ctx, text), style=style or "clearer and more natural",
                     lang_code="uz" if not _CYR.search(text) and ctx.lang == "uz" else ("ru" if _CYR.search(text) else "en"))
    await ctx.answer(esc(out))


@registry.command("grammar", "ai", aliases=["грамматика", "imlo"], **AI_COMMON)
async def cmd_grammar(ctx: CommandContext) -> None:
    out = await _run(ctx, "grammar", _need_text(ctx, ctx.raw or ctx.reply_text()))
    await ctx.answer("✍️ " + esc(out))


@registry.command("explain", "ai", aliases=["объясни", "tushuntir"], **AI_COMMON)
async def cmd_explain(ctx: CommandContext) -> None:
    out = await _run(ctx, "explain", _need_text(ctx, ctx.raw or ctx.reply_text()))
    await ctx.answer("📚 " + esc(out))


@registry.command("code", "ai", aliases=["код", "kod"], min_plan="free", **AI_COMMON)
async def cmd_code(ctx: CommandContext) -> None:
    out = await _run(ctx, "code", _need_text(ctx, ctx.raw or ctx.reply_text()), max_tokens=1500)
    await ctx.answer("👨‍💻 <pre>" + esc(out)[:3800] + "</pre>")


@registry.command("analyze", "ai", aliases=["анализ", "tahlil"], needs_reply=False, **AI_COMMON)
async def cmd_analyze(ctx: CommandContext) -> None:
    out = await _run(ctx, "analyze", _need_text(ctx, ctx.reply_text() or ctx.raw))
    await ctx.answer("🔎 " + esc(out), private=True)


@registry.command("smart", "ai", aliases=["умно", "aqlli"], where="business", needs_reply=True, **AI_COMMON)
async def cmd_smart(ctx: CommandContext) -> None:
    text = _need_text(ctx, ctx.reply_text())
    out = await _run(ctx, "smart", text, system_extra=("Owner's guidance: " + ctx.raw[:300]) if ctx.raw else "")
    await ctx.answer(esc(out))


_HINTS: dict[str, dict[str, Any]] = {}


@registry.command("hint", "ai", aliases=["подсказка", "варианты", "maslahat"],
                  **AI_COMMON)
async def cmd_hint(ctx: CommandContext) -> None:
    text = _need_text(ctx, ctx.reply_text() or ctx.raw)
    out = await _run(ctx, "hint", text, max_tokens=400)
    options = [re.sub(r"^\s*\d+[.)]\s*", "", line).strip() for line in out.splitlines() if re.match(r"^\s*\d+[.)]", line)]
    options = [o for o in options if o][:3] or [out.strip()]
    rows = []
    if ctx.is_business and ctx.conn:
        token = secrets.token_hex(4)
        _HINTS[token] = {"user_id": ctx.user_id, "conn": ctx.conn.id, "chat_id": ctx.chat_id,
                         "reply_to": ctx.reply.message_id if ctx.reply else None, "options": options, "ts": time.time()}
        rows = [[(f"📤 {i + 1}", f"hs:{token}:{i}") for i in range(len(options))]]
        for k in [k for k, v in _HINTS.items() if time.time() - v["ts"] > 3600]:
            _HINTS.pop(k, None)
    body = "💡 <b>" + ctx.t("ai_cmds.varianty_otveta") + "</b>\n\n" + "\n\n".join(f"{i + 1}. {esc(o)}" for i, o in enumerate(options))
    await ctx.answer(body, markup=kb(rows) if rows else None, private=True)


@router.callback_query(F.data.startswith("hs:"))
async def cb_hint_send(cb: CallbackQuery, app: Any) -> None:
    _, token, idx = cb.data.split(":")
    item = _HINTS.get(token)
    if not item or item["user_id"] != cb.from_user.id or not idx.isdigit() or int(idx) >= len(item["options"]):
        await cb.answer("—")
        return
    conn = await app.connections.get(item["conn"])
    if conn is None or conn.user_id != cb.from_user.id:
        await cb.answer("—")
        return
    res = await app.sender.send_text(item["chat_id"], esc(item["options"][int(idx)]), bc_id=conn.id, reply_to=item["reply_to"])
    await cb.answer("✅" if res.ok else f"⚠️ {res.kind}", show_alert=not res.ok)


@router.callback_query(F.data.startswith("hint:"))
async def cb_hint_from_alert(cb: CallbackQuery, app: Any) -> None:
    """'💡 Варианты ответа' button from Smart Inbox alerts: uses the stored preview of the chat."""
    chat_id = cb.data.split(":")[1]
    if not chat_id.lstrip("-").isdigit():
        await cb.answer()
        return
    row = await app.chats.get(cb.from_user.id, int(chat_id))
    s = await app.settings.all(cb.from_user.id)
    if not row or not row.get("last_preview"):
        await cb.answer("—")
        return
    await cb.answer()
    try:
        res = await app.ai.ask(cb.from_user.id, wrap_untrusted(row["last_preview"]), s, task_system=TASK_PROMPTS["hint"], kind="hint")
        await cb.message.answer("💡 " + esc(res.text))
    except AIError as e:
        await cb.message.answer(ai_error_text(s["lang"], e))


@registry.command("remember", "ai", aliases=["запомни", "eslab"], rate=(20, 60), sandbox_safe=False)
async def cmd_remember(ctx: CommandContext) -> None:
    fact = _need_text(ctx, ctx.raw)
    limit = await ctx.app.subs.limit(ctx.user_id, "ai_memory_facts")
    if limit is not None and await ctx.app.ai.memory.count(ctx.user_id) >= limit:
        raise CommandError(ctx.t("ai_cmds.limit_faktov_tarifa", l=limit))
    if not ctx.settings.get("ai_long_memory"):
        await ctx.app.settings.set(ctx.user_id, "ai_long_memory", True)
    mid = await ctx.app.ai.memory.remember(ctx.user_id, fact, ttl_days=ctx.settings.get("ai_memory_ttl_days"))
    await ctx.answer(ctx.t("ai_cmds.zapomnil_dolgaya_pamyat_vklyuchena_udalit", i=mid, p=ctx.prefix), private=True)


@registry.command("forget", "ai", aliases=["забудь", "unut"], rate=(20, 60))
async def cmd_forget(ctx: CommandContext) -> None:
    arg = ctx.raw.strip()
    if not arg:
        raise UsageError()
    mem = ctx.app.ai.memory
    if arg.lower() in ("all", "всё", "все", "hammasi"):
        n = await mem.clear_all(ctx.user_id)
    elif arg.lstrip("#").isdigit():
        n = await mem.forget(ctx.user_id, memory_id=int(arg.lstrip("#")))
    else:
        n = await mem.forget(ctx.user_id, query=arg)
    await ctx.answer(ctx.t("ai_cmds.udaleno", n=n), private=True)


@registry.command("prompt", "ai", aliases=["промпт"], )
async def cmd_prompt(ctx: CommandContext) -> None:
    ai = ctx.app.ai
    prof = await ai.active_profile(ctx.user_id)
    if not ctx.raw:
        cur = (prof or {}).get("system_prompt") or ctx.t("ai_cmds.zadan")
        await ctx.answer(ctx.t("ai_cmds.tekuschiy_prompt_profilya",
                               n=esc((prof or {}).get("name") or "default"), p=esc(cur)), private=True)
        return
    value = None if ctx.raw.strip().lower() in ("reset", "сброс") else ctx.raw[:4000]
    if prof is None:
        prof = await ai.create_profile(ctx.user_id, {"name": "Default", "system_prompt": value, "mode": ctx.settings["ai_style"]})
    else:
        await ai.update_profile(ctx.user_id, prof["id"], {"system_prompt": value})
    await ctx.answer(ctx.t("ai_cmds.prompt_sohranyon"), private=True)


@registry.command("context", "ai", aliases=["контекст"], )
async def cmd_context(ctx: CommandContext) -> None:
    st = await ctx.app.ai.memory.chat_stats(ctx.user_id, ctx.chat_id)
    await ctx.answer(ctx.t("ai_cmds.kontekst_chata_soobscheniy_simvolov_faktov",
                           m=st.get("messages", 0), c=st.get("chars", 0), f=st.get("facts", 0),
                           r=ctx.settings["history_retention_days"], h="on" if ctx.settings["ai_store_history"] else "off"), private=True)


@registry.command("resetai", "ai", aliases=["сбросии", "aireset"], )
async def cmd_resetai(ctx: CommandContext) -> None:
    n = await ctx.app.ai.memory.clear_chat(ctx.user_id, ctx.chat_id)
    await ctx.answer(ctx.t("ai_cmds.kontekst_ochischen", n=n), private=True)


@registry.command("vision", "ai", aliases=["зрение", "фото", "rasm"], **AI_COMMON)
async def cmd_vision(ctx: CommandContext) -> None:
    await ctx.require_ai()
    ref = require_media(ctx, image=True)
    buf = io.BytesIO()
    await ctx.app.bot.download(ref.file_id, destination=buf)
    q = ctx.raw or ctx.t("ai_cmds.opishi_chto_izobrazhenii")
    await ctx.typing()
    try:
        res = await ctx.app.ai.ask(ctx.user_id, q, ctx.settings, images=[ImageInput(buf.getvalue(), "image/jpeg")], kind="vision")
    except AIError as e:
        raise CommandError(ai_error_text(ctx.lang, e)) from None
    await ctx.answer("👁 " + esc(res.text))


async def _stt(ctx: CommandContext) -> str:
    ref = require_media(ctx, av=True)
    buf = io.BytesIO()
    await ctx.app.bot.download(ref.file_id, destination=buf)
    mime = {"voice": "audio/ogg", "video_note": "video/mp4", "video": "video/mp4", "audio": ref.mime}.get(ref.kind, ref.mime)
    name = {"voice": "voice.ogg", "video_note": "note.mp4", "video": "video.mp4"}.get(ref.kind, ref.file_name or "audio.mp3")
    data = buf.getvalue()
    if ref.has_video and ctx.app.health.ffmpeg_ok:
        data = await ctx.app.media.extract_audio_bytes(data)
        mime, name = "audio/ogg", "audio.ogg"
    await ctx.typing("typing")
    try:
        res = await ctx.app.ai.transcribe(ctx.user_id, data, name, mime, ref.duration)
    except AIError as e:
        raise CommandError(ai_error_text(ctx.lang, e)) from None
    return res.text


@registry.command("stt", "voice", aliases=["текст", "расшифруй", "v2t", "matn"], deps=["ai_stt"], status=REQUIRES_API_KEY, rate=(10, 60))
async def cmd_stt(ctx: CommandContext) -> None:
    text = await _stt(ctx)
    await ctx.answer("🎙 " + esc(text or "—"))


@registry.command("vtranslate", "voice", aliases=["перевестиголос", "vtr"], deps=["ai_stt", "ai"],
                  status=REQUIRES_API_KEY, rate=(10, 60))
async def cmd_vtranslate(ctx: CommandContext) -> None:
    target = _target_lang(ctx.parsed.first) if ctx.args else None
    text = await _stt(ctx)
    out = await _run(ctx, "translate", _need_text(ctx, text), lang_code=target or ("en" if _CYR.search(text) else ctx.lang))
    await ctx.answer(f"🎙 <i>{esc(clip(text, 800))}</i>\n\n🌐 {esc(out)}")


@registry.command("vreply", "voice", aliases=["ответголос"], deps=["ai_stt", "ai"], status=REQUIRES_API_KEY, rate=(10, 60))
async def cmd_vreply(ctx: CommandContext) -> None:
    text = await _stt(ctx)
    out = await _run(ctx, "smart", _need_text(ctx, text))
    await ctx.answer(f"🎙 <i>{esc(clip(text, 600))}</i>\n\n💬 {esc(out)}", private=True)


@registry.command("tts", "voice", aliases=["say", "скажи", "озвучь", "ayt"],
                  rate=(10, 60))
async def cmd_tts(ctx: CommandContext) -> None:
    text = _need_text(ctx, ctx.raw or ctx.reply_text())[:1000]
    await ctx.typing("record_voice")
    try:
        path = await ctx.app.media.tts(ctx.user_id, text, ctx.lang)
    except RuntimeError as e:
        raise CommandError(str(e)) from None
    from aiogram.types import FSInputFile
    res = await ctx.send_media("voice", FSInputFile(path), reply_to=ctx.reply.message_id if ctx.reply else None)
    ctx.app.media.files.discard(path)
    if res.ok:
        await ctx.cleanup_command(fallback_text="🔊")


__all__ = ["router", "BufferedInputFile"]


@registry.command("twin", "ai", aliases=["двойник", "egizak"],
                  rate=(20, 60))
async def cmd_twin(ctx: CommandContext) -> None:
    app = ctx.app
    sub = ctx.parsed.first
    modes = {"auto": "auto", "manual": "manual", "draft": "draft", "off": "disabled", "выкл": "disabled", "disabled": "disabled"}
    if sub in modes:
        await app.twin.update(ctx.user_id, mode=modes[sub])
        await ctx.answer(ctx.t("ai_cmds.rezhim_ai_dvoynika", m=modes[sub]), private=True)
        return
    if sub in ("learn", "учись", "o'rgan"):
        text = ctx.raw.split(None, 1)[1] if len(ctx.raw.split(None, 1)) > 1 else ""
        if not text and ctx.reply is not None:
            if ctx.reply.from_user is None or ctx.reply.from_user.id != ctx.user_id:
                raise CommandError(ctx.t("ai_cmds.dobavlyat_mozhno_tolko_vashi_soobscheniya"))
            text = ctx.reply.text or ctx.reply.caption or ""
        try:
            n = await app.twin.add_example(ctx.user_id, text)
        except ValueError:
            raise UsageError(ctx.t("ai_cmds.primer_2_500_simvolov")) from None
        await ctx.answer(ctx.t("ai_cmds.primer_stilya_sohranyon_udalit_vse", n=n, p=ctx.prefix), private=True)
        return
    if sub in ("forget", "забудь", "unut"):
        await app.twin.clear_examples(ctx.user_id)
        await ctx.answer(ctx.t("ai_cmds.primery_stilya_udaleny"), private=True)
        return
    from ..handlers.twin import screen_twin
    text, markup = await screen_twin(app, ctx.user_id, ctx.settings)
    if ctx.source == "sandbox":
        await ctx.answer(text)
        return
    await app.sender.send_text(ctx.user_id, text, markup=markup)
    await ctx.cleanup_command(fallback_text="🤖")
