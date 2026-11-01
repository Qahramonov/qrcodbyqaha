"""Text tools: calculator, fix, encoders, generators, formatting, QR, dates."""
from __future__ import annotations

import base64
import binascii
import datetime as dt
import hashlib
import io
import json
import random
import re
import secrets
import string
import time
import unicodedata
import urllib.parse
import uuid
from typing import Any

import httpx
from aiogram import F, Router
from aiogram.types import BufferedInputFile, CallbackQuery

from ..commands.context import CommandContext, CommandError, UsageError
from ..commands.parser import split_pipe
from ..commands.registry import registry
from ..core.timeutil import local_dt, tz
from ..keyboards import kb
from ..security.sanitize import clip, esc
from ..utils.calc import CalcError, evaluate, fmt_number
from ..utils.textfix import apply_choice, fix_text

router = Router(name="text_tools")
TXT = dict(sandbox_safe=True, rate=(30, 60))
_rng = random.SystemRandom()


def _need(ctx: CommandContext, max_len: int = 4000) -> str:
    t = ctx.raw or ctx.reply_text()
    if not t:
        raise UsageError()
    if len(t) > max_len:
        raise CommandError(ctx.t("Слишком длинный текст (макс. {n}).", "Matn juda uzun (maks. {n}).", n=max_len))
    return t


@registry.command("calc", "text", aliases=["калк", "счёт", "посчитай", "hisob"], ru="Калькулятор (безопасный парсер): + − × ÷ ^ % ! sqrt sin log pi…",
                  uz="Kalkulyator (xavfsiz tahlilchi): + − × ÷ ^ % ! sqrt sin log pi…", syntax=".calc выражение",
                  examples=[".calc 2+2*2", ".calc sqrt(16) + 15% of 200", ".calc 1000 - 15%"], **TXT)
async def cmd_calc(ctx: CommandContext) -> None:
    expr = _need(ctx, 300)
    try:
        v = evaluate(expr)
    except CalcError as e:
        raise CommandError(ctx.t("🧮 Ошибка: {e}", "🧮 Xato: {e}", e=esc(str(e)))) from None
    await ctx.answer(f"🧮 <code>{esc(expr)}</code> = <b>{fmt_number(v)}</b>")


_FIX: dict[str, dict[str, Any]] = {}


@registry.command("fix", "text", aliases=["исправь", "fixit", "tuzat"],
                  ru="Исправить опечатки, раскладку (ghbdtn → привет), Caps Lock, растянутые буквы. Неоднозначное — только с подтверждения",
                  uz="Xatolar, klaviatura (ghbdtn → привет), Caps Lock'ni tuzatish. Noaniq bo'lsa — faqat tasdiq bilan",
                  syntax=".fix текст | .fix (ответом) | .fix ai текст", examples=[".fix ghbdtn rfr ltkf", ".fix привт как дила", ".fix ai i has went"], **TXT)
