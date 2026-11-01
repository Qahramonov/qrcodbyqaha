"""Media Studio + Voice Studio commands (FFmpeg / Pillow) with the job queue."""
from __future__ import annotations

import re
import secrets
import time
from pathlib import Path
from typing import Any, Callable

from aiogram import F, Router
from aiogram.types import CallbackQuery, FSInputFile

from ..commands.context import CommandContext, CommandError, UsageError
from ..commands.registry import registry
from ..keyboards import grid, kb
from ..media import image as I
from ..media.av import SPEEDS
from ..media.ffmpeg import MediaError, volume_gain_db
from ..security.sanitize import esc
from .media_util import MediaRef, download, find_media, require_media

router = Router(name="media_cmds")
MEDIA = dict(deps=["ffmpeg"], rate=(8, 60))
IMG = dict(rate=(12, 60))
_PENDING: dict[str, dict[str, Any]] = {}
_MERGE: dict[tuple[int, int], list[MediaRef]] = {}

ERRORS = {
    "timeout": ("⏱ Обработка заняла слишком много времени и была остановлена.", "⏱ Ishlov berish juda uzoq davom etdi va to'xtatildi."),
    "too many active jobs": ("⏳ У вас уже 3 задачи в работе. Дождитесь завершения или .cancel", "⏳ Sizda 3 ta vazifa bajarilmoqda. Kuting yoki .cancel"),
    "media module is paused": ("⏸ Media Studio временно приостановлена администратором.", "⏸ Media Studio vaqtincha to'xtatilgan."),
    "no audio stream": ("🔇 В файле нет звука.", "🔇 Faylda ovoz yo'q."),
    "video required": ("🎞 Нужно видео.", "🎞 Video kerak."),
    "result too large": ("📦 Результат больше 50 МБ — лимит отправки Telegram.", "📦 Natija 50 MB dan katta — Telegram cheklovi."),
}


def _err_text(ctx: CommandContext, e: Exception) -> str:
    msg = str(e)
    for k, (ru, uz) in ERRORS.items():
        if msg.startswith(k):
            return ctx.t(ru, uz)
    if msg.startswith("video too long"):
        return ctx.t("🎞 Для реверса видео максимум {s} с.", "🎞 Video reversi uchun maksimum {s} s.", s=ctx.app.config.media_max_reverse_video)
    return ctx.t("⚠️ Не удалось обработать медиа: {e}", "⚠️ Mediani qayta ishlab bo'lmadi: {e}", e=esc(msg[:160]))


def _ext(ref: MediaRef) -> str:
    return {"voice": ".ogg", "video_note": ".mp4", "video": ".mp4", "animation": ".mp4", "photo": ".jpg", "sticker": ".webp",
            "audio": Path(ref.file_name or "a.mp3").suffix or ".mp3"}.get(ref.kind, Path(ref.file_name or "file.bin").suffix or ".bin")


