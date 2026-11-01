"""v3 utility commands: .info (user), .geo (coordinates & maps), .ptext (OCR), QR decoding helper.

* ``.info`` shows only what Telegram really exposes to bots (name, username, ID, premium flag, bio/photo when the bot
  can read them). Account registration dates are not available through the Bot API and are never guessed.
* ``.geo`` works with coordinates the user provides or a shared location — it never tries to find someone's position.
* ``.ptext`` uses the offline ``tesseract`` engine (Termux: ``pkg install tesseract``) or, if absent, a configured AI
  provider with vision. Which engine produced the text is always stated.
"""
from __future__ import annotations

import asyncio
import io
import math
import re
import shutil
from pathlib import Path
from typing import Any

from aiogram.exceptions import TelegramAPIError

from ..ai.providers.base import ImageInput
from ..commands.context import CommandContext, CommandError, UsageError
from ..commands.registry import registry
from ..security.sanitize import clip, esc
from .media_util import download, require_media

OCR_LANGS = ("rus", "uzb", "uzb_cyrl", "eng")


# ---- .info ---------------------------------------------------------------------------------------------------------------
@registry.command("info", "system", aliases=["инфо", "whois", "kim"],
                  ru="Сведения о пользователе (ответом на сообщение или о собеседнике): имя, username, ID, bio и фото, если доступны боту",
                  uz="Foydalanuvchi haqida ma'lumot (xabarga javob yoki suhbatdosh): ism, username, ID, bio va rasm, agar botga ochiq bo'lsa",
                  syntax=".info (ответом на сообщение)", examples=[".info"], rate=(15, 60))
async def cmd_info(ctx: CommandContext) -> None:
    app = ctx.app
    user = None
    if ctx.reply is not None:
        user = ctx.reply.from_user
        origin = getattr(ctx.reply, "forward_origin", None)
        if origin is not None and getattr(origin, "sender_user", None):
            user = origin.sender_user
    elif ctx.is_business and ctx.message is not None:
        chat = ctx.message.chat
        user = type("U", (), {"id": chat.id, "first_name": chat.first_name, "last_name": chat.last_name, "username": chat.username,
                              "is_premium": None, "is_bot": False, "language_code": None})()
    elif ctx.message is not None:
        user = ctx.message.from_user
    if user is None:
        raise UsageError()
    name = " ".join(x for x in (getattr(user, "first_name", None), getattr(user, "last_name", None)) if x) or "—"
    lines = [ctx.t("👤 <b>{n}</b>", "👤 <b>{n}</b>", n=esc(name)),
             f"🆔 <code>{user.id}</code>"]
    if getattr(user, "username", None):
        lines.append(f"🔗 @{esc(user.username)}")
    if getattr(user, "is_bot", False):
        lines.append(ctx.t("🤖 Это бот", "🤖 Bu bot"))
    if getattr(user, "is_premium", None):
        lines.append("⭐️ Telegram Premium")
    if getattr(user, "language_code", None):
        lines.append(ctx.t("🌐 Язык клиента: {l}", "🌐 Mijoz tili: {l}", l=esc(user.language_code)))
    photo_id = None
    if ctx.source != "sandbox":
        try:
            full = await app.bot.get_chat(user.id)
            if getattr(full, "bio", None):
                lines.append(ctx.t("📝 Bio: {b}", "📝 Bio: {b}", b=esc(clip(full.bio, 300))))
            if getattr(full, "photo", None):
                photo_id = full.photo.big_file_id
        except (TelegramAPIError, ValueError):
            lines.append(ctx.t("ℹ️ Bio и фото недоступны боту (настройки приватности Telegram).",
                               "ℹ️ Bio va rasm botga ochiq emas (Telegram maxfiylik sozlamalari)."))
    lines.append(ctx.t("ℹ️ Дата регистрации аккаунта через Bot API недоступна.", "ℹ️ Akkaunt ro'yxatdan o'tgan sana Bot API orqali mavjud emas."))
    text = "\n".join(lines)
    if photo_id and ctx.source != "sandbox":
        res = await app.sender.send_media(ctx.user_id, "photo", photo_id, caption=text)
        if res.ok:
            await ctx.cleanup_command(fallback_text="👤")
            return
    await ctx.answer(text, private=ctx.is_business)