async def cmd_fix(ctx: CommandContext) -> None:
    use_ai = ctx.parsed.first == "ai"
    text = (ctx.raw.split(None, 1)[1] if use_ai and len(ctx.raw.split(None, 1)) > 1 else ("" if use_ai else ctx.raw)) or ctx.reply_text()
    if not text:
        raise UsageError()
    if use_ai:
        from .ai_cmds import _run
        out = await _run(ctx, "fix", text)
        await ctx.answer(esc(out))
        return
    res = fix_text(text[:2000])
    if res.ambiguous:
        best = res.text
        for word, cands in res.ambiguous:
            best = apply_choice(best, word, cands[0])
        lines = [ctx.t("✏️ <b>Есть неоднозначные исправления</b> — текст не изменён без вашего подтверждения.",
                       "✏️ <b>Noaniq tuzatishlar bor</b> — matn tasdiqsiz o'zgartirilmadi.")]
        lines += [f"• <b>{esc(w)}</b> → {', '.join(esc(c) for c in cands)}" for w, cands in res.ambiguous[:6]]
        lines += ["", ctx.t("Вариант:", "Variant:") + f" <i>{esc(best)}</i>"]
        markup = None
        if ctx.source != "sandbox":
            token = secrets.token_hex(4)
            _FIX[token] = {"ctx": ctx, "text": best, "ts": time.time()}
            for k in [k for k, v in _FIX.items() if time.time() - v["ts"] > 1800]:
                _FIX.pop(k, None)
            markup = kb([[(ctx.t("✅ Применить вариант", "✅ Variantni qo'llash"), f"fx:{token}:ok"),
                          (ctx.t("✏️ Только точные", "✏️ Faqat aniqlari"), f"fx:{token}:safe")]])
            _FIX[token]["safe"] = res.text
        if ctx.is_business:
            await ctx.answer("\n".join(lines), markup=markup, private=True, in_place=False)
        else:
            await ctx.answer("\n".join(lines), markup=markup)
        return
    if not res.changed:
        if ctx.is_business:
            await ctx.answer(esc(text))
        else:
            await ctx.answer(ctx.t("✅ Ошибок не найдено.", "✅ Xatolar topilmadi."))
        return
    if ctx.is_business:
        await ctx.answer(esc(res.text))  # replaces the command with the corrected message
    else:
        await ctx.answer("✏️ " + esc(res.text))


@router.callback_query(F.data.startswith("fx:"))
async def cb_fix(cb: CallbackQuery, app: Any) -> None:
    _, token, mode = cb.data.split(":")
    item = _FIX.pop(token, None)
    if not item or item["ctx"].user_id != cb.from_user.id:
        await cb.answer("—")
        return
    ctx: CommandContext = item["ctx"]
    text = item["text"] if mode == "ok" else item["safe"]
    if ctx.is_business and ctx.message is not None:
        res = await app.sender.edit_text(ctx.chat_id, ctx.message.message_id, esc(text), bc_id=ctx.bc_id)
        await cb.answer("✅" if res.ok else "⚠️")
    else:
        await cb.message.answer(esc(text))
        await cb.answer("✅")
    try:
        await cb.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass


LEET = str.maketrans({"a": "4", "e": "3", "i": "1", "o": "0", "s": "5", "t": "7", "g": "9", "b": "8", "l": "1", "z": "2",
                      "а": "4", "е": "3", "о": "0", "з": "3", "ч": "4", "б": "6", "т": "7", "в": "8"})


@registry.command("leet", "text", aliases=["лит", "1337"], ru="Текст в стиле l33t", uz="Matnni l33t uslubida", syntax=".leet текст", examples=[".leet hacker"], **TXT)
async def cmd_leet(ctx: CommandContext) -> None:
    await ctx.answer(esc(_need(ctx).lower().translate(LEET)))


def _bubble(text: str) -> str:
    out = []
    for c in text:
        if "a" <= c <= "z":
            out.append(chr(0x24D0 + ord(c) - 97))
        elif "A" <= c <= "Z":
            out.append(chr(0x24B6 + ord(c) - 65))
        elif "1" <= c <= "9":
            out.append(chr(0x2460 + ord(c) - 49))
        elif c == "0":
            out.append("⓪")
        else:
            out.append(c)
    return "".join(out)


@registry.command("bubble", "text", aliases=["пузыри", "kopik"], ru="Текст в кружочках ⓑⓤⓑⓑⓛⓔ", uz="Doiradagi matn ⓑⓤⓑⓑⓛⓔ", syntax=".bubble текст",
                  examples=[".bubble hello"], **TXT)
async def cmd_bubble(ctx: CommandContext) -> None:
    await ctx.answer(esc(_bubble(_need(ctx, 1000))))


ZALGO_UP = [chr(c) for c in range(0x0300, 0x0315)] + [chr(c) for c in (0x033D, 0x0344, 0x0346, 0x034A, 0x034B, 0x034C)]
ZALGO_DOWN = [chr(c) for c in range(0x0316, 0x0334)]