async def run_media(ctx: CommandContext, op: str, *, need: str = "any", av_fn: Callable | None = None, img_fn: Callable | None = None,
                    img_format: str | None = None, label: str = "", ref: MediaRef | None = None,
                    img_out_fn: Callable | None = None) -> None:
    """img_out_fn(image, job_dir) -> (path, send_kind) for image ops that produce a non-photo result (GIF)."""
    app = ctx.app
    ref = ref or require_media(ctx, image=None if need == "any" else need == "image", av=None if need == "any" else need == "av")
    if img_out_fn is not None and img_fn is None:
        img_fn = img_out_fn
    if ref.is_image and img_fn is None:
        raise CommandError(ctx.t("Эта команда работает с аудио/видео.", "Bu buyruq audio/video bilan ishlaydi."))
    if not ref.is_image and av_fn is None:
        raise CommandError(ctx.t("Эта команда работает с изображениями.", "Bu buyruq rasmlar bilan ishlaydi."))
    if not ref.is_image and not app.health.ffmpeg_ok:
        raise CommandError(ctx.t("🎞 FFmpeg не установлен: pkg install ffmpeg", "🎞 FFmpeg o'rnatilmagan: pkg install ffmpeg"))
    if ctx.source != "sandbox":
        limit = await app.subs.limit(ctx.user_id, "media_jobs_day")
        ok, _ = await app.quotas.consume(f"media:{ctx.user_id}", limit)
        if not ok:
            raise CommandError(ctx.t("📉 Дневной лимит медиа-задач ({l}) исчерпан.", "📉 Kunlik media vazifalar limiti ({l}) tugadi.", l=limit))
    await ctx.status(ctx.t("⏳ Обработка…", "⏳ Ishlanmoqda…"))
    reply_to = ref.message.message_id if ref.message is not None else None

    async def runner(job) -> dict[str, Any]:
        d = app.media.files.job_dir(op)
        try:
            src = await download(app, ref, d / f"input{_ext(ref)}")
            extra: dict[str, Any] = {}
            if ref.is_image and img_out_fn is not None:
                im = await app.media.image_op(I.open_image, src)
                out, kind = await app.media.image_op(img_out_fn, im, d)
            elif ref.is_image:
                im = await app.media.image_op(I.open_image, src)
                out_im = await app.media.image_op(img_fn, im)
                if op == "sticker":
                    out = I.save_image(out_im, d, "sticker", "webp")
                    kind = "sticker"
                else:
                    out = I.save_image(out_im, d, "result", img_format)
                    kind = "photo" if out.suffix == ".jpg" and max(out_im.size) <= 4096 else "document"
            else:
                out, kind, extra = await av_fn(src, ref.kind, d, job_id=job.id, cancel=job.cancel)
            size = out.stat().st_size
            if size > 49 * 1048576:
                raise MediaError("result too large")
            res = await ctx.send_media(kind, FSInputFile(out), reply_to=reply_to, **extra)
            if not res.ok:
                raise MediaError(f"send failed: {res.kind}")
            await ctx.cleanup_command(fallback_text=f"✅ {label or op}")
            return {"size": size}
        except MediaError as e:
            if not str(e).startswith("cancelled"):
                await ctx.answer(_err_text(ctx, e), private=ctx.is_business)
            raise
        finally:
            app.media.files.discard(d)

    try:
        job = await app.media.queue.submit(ctx.user_id, ctx.chat_id, op, {"media": ref.kind}, runner, ref.file_size)
    except MediaError as e:
        raise CommandError(_err_text(ctx, e)) from None
    pos = app.media.queue.position(job)
    if pos > 1:
        await ctx.status(ctx.t("⏳ В очереди: {p}. Отмена: {pr}cancel {j}", "⏳ Navbatda: {p}. Bekor: {pr}cancel {j}", p=pos, pr=ctx.prefix, j=job.id))
    if ctx.source == "sandbox":
        await job.done.wait()


def _num(ctx: CommandContext, default: float, lo: float, hi: float) -> float:
    if not ctx.args:
        return default
    try:
        v = float(ctx.args[0].replace(",", ".").rstrip("x×%"))
    except ValueError:
        raise UsageError() from None
    if not lo <= v <= hi:
        raise UsageError(ctx.t("Значение должно быть от {a} до {b}.", "Qiymat {a} dan {b} gacha bo'lishi kerak.", a=lo, b=hi))
    return v


def _pending_kb(ctx: CommandContext, op: str, ref: MediaRef, options: list[tuple[str, str]], cols: int = 5) -> Any:
    token = secrets.token_hex(4)
    _PENDING[token] = {"ctx": ctx, "op": op, "ref": ref, "ts": time.time()}
    for k in [k for k, v in _PENDING.items() if time.time() - v["ts"] > 900]:
        _PENDING.pop(k, None)
    return kb(grid([(label, f"ms:{token}:{val}") for label, val in options], cols))


# ------------------------------------------------------------------------------------------------
# audio / video
# ------------------------------------------------------------------------------------------------

@registry.command("reverse", "media", aliases=["реверс", "задомнаперёд", "teskari"],
                  ru="Развернуть голосовое, аудио, видео или кружок задом наперёд (тип сохраняется)",
                  uz="Ovozli, audio, video yoki dumaloq videoni teskari aylantirish (turi saqlanadi)",
                  syntax=".reverse (ответом на медиа)", examples=[".reverse"], **MEDIA)
async def cmd_reverse(ctx: CommandContext) -> None:
    await run_media(ctx, "reverse", need="av", av_fn=lambda s, k, d, **kw: ctx.app.media.av.reverse(s, k, d, **kw), label="reverse")


@registry.command("speed", "media", aliases=["скорость", "tezlik"],
                  ru="Изменить скорость медиа: 0.25x–5x (без числа — кнопки выбора)", uz="Media tezligini o'zgartirish: 0.25x–5x (raqamsiz — tugmalar)",
                  syntax=".speed [0.25|0.5|0.75|1.25|1.5|2|3|4|5]", examples=[".speed 2", ".speed 0.5", ".speed"], **MEDIA)
