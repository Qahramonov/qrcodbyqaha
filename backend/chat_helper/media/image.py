"""Pillow image studio: designer frames, memes and classic photo tools. All functions are pure & blocking
(run them in a worker thread)."""
from __future__ import annotations

import math
import random
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps

from .ffmpeg import MediaError

FRAME_STYLES = ("gold", "luxury", "diamond", "neon", "cyber", "glass", "minimal")
MAX_SIDE = 2560
_FONT_CACHE: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}


def open_image(path: Path) -> Image.Image:
    try:
        im = Image.open(path)
        im.load()
    except Exception as e:  # corrupted / unsupported
        raise MediaError("cannot open image") from e
    if im.width * im.height > 40_000_000:
        raise MediaError("image too large")
    im = ImageOps.exif_transpose(im)
    if max(im.size) > MAX_SIDE:
        im.thumbnail((MAX_SIDE, MAX_SIDE), Image.LANCZOS)
    return im


def save_image(im: Image.Image, out_dir: Path, name: str = "result", fmt: str | None = None, quality: int = 92) -> Path:
    has_alpha = im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info)
    fmt = (fmt or ("png" if has_alpha else "jpg")).lower()
    if fmt in ("jpg", "jpeg"):
        path = out_dir / f"{name}.jpg"
        im.convert("RGB").save(path, "JPEG", quality=max(10, min(quality, 95)), optimize=True)
    elif fmt == "webp":
        path = out_dir / f"{name}.webp"
        im.save(path, "WEBP", quality=max(10, min(quality, 95)), method=4)
    elif fmt == "png":
        path = out_dir / f"{name}.png"
        im.save(path, "PNG", optimize=True)
    elif fmt == "bmp":
        path = out_dir / f"{name}.bmp"
        im.convert("RGB").save(path, "BMP")
    elif fmt == "gif":
        path = out_dir / f"{name}.gif"
        im.convert("P", palette=Image.ADAPTIVE).save(path, "GIF")
    elif fmt == "ico":
        path = out_dir / f"{name}.ico"
        im.save(path, "ICO", sizes=[(64, 64), (128, 128), (256, 256)])
    elif fmt == "pdf":
        path = out_dir / f"{name}.pdf"
        im.convert("RGB").save(path, "PDF", resolution=150)
    else:
        raise MediaError("unsupported format")
    return path