@registry.command("zalgo", "text", aliases=["залго"], ru="Z̷a̶l̸g̵o̴-текст (сила 1–10)", uz="Z̷a̶l̸g̵o̴ matn (kuch 1–10)", syntax=".zalgo [сила] текст",
                  examples=[".zalgo 5 привет"], **TXT)
async def cmd_zalgo(ctx: CommandContext) -> None:
    raw = _need(ctx, 500)
    power = 4
    m = re.match(r"(\d{1,2})\s+(.+)", raw, re.S)
    if m and 1 <= int(m.group(1)) <= 10:
        power, raw = int(m.group(1)), m.group(2)
    out = "".join(c + ("".join(_rng.choice(ZALGO_UP + ZALGO_DOWN) for _ in range(_rng.randint(1, power))) if c.strip() else "") for c in raw)
    await ctx.answer(esc(out[:4000]))


@registry.command("reverse_text", "text", aliases=["перевернуть", "rtext", "teskari_matn"], ru="Перевернуть текст задом наперёд", uz="Matnni teskari qilish",
                  syntax=".reverse_text текст", examples=[".reverse_text привет"], **TXT)
async def cmd_reverse_text(ctx: CommandContext) -> None:
    await ctx.answer(esc(_need(ctx)[::-1]))


@registry.command("upper", "text", aliases=["верх", "katta"], ru="ВЕРХНИЙ РЕГИСТР", uz="KATTA HARFLAR", syntax=".upper текст", examples=[".upper привет"], **TXT)
async def cmd_upper(ctx: CommandContext) -> None:
    await ctx.answer(esc(_need(ctx).upper()))


@registry.command("lower", "text", aliases=["низ", "kichik"], ru="нижний регистр", uz="kichik harflar", syntax=".lower текст", examples=[".lower ПРИВЕТ"], **TXT)
async def cmd_lower(ctx: CommandContext) -> None:
    await ctx.answer(esc(_need(ctx).lower()))


@registry.command("title", "text", aliases=["заглавные", "sarlavha"], ru="Каждое Слово С Большой Буквы", uz="Har So'z Katta Harf Bilan", syntax=".title текст",
                  examples=[".title привет мир"], **TXT)
async def cmd_title(ctx: CommandContext) -> None:
    await ctx.answer(esc(_need(ctx).title()))


@registry.command("repeat", "text", aliases=["повтори", "takror"], ru="Повторить текст N раз (до 20)", uz="Matnni N marta takrorlash (20 gacha)",
                  syntax=".repeat N текст", examples=[".repeat 3 ура!"], **TXT)
async def cmd_repeat(ctx: CommandContext) -> None:
    m = re.match(r"(\d{1,2})\s+(.+)", ctx.raw, re.S)
    if not m or not 1 <= int(m.group(1)) <= 20:
        raise UsageError()
    out = (m.group(2) + " ") * int(m.group(1))
    await ctx.answer(esc(out.strip()[:4000]))


@registry.command("count", "text", aliases=["счётчик", "sanash"], ru="Статистика текста: символы, слова, строки, время чтения", uz="Matn statistikasi",
                  syntax=".count текст | (ответом)", examples=[".count"], **TXT)
async def cmd_count(ctx: CommandContext) -> None:
    t = _need(ctx, 100000)
    words = re.findall(r"\w+", t)
    sentences = [s for s in re.split(r"[.!?]+", t) if s.strip()]
    await ctx.answer(ctx.t("📊 Символов: {c} (без пробелов {n})\nСлов: {w} · строк: {l} · предложений: {s}\n⏱ Чтение: ~{r} с",
                           "📊 Belgilar: {c} (bo'shliqsiz {n})\nSo'zlar: {w} · qatorlar: {l} · gaplar: {s}\n⏱ O'qish: ~{r} s",
                           c=len(t), n=len(re.sub(r"\s", "", t)), w=len(words), l=t.count("\n") + 1, s=len(sentences),
                           r=max(1, round(len(words) / 3.3))), private=ctx.is_business)