async def cmd_speed(ctx: CommandContext) -> None:
    if not ctx.args:
        ref = require_media(ctx, av=True)
        await ctx.answer(ctx.t("⏩ Выберите скорость:", "⏩ Tezlikni tanlang:"),
                         markup=_pending_kb(ctx, "speed", ref, [(f"{s:g}x", f"{s:g}") for s in SPEEDS if s != 1.0]), private=ctx.is_business)
        return
    factor = _num(ctx, 2.0, 0.25, 5.0)
    await run_media(ctx, "speed", need="av", av_fn=lambda s, k, d, **kw: ctx.app.media.av.speed(s, k, d, factor, **kw), label=f"{factor:g}x")


@registry.command("ld", "media", aliases=["volume", "громкость", "loud", "ovoz"],
                  ru="Усилить громкость: 0–100 (по умолчанию 25). Шкала: +0.3 дБ за шаг → 25 = +7.5 дБ (×2.4), 100 = +30 дБ",
                  uz="Ovoz balandligini oshirish: 0–100 (standart 25). Shkala: har qadam +0.3 dB → 25 = +7.5 dB, 100 = +30 dB",
                  syntax=".ld [0-100]", examples=[".ld", ".ld 60"], **MEDIA)
async def cmd_ld(ctx: CommandContext) -> None:
    level = _num(ctx, 25, 0, 100)
    await run_media(ctx, "volume", need="av", av_fn=lambda s, k, d, **kw: ctx.app.media.av.volume(s, k, d, level, **kw),
                    label=f"+{volume_gain_db(level)} dB")


@registry.command("normalize", "media", aliases=["норм", "нормализация"], ru="Нормализация громкости (EBU R128)", uz="Ovozni normallashtirish (EBU R128)",
                  syntax=".normalize", examples=[".normalize"], **MEDIA)
async def cmd_normalize(ctx: CommandContext) -> None:
    await run_media(ctx, "normalize", need="av", av_fn=lambda s, k, d, **kw: ctx.app.media.av.normalize(s, k, d, **kw), label="normalize")


@registry.command("denoise", "voice", aliases=["шумодав", "clean"], ru="Очистка аудио от шума (FFT-шумоподавление)", uz="Audioni shovqindan tozalash",
                  syntax=".denoise", examples=[".denoise"], **MEDIA)
async def cmd_denoise(ctx: CommandContext) -> None:
    await run_media(ctx, "denoise", need="av", av_fn=lambda s, k, d, **kw: ctx.app.media.av.denoise(s, k, d, **kw), label="denoise")


@registry.command("mp3", "media", aliases=["мп3", "audio"], ru="Извлечь звук в MP3", uz="Ovozni MP3 ga ajratish", syntax=".mp3", examples=[".mp3"], **MEDIA)
async def cmd_mp3(ctx: CommandContext) -> None:
    await run_media(ctx, "mp3", need="av", av_fn=lambda s, k, d, **kw: ctx.app.media.av.to_mp3(s, k, d, **kw), label="mp3")


@registry.command("voice", "voice", aliases=["голосовое", "войс", "ovozli"], ru="Сделать голосовое из аудио/видео", uz="Audio/videodan ovozli xabar",
                  syntax=".voice", examples=[".voice"], **MEDIA)
async def cmd_voice(ctx: CommandContext) -> None:
    await run_media(ctx, "voice", need="av", av_fn=lambda s, k, d, **kw: ctx.app.media.av.to_voice(s, k, d, **kw), label="voice")


@registry.command("extract", "voice", aliases=["извлечь", "голосизвидео"], ru="Извлечь голос из видео в голосовое сообщение",
                  uz="Videodan ovozni ovozli xabar sifatida ajratish", syntax=".extract (ответом на видео)", examples=[".extract"], **MEDIA)
async def cmd_extract(ctx: CommandContext) -> None:
    ref = require_media(ctx, av=True)
    if not ref.has_video:
        raise CommandError(ctx.t("🎞 Нужно видео или кружок.", "🎞 Video yoki dumaloq video kerak."))
    await run_media(ctx, "extract", need="av", ref=ref, av_fn=lambda s, k, d, **kw: ctx.app.media.av.to_voice(s, k, d, **kw), label="extract")


@registry.command("circle", "media", aliases=["кружок", "note", "dumaloq"], ru="Сделать видеокружок из видео (до 60 с)", uz="Videodan dumaloq video (60 s gacha)",
                  syntax=".circle", examples=[".circle"], **MEDIA)