# ---- .geo ----------------------------------------------------------------------------------------------------------------
_COORD = re.compile(r"(-?\d{1,2}(?:[.,]\d+)?)\s*[,; ]\s*(-?\d{1,3}(?:[.,]\d+)?)")


def parse_coords(text: str) -> list[tuple[float, float]]:
    out = []
    for m in _COORD.finditer(text):
        lat, lon = float(m.group(1).replace(",", ".")), float(m.group(2).replace(",", "."))
        if -90 <= lat <= 90 and -180 <= lon <= 180:
            out.append((lat, lon))
    return out


def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    r = 6371.0088
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dp, dl = p2 - p1, math.radians(b[1] - a[1])
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def map_links(lat: float, lon: float) -> str:
    return (f'<a href="https://www.openstreetmap.org/?mlat={lat}&mlon={lon}#map=16/{lat}/{lon}">OSM</a> · '
            f'<a href="https://maps.google.com/?q={lat},{lon}">Google</a> · '
            f'<a href="https://yandex.ru/maps/?pt={lon},{lat}&z=16&l=map">Yandex</a>')


@registry.command("geo", "text", aliases=["гео", "карта", "xarita"],
                  ru="Координаты и карты: точка → геометка и ссылки; две точки → расстояние; ответом на геопозицию → ссылки",
                  uz="Koordinatalar va xaritalar: nuqta → geobelgi va havolalar; ikki nuqta → masofa; geojoylashuvga javob → havolalar",
                  syntax=".geo широта, долгота [; широта2, долгота2]", examples=[".geo 41.3111, 69.2797", ".geo 41.31 69.24; 39.65 66.96"],
                  sandbox_safe=True, rate=(15, 60))
async def cmd_geo(ctx: CommandContext) -> None:
    points = parse_coords(ctx.raw)
    if not points and ctx.reply is not None and ctx.reply.location is not None:
        points = [(ctx.reply.location.latitude, ctx.reply.location.longitude)]
    if not points:
        raise UsageError(ctx.t("Укажите координаты, например 41.3111, 69.2797, или ответьте на геопозицию.",
                               "Koordinatalarni kiriting, masalan 41.3111, 69.2797, yoki geojoylashuvga javob bering."))
    lat, lon = points[0]
    lines = [f"📍 <code>{lat:.6f}, {lon:.6f}</code>", map_links(lat, lon)]
    if len(points) > 1:
        km = haversine_km(points[0], points[1])
        lines.append(ctx.t("📏 Расстояние по прямой: {d}", "📏 To'g'ri chiziq bo'yicha masofa: {d}",
                           d=f"{km:.2f} km" if km >= 1 else f"{km * 1000:.0f} m"))
        lines.append(map_links(*points[1]))
    if ctx.source != "sandbox" and len(points) == 1 and ctx.parsed.first not in ("links", "ссылки"):
        await ctx.app.sender.send_location(ctx.chat_id if ctx.is_business else ctx.user_id, lat, lon, bc_id=ctx.bc_id)
    await ctx.answer("\n".join(lines))


# ---- OCR -----------------------------------------------------------------------------------------------------------------
async def _run(cmd: list[str], timeout: int = 60) -> str:
    proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout)
    except asyncio.TimeoutError:
        proc.kill()
        raise CommandError("OCR timeout") from None
    if proc.returncode != 0:
        raise RuntimeError(err.decode(errors="ignore")[:200])
    return out.decode(errors="ignore")