@registry.command("base64", "text", aliases=["b64"], ru="Кодировать в Base64", uz="Base64 ga kodlash", syntax=".base64 текст", examples=[".base64 hello"], **TXT)
async def cmd_base64(ctx: CommandContext) -> None:
    await ctx.answer(f"<code>{esc(base64.b64encode(_need(ctx).encode()).decode())}</code>")


@registry.command("unbase64", "text", aliases=["ub64", "debase64"], ru="Декодировать Base64", uz="Base64 ni dekodlash", syntax=".unbase64 строка",
                  examples=[".unbase64 aGVsbG8="], **TXT)
async def cmd_unbase64(ctx: CommandContext) -> None:
    raw = _need(ctx).strip()
    try:
        data = base64.b64decode(raw + "=" * (-len(raw) % 4), validate=False)
        text = data.decode("utf-8")
    except (binascii.Error, UnicodeDecodeError, ValueError):
        raise CommandError(ctx.t("Это не корректный Base64 с текстом UTF-8.", "Bu to'g'ri Base64 (UTF-8) emas.")) from None
    await ctx.answer(esc(text))


@registry.command("binary", "text", aliases=["бин", "bin"], ru="Текст ↔ двоичный код (автоопределение)", uz="Matn ↔ ikkilik kod (avto)",
                  syntax=".binary текст | 01101000…", examples=[".binary hi", ".binary 01101000 01101001"], **TXT)
async def cmd_binary(ctx: CommandContext) -> None:
    t = _need(ctx, 2000)
    if re.fullmatch(r"[01\s]+", t) and len(t.replace(" ", "")) % 8 == 0:
        bits = t.replace(" ", "").replace("\n", "")
        try:
            out = bytes(int(bits[i:i + 8], 2) for i in range(0, len(bits), 8)).decode("utf-8")
        except UnicodeDecodeError:
            raise CommandError("invalid UTF-8") from None
        await ctx.answer(esc(out))
    else:
        await ctx.answer("<code>" + " ".join(f"{b:08b}" for b in t.encode())[:4000] + "</code>")


@registry.command("hex", "text", aliases=["хекс"], ru="Текст ↔ HEX (автоопределение)", uz="Matn ↔ HEX (avto)", syntax=".hex текст | 68656c6c6f",
                  examples=[".hex hello"], **TXT)
async def cmd_hex(ctx: CommandContext) -> None:
    t = _need(ctx, 3000).strip()
    compact = t.replace(" ", "")
    if re.fullmatch(r"(0x)?[0-9a-fA-F]+", compact) and len(compact.removeprefix("0x")) % 2 == 0 and len(compact) >= 4:
        try:
            await ctx.answer(esc(bytes.fromhex(compact.removeprefix("0x")).decode("utf-8")))
            return
        except (ValueError, UnicodeDecodeError):
            pass
    await ctx.answer(f"<code>{t.encode().hex()}</code>")


@registry.command("uuid", "text", aliases=["гуид", "guid"], ru="Случайный UUID v4", uz="Tasodifiy UUID v4", syntax=".uuid", examples=[".uuid"], **TXT)
async def cmd_uuid(ctx: CommandContext) -> None:
    await ctx.answer(f"<code>{uuid.uuid4()}</code>")


@registry.command("password", "text", aliases=["пароль", "parol", "pass"], ru="Надёжный пароль (8–64, по умолчанию 16) — придёт вам в личку",
                  uz="Kuchli parol (8–64, standart 16) — shaxsiy chatga keladi", syntax=".password [длина] [nosym]", examples=[".password", ".password 24"], **TXT)