async def cmd_circle(ctx: CommandContext) -> None:
    await run_media(ctx, "circle", need="av", av_fn=lambda s, k, d, **kw: ctx.app.media.av.to_circle(s, k, d, **kw), label="circle")


@registry.command("gif", "media", aliases=["гиф"], ru="Фото или видео (до 15 с) → GIF-анимация без звука",
                  uz="Rasm yoki video (15 s gacha) → ovozsiz GIF animatsiya", syntax=".gif (ответом на фото или видео)",
                  examples=[".gif"], rate=(8, 60))
async def cmd_gif(ctx: CommandContext) -> None:
    await run_media(ctx, "gif", need="any", av_fn=lambda s, k, d, **kw: ctx.app.media.av.to_gif(s, k, d, **kw), label="gif",
                    img_out_fn=lambda im, d: (I.zoom_gif(im, d / "animation.gif"), "animation"))


def _time(s: str) -> float:
    s = s.strip()
    if re.fullmatch(r"\d+(?:\.\d+)?", s):
        return float(s)
    parts = s.split(":")
    if not 2 <= len(parts) <= 3 or not all(re.fullmatch(r"\d+(?:\.\d+)?", p) for p in parts):
        raise ValueError
    vals = [float(p) for p in parts]
    return vals[0] * 60 + vals[1] if len(vals) == 2 else vals[0] * 3600 + vals[1] * 60 + vals[2]


@registry.command("trim", "media", aliases=["обрезать", "kesish"], ru="Обрезать аудио/видео по времени", uz="Audio/videoni vaqt bo'yicha kesish",
                  syntax=".trim начало [конец]", examples=[".trim 0:05 0:20", ".trim 10"], **MEDIA)
async def cmd_trim(ctx: CommandContext) -> None:
    if not ctx.args:
        raise UsageError()
    try:
        start = _time(ctx.args[0])
        end = _time(ctx.args[1]) if len(ctx.args) > 1 else None
    except ValueError:
        raise UsageError() from None
    await run_media(ctx, "trim", need="av", av_fn=lambda s, k, d, **kw: ctx.app.media.av.trim(s, k, d, start, end, **kw), label="trim")


@registry.command("merge", "media", aliases=["склеить", "birlashtir"],
                  ru="Склеить файлы: ответьте .merge на каждый файл, затем .merge done (clear — очистить)",
                  uz="Fayllarni birlashtirish: har bir faylga .merge, so'ng .merge done (clear — tozalash)",
                  syntax=".merge | .merge done | .merge clear", examples=[".merge", ".merge done"], **MEDIA)
async def cmd_merge(ctx: CommandContext) -> None:
    key = (ctx.user_id, ctx.chat_id)
    sub = ctx.parsed.first
    buf = _MERGE.setdefault(key, [])
    if sub in ("clear", "очистить"):
        _MERGE.pop(key, None)
        await ctx.answer(ctx.t("🧹 Список склейки очищен.", "🧹 Birlashtirish ro'yxati tozalandi."), private=ctx.is_business)
        return
    if sub in ("done", "готово", "tayyor"):
        if len(buf) < 2:
            raise CommandError(ctx.t("Добавьте минимум 2 файла.", "Kamida 2 ta fayl qo'shing."))
        refs = list(buf)
        _MERGE.pop(key, None)
        app = ctx.app

        async def merge_fn(src, kind, d, **kw):
            paths = [src]
            for i, r in enumerate(refs[1:], 1):
                paths.append(await download(app, r, d / f"in{i}{_ext(r)}"))
            return await app.media.av.merge(paths, [r.kind for r in refs], d, **kw)
        await run_media(ctx, "merge", need="av", ref=refs[0], av_fn=merge_fn, label=f"merge ×{len(refs)}")
        return
    ref = require_media(ctx, av=True)
    if len(buf) >= 10:
        raise CommandError(ctx.t("Максимум 10 файлов.", "Maksimum 10 ta fayl."))
    buf.append(ref)
    await ctx.answer(ctx.t("➕ Добавлено ({n}). Когда всё — {p}merge done", "➕ Qo'shildi ({n}). Tayyor bo'lganda — {p}merge done", n=len(buf), p=ctx.prefix),
                     private=ctx.is_business)