def font(size: int, font_path: str | None = None, weight: str = "Bold") -> ImageFont.FreeTypeFont:
    key = (font_path or "", size)
    if key in _FONT_CACHE:
        return _FONT_CACHE[key]
    candidates = [font_path] if font_path else []
    here = Path(__file__).resolve().parents[3] / "assets" / "fonts" / "Oswald-Variable.ttf"
    candidates += [str(here), "/system/fonts/Roboto-Bold.ttf", "/system/fonts/RobotoStatic-Bold.ttf", "/system/fonts/Roboto-Regular.ttf",
                   "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]
    for c in candidates:
        if c and Path(c).exists():
            try:
                f = ImageFont.truetype(c, size)
                try:
                    f.set_variation_by_name(weight)
                except Exception:
                    pass
                _FONT_CACHE[key] = f
                return f
            except OSError:
                continue
    f = ImageFont.load_default(size=size)
    _FONT_CACHE[key] = f  # type: ignore[assignment]
    return f  # type: ignore[return-value]


# ---------------------------------------------------------------------------------------------
# frames
# ---------------------------------------------------------------------------------------------

def _gradient(size: tuple[int, int], stops: list[tuple[float, tuple[int, int, int]]], angle: float = 45) -> Image.Image:
    w, h = size
    small = Image.new("RGB", (256, 1))
    px = small.load()
    for x in range(256):
        t = x / 255
        for i in range(len(stops) - 1):
            t0, c0 = stops[i]
            t1, c1 = stops[i + 1]
            if t0 <= t <= t1:
                k = 0 if t1 == t0 else (t - t0) / (t1 - t0)
                px[x, 0] = tuple(int(c0[j] + (c1[j] - c0[j]) * k) for j in range(3))
                break
    diag = int(math.hypot(w, h)) + 2
    g = small.resize((diag, diag), Image.BILINEAR).rotate(angle, resample=Image.BILINEAR)
    left, top = (diag - w) // 2, (diag - h) // 2
    return g.crop((left, top, left + w, top + h))


def _border_mask(size: tuple[int, int], b: int, radius: int = 0) -> Image.Image:
    w, h = size
    m = Image.new("L", size, 255)
    ImageDraw.Draw(m).rounded_rectangle((b, b, w - b - 1, h - b - 1), radius=radius, fill=0)
    return m


def _star(draw: ImageDraw.ImageDraw, x: float, y: float, r: float, fill: tuple[int, ...]) -> None:
    pts = []
    for i in range(8):
        ang = math.pi / 4 * i
        rad = r if i % 2 == 0 else r * 0.28
        pts.append((x + rad * math.cos(ang), y + rad * math.sin(ang)))
    draw.polygon(pts, fill=fill)


def frame(im: Image.Image, style: str) -> Image.Image:
    if style not in FRAME_STYLES:
        raise MediaError("unknown frame style")
    im = im.convert("RGB")
    w, h = im.size
    b = max(18, int(min(w, h) * 0.065))
    W, H = w + 2 * b, h + 2 * b
    rnd = random.Random(w * 31 + h)

    if style == "gold":
        canvas = _gradient((W, H), [(0, (110, 78, 20)), (0.35, (246, 215, 122)), (0.55, (184, 134, 43)), (0.8, (255, 236, 160)), (1, (120, 86, 24))])
        canvas.paste(im, (b, b))
        d = ImageDraw.Draw(canvas)
        d.rectangle((b - 3, b - 3, W - b + 2, H - b + 2), outline=(70, 48, 10), width=3)
        d.rectangle((2, 2, W - 3, H - 3), outline=(255, 240, 190), width=2)
        d.rectangle((b // 2, b // 2, W - b // 2, H - b // 2), outline=(150, 105, 30), width=max(1, b // 14))
        for cx, cy in ((b // 2, b // 2), (W - b // 2, b // 2), (b // 2, H - b // 2), (W - b // 2, H - b // 2)):
            r = b * 0.42
            d.polygon([(cx, cy - r), (cx + r, cy), (cx, cy + r), (cx - r, cy)], fill=(255, 235, 150), outline=(110, 75, 15))
        return canvas

    if style == "luxury":
        canvas = _gradient((W, H), [(0, (20, 6, 12)), (0.5, (70, 10, 28)), (1, (15, 4, 10))], 135)
        vign = Image.new("L", (w, h), 0)
        ImageDraw.Draw(vign).ellipse((-w * 0.25, -h * 0.25, w * 1.25, h * 1.25), fill=255)
        vign = vign.filter(ImageFilter.GaussianBlur(min(w, h) // 6))
        photo = Image.composite(im, ImageEnhance.Brightness(im).enhance(0.55), vign)
        canvas.paste(photo, (b, b))
        d = ImageDraw.Draw(canvas)
        gold = (212, 175, 90)
        for off, wd in ((b * 0.25, 2), (b * 0.45, 1), (b - 4, 2)):
            o = int(off)
            d.rectangle((o, o, W - o - 1, H - o - 1), outline=gold, width=wd)
        for cx, cy, sx, sy in ((b * 0.25, b * 0.25, 1, 1), (W - b * 0.25, b * 0.25, -1, 1), (b * 0.25, H - b * 0.25, 1, -1), (W - b * 0.25, H - b * 0.25, -1, -1)):
            rr = b * 0.35
            d.ellipse((cx - rr, cy - rr, cx + rr, cy + rr), outline=gold, width=2)
            d.line((cx, cy, cx + sx * b * 1.6, cy), fill=gold, width=2)
            d.line((cx, cy, cx, cy + sy * b * 1.6), fill=gold, width=2)
        return canvas

    if style == "diamond":
        canvas = _gradient((W, H), [(0, (200, 210, 225)), (0.3, (250, 252, 255)), (0.5, (160, 175, 200)), (0.75, (245, 248, 255)), (1, (180, 190, 210))], 30)
        d = ImageDraw.Draw(canvas, "RGBA")
        step = max(10, b // 2)
        for x in range(0, W, step):
            for y in (0, H - b):
                d.polygon([(x, y), (x + step / 2, y + b / 2), (x, y + b)], fill=(255, 255, 255, 70))
                d.polygon([(x + step / 2, y + b / 2), (x + step, y), (x + step, y + b)], fill=(120, 140, 170, 50))
        for y in range(0, H, step):
            for x in (0, W - b):
                d.polygon([(x, y), (x + b / 2, y + step / 2), (x + b, y)], fill=(255, 255, 255, 60))
        canvas.paste(im, (b, b))
        d = ImageDraw.Draw(canvas, "RGBA")
        d.rectangle((b - 2, b - 2, W - b + 1, H - b + 1), outline=(255, 255, 255, 230), width=2)
        for _ in range(28):
            side = rnd.choice(("t", "b", "l", "r"))
            x = rnd.uniform(0, W) if side in "tb" else (rnd.uniform(0, b) if side == "l" else rnd.uniform(W - b, W))
            y = rnd.uniform(0, H) if side in "lr" else (rnd.uniform(0, b) if side == "t" else rnd.uniform(H - b, H))
            _star(d, x, y, rnd.uniform(b * 0.15, b * 0.45), (255, 255, 255, 235))
        return canvas

    if style == "neon":
        canvas = Image.new("RGB", (W, H), (8, 6, 20))
        canvas.paste(im, (b, b))
        glow = Image.new("RGB", (W, H), (0, 0, 0))
        gd = ImageDraw.Draw(glow)
        lw = max(3, b // 6)
        gd.rounded_rectangle((b // 2, b // 2, W - b // 2, H - b // 2), radius=b // 2, outline=(0, 240, 255), width=lw)
        gd.rounded_rectangle((b // 4, b // 4, W - b // 4, H - b // 4), radius=b // 2, outline=(255, 40, 200), width=max(2, lw // 2))
        blur1 = glow.filter(ImageFilter.GaussianBlur(b // 3))
        blur2 = glow.filter(ImageFilter.GaussianBlur(b // 8))
        out = ImageChops.screen(canvas, blur1)
        out = ImageChops.screen(out, blur2)
        out = ImageChops.screen(out, glow)
        out.paste(im, (b, b))
        return out

    if style == "cyber":
        canvas = Image.new("RGB", (W, H), (6, 10, 16))
        r, g, bl = im.split()
        shift = max(2, w // 220)
        glitch = Image.merge("RGB", (ImageChops.offset(r, shift, 0), g, ImageChops.offset(bl, -shift, 0)))
        canvas.paste(glitch, (b, b))
        d = ImageDraw.Draw(canvas, "RGBA")
        for y in range(0, H, 4):
            d.line((0, y, W, y), fill=(0, 0, 0, 55))
        cyan, mag = (0, 255, 230, 255), (255, 0, 140, 255)
        L = b * 2.2
        lw = max(3, b // 5)
        for cx, cy, sx, sy in ((b // 3, b // 3, 1, 1), (W - b // 3, b // 3, -1, 1), (b // 3, H - b // 3, 1, -1), (W - b // 3, H - b // 3, -1, -1)):
            d.line((cx, cy, cx + sx * L, cy), fill=cyan, width=lw)
            d.line((cx, cy, cx, cy + sy * L), fill=cyan, width=lw)
        for x in range(int(b * 3), int(W - b * 3), max(8, b // 2)):
            d.line((x, b // 3, x, b // 3 + (b // 4 if (x // 8) % 3 else b // 2)), fill=(0, 255, 230, 140), width=1)
        d.rectangle((b - 2, b - 2, W - b + 1, H - b + 1), outline=mag, width=2)
        return canvas

    if style == "glass":
        bg = im.resize((W, H), Image.LANCZOS).filter(ImageFilter.GaussianBlur(max(12, b)))
        bg = ImageEnhance.Brightness(bg).enhance(1.12)
        overlay = Image.new("RGBA", (W, H), (255, 255, 255, 60))
        canvas = Image.alpha_composite(bg.convert("RGBA"), overlay)
        shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(shadow).rounded_rectangle((b + 4, b + 8, b + w + 4, b + h + 8), radius=b // 2, fill=(0, 0, 0, 110))
        canvas = Image.alpha_composite(canvas, shadow.filter(ImageFilter.GaussianBlur(b // 3)))
        mask = Image.new("L", (w, h), 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, w - 1, h - 1), radius=b // 2, fill=255)
        canvas.paste(im, (b, b), mask)
        d = ImageDraw.Draw(canvas)
        d.rounded_rectangle((b, b, b + w - 1, b + h - 1), radius=b // 2, outline=(255, 255, 255, 200), width=2)
        d.rounded_rectangle((3, 3, W - 4, H - 4), radius=b, outline=(255, 255, 255, 150), width=2)
        return canvas.convert("RGB")

    # minimal
    pad = max(b, int(min(w, h) * 0.08))
    W2, H2 = w + 2 * pad, h + 2 * pad
    canvas = Image.new("RGB", (W2, H2), (250, 250, 248))
    shadow = Image.new("RGBA", (W2, H2), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rectangle((pad + 3, pad + 6, pad + w + 3, pad + h + 6), fill=(0, 0, 0, 90))
    canvas = Image.alpha_composite(canvas.convert("RGBA"), shadow.filter(ImageFilter.GaussianBlur(pad // 6 + 2))).convert("RGB")
    canvas.paste(im, (pad, pad))
    ImageDraw.Draw(canvas).rectangle((pad - 1, pad - 1, pad + w, pad + h), outline=(210, 210, 205), width=1)
    return canvas


# ---------------------------------------------------------------------------------------------
# meme
# ---------------------------------------------------------------------------------------------

def _wrap(draw: ImageDraw.ImageDraw, text: str, fnt: ImageFont.FreeTypeFont, max_w: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    cur = ""
    for wd in words:
        trial = (cur + " " + wd).strip()
        if draw.textlength(trial, font=fnt) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = wd
    if cur:
        lines.append(cur)
    return lines


def _fit(draw: ImageDraw.ImageDraw, text: str, w: int, h: int, font_path: str | None) -> tuple[ImageFont.FreeTypeFont, list[str]]:
    size = max(18, int(w / 7))
    while size > 14:
        fnt = font(size, font_path)
        lines = _wrap(draw, text, fnt, int(w * 0.88))
        if len(lines) <= 3 and all(draw.textlength(ln, font=fnt) + fnt.size // 5 <= w * 0.92 for ln in lines) and size * 1.15 * len(lines) <= h * 0.32:
            return fnt, lines
        size = int(size * 0.9)
    fnt = font(14, font_path)
    return fnt, _wrap(draw, text, fnt, int(w * 0.94))[:4]


def meme(im: Image.Image, top: str | None, bottom: str | None, font_path: str | None = None) -> Image.Image:
    im = im.convert("RGB")
    if min(im.size) < 320:
        scale = 320 / min(im.size)
        im = im.resize((int(im.width * scale), int(im.height * scale)), Image.LANCZOS)
    d = ImageDraw.Draw(im)
    w, h = im.size
    for text, at_top in ((top, True), (bottom, False)):
        if not text:
            continue
        text = text.upper().strip()[:200]
        fnt, lines = _fit(d, text, w, h, font_path)
        lh = int(fnt.size * 1.12)
        stroke = max(2, fnt.size // 11)
        y = int(h * 0.025) if at_top else h - int(h * 0.03) - lh * len(lines)
        for ln in lines:
            tw = d.textlength(ln, font=fnt)
            d.text(((w - tw) / 2, y), ln, font=fnt, fill="white", stroke_width=stroke, stroke_fill="black")
            y += lh
    return im


# ---------------------------------------------------------------------------------------------
# classic tools
# ---------------------------------------------------------------------------------------------

def blur(im: Image.Image, radius: float = 8) -> Image.Image:
    return im.convert("RGB").filter(ImageFilter.GaussianBlur(max(0.5, min(radius, 60))))


def pixelate(im: Image.Image, block: int = 12) -> Image.Image:
    im = im.convert("RGB")
    block = max(2, min(block, 100))
    small = im.resize((max(1, im.width // block), max(1, im.height // block)), Image.NEAREST)
    return small.resize(im.size, Image.NEAREST)


def resize(im: Image.Image, spec: str) -> Image.Image:
    spec = spec.lower().replace("×", "x").strip()
    if spec.endswith("%"):
        k = float(spec[:-1]) / 100
        if not 0.05 <= k <= 4:
            raise MediaError("scale must be 5%..400%")
        size = (max(1, int(im.width * k)), max(1, int(im.height * k)))
    elif "x" in spec:
        a, b = spec.split("x", 1)
        tw, th = int(a or 0), int(b or 0)
        if tw <= 0 and th <= 0:
            raise MediaError("bad size")
        if tw <= 0:
            tw = int(im.width * th / im.height)
        if th <= 0:
            th = int(im.height * tw / im.width)
        size = (tw, th)
    else:
        tw = int(spec)
        size = (tw, int(im.height * tw / im.width))
    if not (1 <= size[0] <= 4096 and 1 <= size[1] <= 4096):
        raise MediaError("size must be within 4096 px")
    return im.resize(size, Image.LANCZOS)


def crop(im: Image.Image, spec: str) -> Image.Image:
    spec = spec.strip().lower()
    if ":" in spec:
        a, b = (float(x) for x in spec.split(":", 1))
        if a <= 0 or b <= 0:
            raise MediaError("bad ratio")
        target = a / b
        w, h = im.size
        if w / h > target:
            nw = int(h * target)
            box = ((w - nw) // 2, 0, (w - nw) // 2 + nw, h)
        else:
            nh = int(w / target)
            box = (0, (h - nh) // 2, w, (h - nh) // 2 + nh)
        return im.crop(box)
    parts = [int(x) for x in spec.replace(" ", "").split(",")]
    if len(parts) != 4:
        raise MediaError("crop: use ratio 1:1 or x,y,w,h")
    x, y, cw, ch = parts
    if cw <= 0 or ch <= 0 or x < 0 or y < 0 or x + cw > im.width or y + ch > im.height:
        raise MediaError("crop box outside image")
    return im.crop((x, y, x + cw, y + ch))


def rotate(im: Image.Image, degrees: float = 90) -> Image.Image:
    return im.rotate(-degrees, expand=True, resample=Image.BICUBIC, fillcolor=(0, 0, 0) if im.mode == "RGB" else None)


def mirror(im: Image.Image, axis: str = "h") -> Image.Image:
    return ImageOps.flip(im) if axis.startswith("v") else ImageOps.mirror(im)


def bw(im: Image.Image) -> Image.Image:
    return ImageOps.grayscale(im).convert("RGB")


def sepia(im: Image.Image) -> Image.Image:
    g = ImageOps.grayscale(im)
    return ImageOps.colorize(g, (40, 26, 13), (255, 240, 192), mid=(160, 120, 70))


def watermark(im: Image.Image, text: str, position: str = "br", opacity: int = 160, font_path: str | None = None) -> Image.Image:
    im = im.convert("RGBA")
    layer = Image.new("RGBA", im.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    fnt = font(max(14, im.width // 22), font_path, "Medium")
    tw = d.textlength(text, font=fnt)
    th = fnt.size
    m = im.width // 40 + 4
    pos = {"br": (im.width - tw - m, im.height - th - m * 1.5), "bl": (m, im.height - th - m * 1.5), "tr": (im.width - tw - m, m),
           "tl": (m, m), "c": ((im.width - tw) / 2, (im.height - th) / 2)}.get(position, (im.width - tw - m, im.height - th - m * 1.5))
    d.text(pos, text, font=fnt, fill=(255, 255, 255, opacity), stroke_width=max(1, th // 14), stroke_fill=(0, 0, 0, opacity // 2))
    return Image.alpha_composite(im, layer).convert("RGB")


def watermark_layer(size: tuple[int, int], text: str, position: str = "br", opacity: int = 170,
                    font_path: str | None = None) -> Image.Image:
    """Transparent full-size RGBA layer with the watermark text (used to overlay videos with FFmpeg)."""
    blank = Image.new("RGBA", size, (0, 0, 0, 0))
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    fnt = font(max(14, size[0] // 22), font_path, "Medium")
    tw, th = d.textlength(text, font=fnt), fnt.size
    m = size[0] // 40 + 4
    pos = {"br": (size[0] - tw - m, size[1] - th - m * 1.5), "bl": (m, size[1] - th - m * 1.5), "tr": (size[0] - tw - m, m),
           "tl": (m, m), "c": ((size[0] - tw) / 2, (size[1] - th) / 2)}.get(position, (size[0] - tw - m, size[1] - th - m * 1.5))
    d.text(pos, text, font=fnt, fill=(255, 255, 255, opacity), stroke_width=max(1, th // 14), stroke_fill=(0, 0, 0, opacity // 2))
    return Image.alpha_composite(blank, layer)


def zoom_gif(im: Image.Image, out: Path, seconds: float = 2.5, fps: int = 12, max_side: int = 480) -> Path:
    """Photo → short animated GIF (slow zoom, «Ken Burns»)."""
    im = im.convert("RGB")
    im.thumbnail((max_side, max_side))
    w, h = im.size
    frames = []
    n = max(2, int(seconds * fps))
    for i in range(n):
        z = 1 + 0.12 * i / (n - 1)
        cw, ch = int(w / z), int(h / z)
        left, top = (w - cw) // 2, (h - ch) // 2
        frames.append(im.crop((left, top, left + cw, top + ch)).resize((w, h), Image.LANCZOS).quantize(colors=128))
    frames[0].save(out, save_all=True, append_images=frames[1:], duration=int(1000 / fps), loop=0, optimize=True)
    return out


def noise(im: Image.Image, amount: int = 25) -> Image.Image:
    im = im.convert("RGB")
    amount = max(1, min(amount, 100))
    n = Image.effect_noise(im.size, amount * 2).convert("RGB")
    return ImageChops.blend(im, ImageChops.overlay(im, n), min(0.9, amount / 100 + 0.15))


def sharpen(im: Image.Image, amount: float = 1.5) -> Image.Image:
    percent = int(max(0.1, min(float(amount), 5.0)) * 100)
    return im.convert("RGB").filter(ImageFilter.UnsharpMask(radius=2, percent=percent, threshold=2))


def brightness(im: Image.Image, factor: float) -> Image.Image:
    return ImageEnhance.Brightness(im.convert("RGB")).enhance(max(0.0, min(factor, 5.0)))


def contrast(im: Image.Image, factor: float) -> Image.Image:
    return ImageEnhance.Contrast(im.convert("RGB")).enhance(max(0.0, min(factor, 5.0)))


def sticker(im: Image.Image) -> Image.Image:
    im = im.convert("RGBA")
    im.thumbnail((512, 512), Image.LANCZOS)
    if max(im.size) < 512:
        k = 512 / max(im.size)
        im = im.resize((max(1, int(im.width * k)), max(1, int(im.height * k))), Image.LANCZOS)
    return im


def info(im: Image.Image, path: Path) -> dict[str, object]:
    return {"width": im.width, "height": im.height, "mode": im.mode, "format": im.format or path.suffix.lstrip("."),
            "size_kb": round(path.stat().st_size / 1024, 1), "megapixels": round(im.width * im.height / 1e6, 2)}


def demo_image(size: tuple[int, int] = (640, 480)) -> Image.Image:
    """Synthetic test picture for the APK effects demo (no user data involved)."""
    im = _gradient(size, [(0, (40, 30, 120)), (0.5, (220, 80, 140)), (1, (255, 200, 90))], 30)
    d = ImageDraw.Draw(im)
    w, h = size
    d.ellipse((w * 0.32, h * 0.2, w * 0.68, h * 0.68), fill=(255, 240, 200))
    d.polygon([(0, h), (w * 0.3, h * 0.55), (w * 0.55, h), ], fill=(30, 20, 60))
    d.polygon([(w * 0.35, h), (w * 0.7, h * 0.5), (w, h)], fill=(50, 30, 90))
    d.text((20, 20), "Chat helper", font=font(36), fill="white")
    return im