async def cmd_password(ctx: CommandContext) -> None:
    n = 16
    if ctx.args and ctx.args[0].isdigit():
        n = int(ctx.args[0])
    if not 8 <= n <= 64:
        raise UsageError()
    alphabet = string.ascii_letters + string.digits + ("" if "nosym" in ctx.args else "!@#$%^&*-_=+?")
    while True:
        pw = "".join(secrets.choice(alphabet) for _ in range(n))
        if any(c.islower() for c in pw) and any(c.isupper() for c in pw) and any(c.isdigit() for c in pw):
            break
    await ctx.answer(f"🔑 <tg-spoiler><code>{esc(pw)}</code></tg-spoiler>", private=True)


@registry.command("qr", "text", aliases=["кьюар", "qrcode"], ru="QR-код из текста или ссылки", uz="Matn yoki havoladan QR-kod", syntax=".qr текст",
                  examples=[".qr https://t.me/libPM"], rate=(10, 60))
async def cmd_qr(ctx: CommandContext) -> None:
    import segno
    text = _need(ctx, 1500)
    qr = segno.make(text, error="m")
    buf = io.BytesIO()
    qr.save(buf, kind="png", scale=10, border=3, dark="#111827", light="#ffffff")
    if ctx.source == "sandbox":
        ctx.outputs.append({"type": "photo", "caption": f"QR ({qr.version})"})
        return
    res = await ctx.send_media("photo", BufferedInputFile(buf.getvalue(), "qr.png"), caption="🔳 " + esc(clip(text, 200)))
    if res.ok:
        await ctx.cleanup_command(fallback_text="🔳 QR")


@registry.command("short", "text", aliases=["сократить", "qisqa"], ru="Сократить ссылку (через is.gd / tinyurl — внешний сервис)",
                  uz="Havolani qisqartirish (is.gd / tinyurl orqali)", syntax=".short ссылка", examples=[".short https://example.com/very/long/link"],
                  deps=["network"], rate=(10, 60))
async def cmd_short(ctx: CommandContext) -> None:
    url = _need(ctx, 2000).strip()
    if not re.fullmatch(r"https?://[^\s]{4,}", url):
        raise UsageError(ctx.t("Нужна ссылка http(s)://", "http(s):// havola kerak"))
    async with httpx.AsyncClient(timeout=10) as client:
        for api in (f"https://is.gd/create.php?format=simple&url={urllib.parse.quote(url, safe='')}",
                    f"https://tinyurl.com/api-create.php?url={urllib.parse.quote(url, safe='')}"):
            try:
                r = await client.get(api)
                if r.status_code == 200 and r.text.startswith("http"):
                    await ctx.answer(f"🔗 {esc(r.text.strip())}")
                    return
            except httpx.HTTPError:
                continue
    raise CommandError(ctx.t("Сервисы сокращения ссылок недоступны.", "Havola qisqartirish xizmatlari mavjud emas."))


FORMATS = {"b": "b", "bold": "b", "ж": "b", "i": "i", "italic": "i", "к": "i", "u": "u", "underline": "u", "s": "s", "strike": "s",
           "code": "code", "mono": "code", "spoiler": "tg-spoiler", "спойлер": "tg-spoiler", "quote": "blockquote", "цитата": "blockquote"}


@registry.command("format", "text", aliases=["формат", "fmt"], ru="Форматирование: b, i, u, s, code, spoiler, quote", uz="Formatlash: b, i, u, s, code, spoiler, quote",
                  syntax=".format стиль текст", examples=[".format b Важно!", ".format spoiler сюрприз"], **TXT)
async def cmd_format(ctx: CommandContext) -> None:
    parts = ctx.raw.split(None, 1)
    if len(parts) < 2 or parts[0].lower() not in FORMATS:
        raise UsageError()
    tag = FORMATS[parts[0].lower()]
    await ctx.answer(f"<{tag}>{esc(parts[1])}</{tag}>")