@registry.command("compress", "media", aliases=["сжать", "siqish"], ru="Сжать фото/видео/аудио (уровень 1–3)", uz="Rasm/video/audioni siqish (1–3 daraja)",
                  syntax=".compress [1-3]", examples=[".compress", ".compress 3"], **MEDIA)
async def cmd_compress(ctx: CommandContext) -> None:
    level = int(_num(ctx, 2, 1, 3))
    q = {1: 85, 2: 65, 3: 45}[level]
    ref = require_media(ctx)
    await run_media(ctx, "compress", ref=ref, av_fn=lambda s, k, d, **kw: ctx.app.media.av.compress(s, k, d, level, **kw),
                    img_fn=lambda im: im.convert("RGB").resize((max(1, int(im.width * (1 if level < 3 else 0.75))),
                                                                max(1, int(im.height * (1 if level < 3 else 0.75))))),
                    img_format="jpg", label=f"q{q}")


@registry.command("convert", "media", aliases=["конверт", "конвертировать"], ru="Конвертировать формат: png/jpg/webp/bmp/gif/ico/pdf, mp3/ogg/wav/m4a/flac, mp4/webm/gif",
                  uz="Formatni o'zgartirish: png/jpg/webp/…, mp3/ogg/wav/…, mp4/webm/gif", syntax=".convert формат", examples=[".convert png", ".convert mp3"], **MEDIA)
async def cmd_convert(ctx: CommandContext) -> None:
    if not ctx.args:
        raise UsageError()
    fmt = ctx.parsed.first.lstrip(".")
    ref = require_media(ctx)
    if ref.is_image:
        if fmt not in ("png", "jpg", "jpeg", "webp", "bmp", "gif", "ico", "pdf"):
            raise UsageError(ctx.t("Неподдерживаемый формат для изображения.", "Rasm uchun qo'llab-quvvatlanmaydigan format."))
        await run_media(ctx, "convert", ref=ref, img_fn=lambda im: im, img_format="jpg" if fmt == "jpeg" else fmt, label=fmt)
        return
    await run_media(ctx, "convert", ref=ref, av_fn=lambda s, k, d, **kw: ctx.app.media.av.convert(s, k, d, fmt, **kw), label=fmt)


# ------------------------------------------------------------------------------------------------
# images
# ------------------------------------------------------------------------------------------------

@registry.command("ramka", "media", aliases=["рамка", "frame", "ramka_"], ru="Дизайнерская рамка: gold, luxury, diamond, neon, cyber, glass, minimal",
                  uz="Dizayner ramka: gold, luxury, diamond, neon, cyber, glass, minimal", syntax=".ramka [стиль]",
                  examples=[".ramka gold", ".ramka neon", ".ramka"], **IMG)
async def cmd_ramka(ctx: CommandContext) -> None:
    style = ctx.parsed.first
    ref = require_media(ctx, image=True)
    if style not in I.FRAME_STYLES:
        await ctx.answer(ctx.t("🖼 Выберите рамку:", "🖼 Ramkani tanlang:"),
                         markup=_pending_kb(ctx, "ramka", ref, [(s.title(), s) for s in I.FRAME_STYLES], cols=4), private=ctx.is_business)
        return
    await run_media(ctx, "ramka", ref=ref, need="image", img_fn=lambda im: I.frame(im, style), label=style)


def parse_meme(raw: str) -> tuple[str | None, str | None]:
    raw = raw.strip()
    top = bottom = None
    if "|" in raw:
        for part in raw.split("|"):
            p = part.strip()
            low = p.lower()
            if low.startswith(("up ", "верх ", "top ")):
                top = p.split(None, 1)[1] if " " in p else ""
            elif low.startswith(("down ", "низ ", "bottom ")):
                bottom = p.split(None, 1)[1] if " " in p else ""
            elif top is None:
                top = p
            else:
                bottom = p
        return top or None, bottom or None
    low = raw.lower()
    if low.startswith(("up ", "верх ", "top ")):
        return raw.split(None, 1)[1], None
    if low.startswith(("down ", "низ ", "bottom ")):
        return None, raw.split(None, 1)[1]
    return None, raw or None


@registry.command("meme", "media", aliases=["мем"], ru="Мем с текстом сверху/снизу", uz="Yuqori/pastki matnli mem",
                  syntax=".meme текст | .meme up текст | .meme down текст | .meme up верх | down низ",
                  examples=[".meme Когда код заработал", ".meme up ВЕРХ | down НИЗ", ".meme up Понедельник"], **IMG)