async def tesseract_ocr(path: Path) -> tuple[str, str] | None:
    exe = shutil.which("tesseract")
    if exe is None:
        return None
    listing = await _run([exe, "--list-langs"], 20)
    have = {ln.strip() for ln in listing.splitlines()[1:]}
    langs = [x for x in OCR_LANGS if x in have] or ["eng"]
    text = await _run([exe, str(path), "stdout", "-l", "+".join(langs), "--psm", "3"], 90)
    return text.strip(), "tesseract (" + "+".join(langs) + ")"


@registry.command("ptext", "media", aliases=["ocr", "текстсфото", "matnrasm"],
                  ru="Распознать текст на фото (русский, узбекский, английский): офлайн tesseract или AI-зрение",
                  uz="Rasmdagi matnni aniqlash (rus, o'zbek, ingliz): oflayn tesseract yoki AI ko'rish",
                  syntax=".ptext (ответом на фото)", examples=[".ptext"], rate=(8, 60))
async def cmd_ptext(ctx: CommandContext) -> None:
    app = ctx.app
    ref = require_media(ctx, image=True)
    d = app.media.files.job_dir("ocr")
    try:
        src = await download(app, ref, d / "input.jpg")
        result = await tesseract_ocr(src)
        if result is None and app.ai.available("vision"):
            res = await app.ai.ask(ctx.user_id, "Extract all text from the image verbatim, keeping line breaks. "
                                                "Languages may be Russian, Uzbek (Latin or Cyrillic) or English. Output only the text.",
                                   ctx.settings, images=[ImageInput(src.read_bytes(), "image/jpeg")], kind="ocr")
            result = (res.text.strip(), "AI vision")
        if result is None:
            raise CommandError(ctx.t("🔤 OCR недоступен: установите tesseract (Termux: <code>pkg install tesseract</code>) "
                                     "или добавьте AI-ключ с поддержкой изображений.",
                                     "🔤 OCR mavjud emas: tesseract o'rnating (Termux: <code>pkg install tesseract</code>) "
                                     "yoki rasmlarni qo'llab-quvvatlovchi AI kalitini qo'shing."))
        text, engine = result
        if not text:
            await ctx.answer(ctx.t("🔤 Текст не найден ({e}).", "🔤 Matn topilmadi ({e}).", e=engine))
            return
        body = f"🔤 <i>{esc(engine)}</i>\n<pre>{esc(clip(text, 3500))}</pre>"
        await ctx.answer(body, private=len(text) > 3500)
    finally:
        app.media.files.discard(d)


def decode_qr_bytes(data: bytes) -> list[str]:
    """Offline QR decoding with zxing-cpp (pip install zxing-cpp) — returns decoded texts."""
    try:
        import zxingcpp
        from PIL import Image
    except ImportError:
        return []
    im = Image.open(io.BytesIO(data)).convert("RGB")
    return [r.text for r in zxingcpp.read_barcodes(im) if r.text]


async def decode_qr(app: Any, ctx: CommandContext, ref: Any) -> tuple[list[str], str]:
    buf = io.BytesIO()
    await app.bot.download(ref.file_id, destination=buf)
    data = buf.getvalue()
    found = decode_qr_bytes(data)
    if found:
        return found, "zxing-cpp"
    exe = shutil.which("zbarimg")
    if exe:
        d = app.media.files.job_dir("qr")
        try:
            p = d / "qr.jpg"
            p.write_bytes(data)
            out = await _run([exe, "--quiet", "--raw", str(p)], 30)
            found = [ln for ln in out.splitlines() if ln.strip()]
            if found:
                return found, "zbarimg"
        except RuntimeError:
            pass
        finally:
            app.media.files.discard(d)
    if app.ai.available("vision"):
        res = await app.ai.ask(ctx.user_id, "If the image contains a QR code, output only its exact decoded content. If not, output NONE.",
                               ctx.settings, images=[ImageInput(data, "image/jpeg")], kind="qr")
        if res.text.strip() and res.text.strip().upper() != "NONE":
            return [res.text.strip()], "AI vision"
    return [], ""