EMOJI_MAP = {"любовь": "❤️", "люблю": "❤️", "sevgi": "❤️", "love": "❤️", "огонь": "🔥", "fire": "🔥", "olov": "🔥", "кофе": "☕️", "coffee": "☕️",
             "qahva": "☕️", "чай": "🍵", "choy": "🍵", "солнце": "☀️", "quyosh": "☀️", "sun": "☀️", "дождь": "🌧", "yomg'ir": "🌧", "ночь": "🌙",
             "tun": "🌙", "деньги": "💰", "pul": "💰", "money": "💰", "машина": "🚗", "mashina": "🚗", "car": "🚗", "дом": "🏠", "uy": "🏠",
             "home": "🏠", "кот": "🐱", "mushuk": "🐱", "cat": "🐱", "собака": "🐶", "it": "🐶", "dog": "🐶", "работа": "💼", "ish": "💼",
             "work": "💼", "сон": "😴", "uyqu": "😴", "sleep": "😴", "праздник": "🎉", "bayram": "🎉", "party": "🎉", "музыка": "🎵", "musiqa": "🎵",
             "music": "🎵", "еда": "🍽", "ovqat": "🍽", "food": "🍽", "пицца": "🍕", "pizza": "🍕", "спорт": "⚽️", "sport": "⚽️", "книга": "📚",
             "kitob": "📚", "book": "📚", "телефон": "📱", "telefon": "📱", "phone": "📱", "время": "⏰", "vaqt": "⏰", "time": "⏰", "спасибо": "🙏",
             "rahmat": "🙏", "thanks": "🙏", "привет": "👋", "salom": "👋", "hello": "👋", "ok": "👌", "да": "✅", "ha": "✅", "yes": "✅",
             "нет": "❌", "yo'q": "❌", "no": "❌", "идея": "💡", "g'oya": "💡", "idea": "💡", "звезда": "⭐️", "yulduz": "⭐️", "star": "⭐️",
             "сердце": "💖", "yurak": "💖", "heart": "💖", "смех": "😂", "kulgi": "😂", "lol": "😂", "грусть": "😢", "qayg'u": "😢", "sad": "😢"}
RANDOM_EMOJI = list("😀😎🤩🥳😇🤖👻🦄🐼🦊🐙🌈🔥⭐️🍀🍕🎈🎯🚀💎🎧🌸🍉🧠⚡️")


@registry.command("emoji", "text", aliases=["эмодзи", "emodzi"], ru="Добавить эмодзи к словам (или случайный эмодзи)", uz="So'zlarga emoji qo'shish (yoki tasodifiy)",
                  syntax=".emoji [текст]", examples=[".emoji люблю кофе и музыку", ".emoji"], **TXT)
async def cmd_emoji(ctx: CommandContext) -> None:
    t = ctx.raw or ctx.reply_text()
    if not t:
        await ctx.answer(_rng.choice(RANDOM_EMOJI))
        return
    out = []
    for w in t.split():
        key = re.sub(r"[^\w']", "", w.lower())
        out.append(f"{w} {EMOJI_MAP[key]}" if key in EMOJI_MAP else w)
    await ctx.answer(esc(" ".join(out)) + " " + _rng.choice(RANDOM_EMOJI))


@registry.command("random", "text", aliases=["случайно", "rand"], ru="Случайное: число, цвет, буква, да/нет", uz="Tasodifiy: son, rang, harf, ha/yo'q",
                  syntax=".random [num min max|color|letter|yesno]", examples=[".random", ".random color", ".random num 1 6"], **TXT)