async def cmd_meme(ctx: CommandContext) -> None:
    top, bottom = parse_meme(ctx.raw)
    if not top and not bottom:
        raise UsageError()
    fp = ctx.app.media.font_path
    await run_media(ctx, "meme", need="image", img_fn=lambda im: I.meme(im, top, bottom, fp), label="meme")


@registry.command("blur", "media", aliases=["размыть", "xira"], ru="Размытие (радиус 1–60, по умолчанию 8)", uz="Xiralashtirish (radius 1–60)",
                  syntax=".blur [радиус]", examples=[".blur", ".blur 20"], **IMG)
async def cmd_blur(ctx: CommandContext) -> None:
    r = _num(ctx, 8, 1, 60)
    await run_media(ctx, "blur", need="image", img_fn=lambda im: I.blur(im, r))


@registry.command("pixel", "media", aliases=["пиксель", "pixelate"], ru="Пикселизация (блок 2–100)", uz="Pikselizatsiya (blok 2–100)",
                  syntax=".pixel [размер]", examples=[".pixel", ".pixel 24"], **IMG)
async def cmd_pixel(ctx: CommandContext) -> None:
    n = int(_num(ctx, 12, 2, 100))
    await run_media(ctx, "pixel", need="image", img_fn=lambda im: I.pixelate(im, n))


@registry.command("resize", "media", aliases=["размер", "o'lcham"], ru="Изменить размер: 800, 800x600, x600, 50%", uz="O'lchamni o'zgartirish: 800, 800x600, 50%",
                  syntax=".resize размер", examples=[".resize 1080", ".resize 50%", ".resize 512x512"], **IMG)
async def cmd_resize(ctx: CommandContext) -> None:
    if not ctx.args:
        raise UsageError()
    spec = ctx.args[0]
    if not re.fullmatch(r"\d{1,4}(?:%|[x×]\d{0,4})?|[x×]\d{1,4}", spec.lower()):
        raise UsageError()
    await run_media(ctx, "resize", need="image", img_fn=lambda im: I.resize(im, spec), img_format=None)


@registry.command("crop", "media", aliases=["кроп", "qirqish"], ru="Обрезать: пропорция 1:1, 16:9 или x,y,w,h", uz="Qirqish: nisbat 1:1, 16:9 yoki x,y,w,h",
                  syntax=".crop 1:1 | .crop x,y,w,h", examples=[".crop 1:1", ".crop 9:16"], **IMG)
async def cmd_crop(ctx: CommandContext) -> None:
    if not ctx.args:
        raise UsageError()
    spec = ctx.raw.replace(" ", "")
    await run_media(ctx, "crop", need="image", img_fn=lambda im: I.crop(im, spec))


@registry.command("rotate", "media", aliases=["повернуть", "aylantir"], ru="Повернуть по часовой (по умолчанию 90°)", uz="Soat yo'nalishida burish (90°)",
                  syntax=".rotate [градусы]", examples=[".rotate", ".rotate 180"], **IMG)
async def cmd_rotate(ctx: CommandContext) -> None:
    deg = _num(ctx, 90, -360, 360)
    await run_media(ctx, "rotate", need="image", img_fn=lambda im: I.rotate(im, deg))


@registry.command("mirror", "media", aliases=["зеркало", "ko'zgu"], ru="Отражение: h — горизонтально, v — вертикально", uz="Aks: h — gorizontal, v — vertikal",
                  syntax=".mirror [h|v]", examples=[".mirror", ".mirror v"], **IMG)
async def cmd_mirror(ctx: CommandContext) -> None:
    axis = ctx.parsed.first or "h"
    await run_media(ctx, "mirror", need="image", img_fn=lambda im: I.mirror(im, axis))


@registry.command("bw", "media", aliases=["чб", "oq_qora"], ru="Чёрно-белое фото", uz="Oq-qora rasm", syntax=".bw", examples=[".bw"], **IMG)
async def cmd_bw(ctx: CommandContext) -> None:
    await run_media(ctx, "bw", need="image", img_fn=I.bw)


@registry.command("sepia", "media", aliases=["сепия"], ru="Эффект сепии", uz="Sepiya effekti", syntax=".sepia", examples=[".sepia"], **IMG)
async def cmd_sepia(ctx: CommandContext) -> None:
    await run_media(ctx, "sepia", need="image", img_fn=I.sepia)