async def cmd_random(ctx: CommandContext) -> None:
    kind = ctx.parsed.first or "num"
    if kind in ("color", "цвет", "rang"):
        c = "#%06X" % _rng.randint(0, 0xFFFFFF)
        await ctx.answer(f"🎨 <code>{c}</code>")
    elif kind in ("letter", "буква", "harf"):
        await ctx.answer("🔤 " + _rng.choice("АБВГДЕЖЗИКЛМНОПРСТУФХЦЧШЭЮЯ" if ctx.lang == "ru" else "ABDEFGHIJKLMNOPQRSTUVXYZ"))
    elif kind in ("yesno", "данет", "hayoq"):
        await ctx.answer(_rng.choice([ctx.t("✅ Да", "✅ Ha"), ctx.t("❌ Нет", "❌ Yo'q")]))
    else:
        nums = [a for a in ctx.args if a.lstrip("-").isdigit()]
        lo, hi = (int(nums[0]), int(nums[1])) if len(nums) >= 2 else (1, int(nums[0]) if nums else 100)
        if lo > hi:
            raise UsageError()
        await ctx.answer(f"🎲 <b>{_rng.randint(lo, hi)}</b>")


TZ_ALIASES = {"msk": "Europe/Moscow", "moscow": "Europe/Moscow", "москва": "Europe/Moscow", "tashkent": "Asia/Tashkent", "ташкент": "Asia/Tashkent",
              "toshkent": "Asia/Tashkent", "utc": "UTC", "london": "Europe/London", "ny": "America/New_York", "dubai": "Asia/Dubai",
              "istanbul": "Europe/Istanbul", "almaty": "Asia/Almaty", "tokyo": "Asia/Tokyo", "berlin": "Europe/Berlin", "seoul": "Asia/Seoul"}
WEEKDAYS = {"ru": ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"],
            "uz": ["dushanba", "seshanba", "chorshanba", "payshanba", "juma", "shanba", "yakshanba"]}


def _tz_arg(ctx: CommandContext) -> str:
    if ctx.args:
        a = ctx.args[0]
        name = TZ_ALIASES.get(a.lower(), a)
        z = tz(name)
        if z is dt.timezone.utc and name.upper() != "UTC":
            raise UsageError(ctx.t("Неизвестный часовой пояс.", "Noma'lum vaqt mintaqasi."))
        return name
    return ctx.settings.get("timezone") or ctx.app.config.timezone


@registry.command("date", "text", aliases=["дата", "sana"], ru="Сегодняшняя дата и день недели", uz="Bugungi sana va hafta kuni", syntax=".date [часовой пояс]",
                  examples=[".date", ".date msk"], **TXT)
async def cmd_date(ctx: CommandContext) -> None:
    d = local_dt(None, _tz_arg(ctx))
    await ctx.answer(f"📅 {d.strftime('%d.%m.%Y')} · {WEEKDAYS[ctx.lang][d.weekday()]} · {ctx.t('неделя', 'hafta')} {d.isocalendar()[1]}")


@registry.command("time", "text", aliases=["время", "vaqt"], ru="Текущее время (можно указать город/пояс)", uz="Joriy vaqt (shahar/mintaqa ko'rsatish mumkin)",
                  syntax=".time [пояс]", examples=[".time", ".time tokyo", ".time Europe/Paris"], **TXT)
async def cmd_time(ctx: CommandContext) -> None:
    name = _tz_arg(ctx)
    d = local_dt(None, name)
    await ctx.answer(f"🕒 <b>{d.strftime('%H:%M:%S')}</b> · {esc(name)} (UTC{d.strftime('%z')[:3]}:{d.strftime('%z')[3:]})")


@registry.command("timestamp", "text", aliases=["unix", "ts"], ru="Unix-время: сейчас, из числа в дату или из даты в число", uz="Unix vaqt: hozir, son↔sana",
                  syntax=".timestamp [число | ГГГГ-ММ-ДД ЧЧ:ММ]", examples=[".timestamp", ".timestamp 1700000000", ".timestamp 2025-01-01 12:00"], **TXT)