@registry.command("watermark", "media", aliases=["вотермарк", "водянойзнак", "wm", "wtm"],
                  ru="Водяной знак на фото, видео или кружок (позиция: br, bl, tr, tl, c)",
                  uz="Rasm, video yoki dumaloq videoga suv belgisi (joylashuv: br, bl, tr, tl, c)",
                  syntax=".wtm [позиция] текст", examples=[".wtm © Мой бренд", ".wtm c DRAFT"], **IMG)
async def cmd_watermark(ctx: CommandContext) -> None:
    if not ctx.raw:
        raise UsageError()
    pos, text = "br", ctx.raw
    first = ctx.parsed.first
    if first in ("br", "bl", "tr", "tl", "c") and len(ctx.args) > 1:
        pos, text = first, ctx.raw.split(None, 1)[1]
    fp = ctx.app.media.font_path

    async def video_wm(src, kind, d, **kw):
        info = await ctx.app.media.ff.probe(src)
        layer = d / "wm.png"
        I.watermark_layer((max(2, info["width"]), max(2, info["height"])), text[:80], pos, 170, fp).save(layer)
        return await ctx.app.media.av.watermark(src, kind, d, layer, **kw)

    await run_media(ctx, "watermark", need="any", img_fn=lambda im: I.watermark(im, text[:80], pos, 170, fp), av_fn=video_wm)


@registry.command("noise", "media", aliases=["шум", "shovqin"], ru="Эффект шума/зерна для фото (1–100)", uz="Rasm uchun shovqin effekti (1–100)",
                  syntax=".noise [сила]", examples=[".noise", ".noise 50"], **IMG)
async def cmd_noise(ctx: CommandContext) -> None:
    amt = int(_num(ctx, 25, 1, 100))
    await run_media(ctx, "noise", need="image", img_fn=lambda im: I.noise(im, amt))


@registry.command("sharpen", "media", aliases=["резкость", "aniqlik"], ru="Повысить резкость (0.1–5)", uz="Aniqlikni oshirish (0.1–5)",
                  syntax=".sharpen [сила]", examples=[".sharpen", ".sharpen 3"], **IMG)
async def cmd_sharpen(ctx: CommandContext) -> None:
    a = _num(ctx, 1.5, 0.1, 5)
    await run_media(ctx, "sharpen", need="image", img_fn=lambda im: I.sharpen(im, a))


@registry.command("brightness", "media", aliases=["яркость", "yorqinlik"], ru="Яркость: коэффициент 0–5 (1 = без изменений)", uz="Yorqinlik: koeffitsient 0–5",
                  syntax=".brightness [коэф.]", examples=[".brightness 1.3", ".brightness 0.7"], **IMG)
async def cmd_brightness(ctx: CommandContext) -> None:
    f = _num(ctx, 1.3, 0, 5)
    await run_media(ctx, "brightness", need="image", img_fn=lambda im: I.brightness(im, f))


@registry.command("contrast", "media", aliases=["контраст", "kontrast"], ru="Контраст: коэффициент 0–5 (1 = без изменений)", uz="Kontrast: koeffitsient 0–5",
                  syntax=".contrast [коэф.]", examples=[".contrast 1.4"], **IMG)
async def cmd_contrast(ctx: CommandContext) -> None:
    f = _num(ctx, 1.4, 0, 5)
    await run_media(ctx, "contrast", need="image", img_fn=lambda im: I.contrast(im, f))


@registry.command("sticker", "media", aliases=["стикер", "stiker"], ru="Сделать стикер из картинки (512 px WEBP)", uz="Rasmdan stiker (512 px WEBP)",
                  syntax=".sticker", examples=[".sticker"], **IMG)
async def cmd_sticker(ctx: CommandContext) -> None:
    await run_media(ctx, "sticker", need="image", img_fn=I.sticker)


@registry.command("finfo", "media", aliases=["fileinfo", "медиаинфо", "meta"], ru="Метаданные файла (формат, размер, длительность, кодеки)",
                  uz="Fayl metama'lumotlari", syntax=".finfo (ответом на медиа)", examples=[".finfo"], rate=(15, 60))
async def cmd_finfo(ctx: CommandContext) -> None:
    ref = require_media(ctx)
    app = ctx.app
    d = app.media.files.job_dir("info")
    try:
        src = await download(app, ref, d / f"input{_ext(ref)}")
        lines = [f"ℹ️ <b>{esc(ref.kind)}</b> · {round(src.stat().st_size / 1024, 1)} KB · {esc(ref.mime)}"]
        if ref.is_image:
            im = await app.media.image_op(I.open_image, src)
            inf = I.info(im, src)
            lines.append(f"🖼 {inf['width']}×{inf['height']} · {inf['mode']} · {inf['megapixels']} MP")
        elif app.health.ffmpeg_ok:
            inf = await app.media.ff.probe(src)
            lines.append(f"⏱ {inf['duration']:.2f} s · {inf['format']}")
            if inf["has_video"]:
                lines.append(f"🎞 {inf['vcodec']} {inf['width']}×{inf['height']}")
            if inf["has_audio"]:
                lines.append(f"🔊 {inf['acodec']} · {inf['sample_rate']} Hz · {inf['channels']} ch")
            if inf["bitrate"]:
                lines.append(f"📶 {inf['bitrate'] // 1000} kbit/s")
        await ctx.answer("\n".join(lines), private=ctx.is_business)
    except MediaError as e:
        raise CommandError(_err_text(ctx, e)) from None
    finally:
        app.media.files.discard(d)


@registry.command("caption", "media", aliases=["подпись", "izoh"], ru="Изменить подпись вашего медиа-сообщения (ответом на него)",
                  uz="Media xabaringiz izohini o'zgartirish (unga javob sifatida)", syntax=".caption текст | .caption -",
                  examples=[".caption Новый текст", ".caption -"], needs_reply=True, rights=["can_reply"], rate=(15, 60))
async def cmd_caption(ctx: CommandContext) -> None:
    r = ctx.reply
    if r is None or find_media(ctx) is None:
        raise CommandError(ctx.t("Ответьте на своё сообщение с медиа.", "Media bilan o'z xabaringizga javob bering."))
    if ctx.is_business and (r.from_user is None or r.from_user.id != ctx.user_id) and r.sender_business_bot is None:
        raise CommandError(ctx.t("Можно менять подпись только своих сообщений.", "Faqat o'z xabarlaringiz izohini o'zgartirish mumkin."))
    text = "" if ctx.raw.strip() == "-" else ctx.raw
    if ctx.is_business:
        res = await ctx.app.sender.edit_caption(ctx.chat_id, r.message_id, text, bc_id=ctx.bc_id)
    else:
        res = await ctx.app.sender.edit_caption(ctx.chat_id, r.message_id, text)
    if not res.ok:
        raise CommandError(ctx.t("Не удалось изменить подпись ({k}). Telegram разрешает правку чужих бизнес-сообщений только 48 ч.",
                                 "Izohni o'zgartirib bo'lmadi ({k}).", k=res.kind))
    await ctx.cleanup_command(fallback_text="✅")


@registry.command("cancel", "media", aliases=["отмена", "bekor"], ru="Отменить медиа-задачу (последнюю или по ID)", uz="Media vazifani bekor qilish",
                  syntax=".cancel [ID]", examples=[".cancel", ".cancel 42"], rate=(20, 60))
async def cmd_cancel(ctx: CommandContext) -> None:
    q = ctx.app.media.queue
    if ctx.args and ctx.args[0].isdigit():
        ids = [int(ctx.args[0])]
    else:
        ids = sorted((j.id for j in q.jobs.values() if j.user_id == ctx.user_id), reverse=True)[:1]
    ok = False
    for jid in ids:
        ok = await q.cancel(jid, ctx.user_id) or ok
    await ctx.answer(ctx.t("🛑 Задача отменена.", "🛑 Vazifa bekor qilindi.") if ok else ctx.t("Активных задач нет.", "Faol vazifalar yo'q."),
                     private=ctx.is_business)


@router.callback_query(F.data.startswith("ms:"))
async def cb_media_choice(cb: CallbackQuery, app: Any) -> None:
    _, token, value = cb.data.split(":", 2)
    item = _PENDING.get(token)
    if not item or item["ctx"].user_id != cb.from_user.id:
        await cb.answer("—")
        return
    ctx: CommandContext = item["ctx"]
    _PENDING.pop(token, None)
    await cb.answer("⏳")
    try:
        await cb.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    try:
        if item["op"] == "speed":
            factor = float(value)
            await run_media(ctx, "speed", need="av", ref=item["ref"],
                            av_fn=lambda s, k, d, **kw: app.media.av.speed(s, k, d, factor, **kw), label=f"{factor:g}x")
        elif item["op"] == "ramka" and value in I.FRAME_STYLES:
            await run_media(ctx, "ramka", need="image", ref=item["ref"], img_fn=lambda im: I.frame(im, value), label=value)
    except CommandError as e:
        await app.sender.send_text(cb.from_user.id, str(e))