async def cmd_timestamp(ctx: CommandContext) -> None:
    tz_name = ctx.settings.get("timezone") or ctx.app.config.timezone
    raw = ctx.raw.strip()
    if not raw:
        await ctx.answer(f"⏱ <code>{int(time.time())}</code>")
        return
    if re.fullmatch(r"\d{9,13}", raw):
        v = int(raw)
        if v > 10 ** 11:
            v //= 1000
        await ctx.answer(f"📅 {local_dt(v, tz_name).strftime('%d.%m.%Y %H:%M:%S')} ({esc(tz_name)})")
        return
    for f in ("%Y-%m-%d %H:%M", "%Y-%m-%d", "%d.%m.%Y %H:%M", "%d.%m.%Y"):
        try:
            d = dt.datetime.strptime(raw, f).replace(tzinfo=tz(tz_name))
            await ctx.answer(f"⏱ <code>{int(d.timestamp())}</code>")
            return
        except ValueError:
            continue
    raise UsageError()


@registry.command("json", "text", aliases=["джсон"], ru="Проверить и красиво оформить JSON (min — сжать)", uz="JSON'ni tekshirish va formatlash (min — siqish)",
                  syntax=".json [min] текст", examples=['.json {"a":1,"b":[1,2]}', ".json min (ответом)"], **TXT)
async def cmd_json(ctx: CommandContext) -> None:
    minify = ctx.parsed.first == "min"
    raw = (ctx.raw.split(None, 1)[1] if minify and len(ctx.raw.split(None, 1)) > 1 else ("" if minify else ctx.raw)) or ctx.reply_text()
    if not raw:
        raise UsageError()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise CommandError(ctx.t("❌ Невалидный JSON: {e}", "❌ Noto'g'ri JSON: {e}", e=esc(str(e)))) from None
    out = json.dumps(data, ensure_ascii=False, separators=(",", ":")) if minify else json.dumps(data, ensure_ascii=False, indent=2)
    await ctx.answer(f"<pre>{esc(out[:3800])}</pre>")


@registry.command("hash", "text", aliases=["хэш", "хеш"], ru="Хэш текста: sha256 (по умолчанию), md5, sha1, sha512, blake2b", uz="Matn xeshi",
                  syntax=".hash [алгоритм] текст", examples=[".hash hello", ".hash md5 hello"], **TXT)
async def cmd_hash(ctx: CommandContext) -> None:
    algos = ("sha256", "md5", "sha1", "sha512", "blake2b", "sha3_256")
    parts = ctx.raw.split(None, 1)
    algo = "sha256"
    text = ctx.raw
    if parts and parts[0].lower() in algos:
        algo = parts[0].lower()
        text = parts[1] if len(parts) > 1 else ""
    text = text or ctx.reply_text()
    if not text:
        raise UsageError()
    await ctx.answer(f"#️⃣ {algo}: <code>{hashlib.new(algo, text.encode()).hexdigest()}</code>")


@registry.command("urlencode", "text", aliases=["urlenc"], ru="URL-кодирование", uz="URL kodlash", syntax=".urlencode текст", examples=[".urlencode привет мир"], **TXT)
async def cmd_urlencode(ctx: CommandContext) -> None:
    await ctx.answer(f"<code>{esc(urllib.parse.quote(_need(ctx), safe=''))}</code>")


@registry.command("urldecode", "text", aliases=["urldec"], ru="URL-декодирование", uz="URL dekodlash", syntax=".urldecode строка",
                  examples=[".urldecode %D0%BF%D1%80%D0%B8%D0%B2%D0%B5%D1%82"], **TXT)
async def cmd_urldecode(ctx: CommandContext) -> None:
    await ctx.answer(esc(urllib.parse.unquote_plus(_need(ctx))))


@registry.command("normalize_text", "text", aliases=["clean_text"], ru="Нормализовать Unicode (убрать «невидимые» символы)", uz="Unicode'ni normallashtirish",
                  syntax=".normalize_text текст", examples=[".normalize_text ｔｅｘｔ"], **TXT)
async def cmd_normalize_text(ctx: CommandContext) -> None:
    t = unicodedata.normalize("NFKC", _need(ctx))
    t = re.sub(r"[​-‏⁠﻿]", "", t)
    await ctx.answer(esc(t))


__all__ = ["router", "split_pipe"]
