"""Original onboarding infographic: «how to connect Chat helper» (RU / UZ), vertical 1080×1920.

Everything is drawn here with Pillow primitives (no third-party artwork or logos). The PNGs are pre-rendered into
``assets/onboarding/`` by ``backend/tools/render_assets.py``; at runtime the bot uses those files and only falls back
to rendering on the fly (with whatever fonts the device has) if they are missing.
"""
from __future__ import annotations

import io
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[3]
ASSETS = ROOT / "assets" / "onboarding"
SCALE = 2                      # render at 2x and downsample → smooth edges
W, H = 1080, 1920

BG_TOP = (9, 12, 28)
BG_BOTTOM = (22, 14, 48)
ACCENT_A = (59, 130, 246)       # blue
ACCENT_B = (139, 92, 246)       # violet
TEXT = (240, 243, 255)
TEXT_DIM = (166, 176, 206)

STEPS = {
    "ru": {
        "title": "Подключение за 1 минуту",
        "subtitle": "Официальная функция Telegram «Автоматизация чатов»",
        "steps": [
            ("Скопируйте username бота", "Кнопка «Скопировать» в чате с ботом"),
            ("Откройте настройки профиля", "Настройки → Изм. (Edit)"),
            ("Раздел «Автоматизация чатов»", "Старые версии: Telegram для бизнеса → Чат-боты"),
            ("Добавьте бота", "Вставьте username и выберите чаты"),
            ("Выдайте права", "Чтение, ответы, удаление сообщений"),
            ("Проверьте подключение", "Вернитесь в бот → «Проверить подключение»"),
        ],
        "footer": "Chat helper · официальный Telegram Bot API · без паролей и кодов входа",
    },
    "uz": {
        "title": "1 daqiqada ulash",
        "subtitle": "Telegram'ning rasmiy «Chat automation» funksiyasi",
        "steps": [
            ("Bot username'ini nusxalang", "Bot chatidagi «Nusxalash» tugmasi"),
            ("Profil sozlamalarini oching", "Sozlamalar → Tahrirlash (Edit)"),
            ("«Chatlarni avtomatlashtirish»", "Eski versiyalar: Telegram Business → Chat-botlar"),
            ("Botni qo'shing", "Username'ni qo'ying va chatlarni tanlang"),
            ("Huquqlarni bering", "O'qish, javob berish, xabarlarni o'chirish"),
            ("Ulanishni tekshiring", "Botga qayting → «Ulanishni tekshirish»"),
        ],
        "footer": "Chat helper · rasmiy Telegram Bot API · parol va kirish kodlarisiz",
    },
}

_FONT_FILES = {
    "bold": ["/usr/share/fonts/opentype/inter/Inter-Bold.otf", "/system/fonts/Roboto-Bold.ttf",
             "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"],
    "semibold": ["/usr/share/fonts/opentype/inter/Inter-SemiBold.otf", "/system/fonts/Roboto-Medium.ttf",
                 "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"],
    "regular": ["/usr/share/fonts/opentype/inter/Inter-Regular.otf", "/system/fonts/Roboto-Regular.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"],
}


def _font(kind: str, size: int) -> ImageFont.FreeTypeFont:
    for path in _FONT_FILES[kind]:
        if Path(path).exists():
            return ImageFont.truetype(path, size * SCALE)
    oswald = ROOT / "assets" / "fonts" / "Oswald-Variable.ttf"
    f = ImageFont.truetype(str(oswald), size * SCALE)
    try:
        f.set_variation_by_name("Bold" if kind != "regular" else "Regular")
    except Exception:  # pragma: no cover
        pass
    return f


def _s(v: float) -> int:
    return int(round(v * SCALE))


def _lerp(a: tuple[int, ...], b: tuple[int, ...], t: float) -> tuple[int, ...]:
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(len(a)))


def _vertical_gradient(w: int, h: int, top: tuple[int, int, int], bottom: tuple[int, int, int]) -> Image.Image:
    col = Image.new("RGB", (1, 256))
    px = col.load()
    for y in range(256):
        px[0, y] = _lerp(top, bottom, y / 255)
    return col.resize((w, h), Image.BILINEAR)


def _diag_gradient(size: int, a: tuple[int, int, int], b: tuple[int, int, int]) -> Image.Image:
    row = Image.new("RGB", (256, 1))
    px = row.load()
    for x in range(256):
        px[x, 0] = _lerp(a, b, x / 255)
    big = row.resize((size * 2, size * 2), Image.BILINEAR).rotate(45, resample=Image.BILINEAR)
    o = size // 2
    return big.crop((o, o, o + size, o + size))


def _glow(canvas: Image.Image, cx: float, cy: float, r: float, color: tuple[int, int, int], alpha: int) -> None:
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(*color, alpha))
    layer = layer.filter(ImageFilter.GaussianBlur(r * 0.45))
    canvas.alpha_composite(layer)


def _rounded_mask(size: tuple[int, int], radius: int) -> Image.Image:
    m = Image.new("L", size, 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, size[0] - 1, size[1] - 1), radius=radius, fill=255)
    return m


# ---- icons (white line art inside a gradient tile) ------------------------------------------------------
def _icon(kind: str, d: ImageDraw.ImageDraw, x: int, y: int, s: int) -> None:
    w = max(2, s // 14)
    white = (255, 255, 255, 255)
    cx, cy = x + s / 2, y + s / 2
    if kind == "copy":
        d.rounded_rectangle((x + s * .30, y + s * .22, x + s * .76, y + s * .72), radius=s * .08, outline=white, width=w)
        d.rounded_rectangle((x + s * .22, y + s * .32, x + s * .66, y + s * .80), radius=s * .08, fill=(255, 255, 255, 60), outline=white, width=w)
    elif kind == "gear":
        teeth, ro, ri = 8, s * .33, s * .25
        pts = []
        for i in range(teeth * 2):
            a0 = math.pi * 2 * i / (teeth * 2)
            r = ro if i % 2 == 0 else ri
            for da in (-0.17, 0.17):
                pts.append((cx + r * math.cos(a0 + da), cy + r * math.sin(a0 + da)))
        d.polygon(pts, outline=white, width=w)
        d.ellipse((cx - s * .10, cy - s * .10, cx + s * .10, cy + s * .10), outline=white, width=w)
    elif kind == "automation":
        d.rounded_rectangle((x + s * .18, y + s * .22, x + s * .82, y + s * .66), radius=s * .14, outline=white, width=w)
        d.polygon([(x + s * .32, y + s * .64), (x + s * .30, y + s * .80), (x + s * .46, y + s * .66)], fill=white)
        bolt = [(cx + s * .04, y + s * .28), (cx - s * .10, cy + s * .02), (cx, cy + s * .02),
                (cx - s * .04, y + s * .60), (cx + s * .11, cy - s * .04), (cx + s * .01, cy - s * .04)]
        d.polygon(bolt, fill=white)
    elif kind == "add":
        d.rounded_rectangle((x + s * .18, y + s * .30, x + s * .66, y + s * .74), radius=s * .12, outline=white, width=w)
        d.line((x + s * .42, y + s * .30, x + s * .42, y + s * .20), fill=white, width=w)
        d.ellipse((x + s * .38, y + s * .14, x + s * .46, y + s * .22), fill=white)
        for ex in (.32, .52):
            d.ellipse((x + s * ex - s * .04, y + s * .46, x + s * ex + s * .04, y + s * .54), fill=white)
        d.ellipse((x + s * .56, y + s * .56, x + s * .86, y + s * .86), fill=(255, 255, 255, 255))
        d.line((x + s * .71, y + s * .62, x + s * .71, y + s * .80), fill=(91, 108, 246, 255), width=w)
        d.line((x + s * .62, y + s * .71, x + s * .80, y + s * .71), fill=(91, 108, 246, 255), width=w)
    elif kind == "shield":
        pts = [(cx, y + s * .16), (x + s * .78, y + s * .28), (x + s * .74, y + s * .58), (cx, y + s * .86),
               (x + s * .26, y + s * .58), (x + s * .22, y + s * .28)]
        d.polygon(pts, outline=white, width=w)
        d.line((x + s * .36, cy + s * .02, x + s * .47, cy + s * .13, x + s * .65, cy - s * .10), fill=white, width=w, joint="curve")
    elif kind == "check":
        d.arc((x + s * .18, y + s * .18, x + s * .82, y + s * .82), start=-60, end=250, fill=white, width=w)
        d.polygon([(x + s * .72, y + s * .14), (x + s * .86, y + s * .30), (x + s * .66, y + s * .33)], fill=white)
        d.line((x + s * .36, cy + s * .01, x + s * .47, cy + s * .12, x + s * .66, cy - s * .10), fill=white, width=w, joint="curve")


ICONS = ["copy", "gear", "automation", "add", "shield", "check"]


def _logo(canvas: Image.Image, x: int, y: int, size: int) -> None:
    tile = _diag_gradient(size, ACCENT_A, ACCENT_B).convert("RGBA")
    tile.putalpha(_rounded_mask((size, size), int(size * .28)))
    canvas.alpha_composite(tile, (x, y))
    d = ImageDraw.Draw(canvas)
    w = max(2, size // 14)
    d.rounded_rectangle((x + size * .22, y + size * .26, x + size * .78, y + size * .66), radius=size * .14,
                        outline=(255, 255, 255, 255), width=w)
    d.polygon([(x + size * .34, y + size * .64), (x + size * .30, y + size * .80), (x + size * .48, y + size * .66)],
              fill=(255, 255, 255, 255))
    for i, k in enumerate((.38, .50, .62)):
        r = size * .035
        d.ellipse((x + size * k - r, y + size * .46 - r, x + size * k + r, y + size * .46 + r), fill=(255, 255, 255, 255))


def _fit(d: ImageDraw.ImageDraw, text: str, font_kind: str, size: int, max_w: int) -> ImageFont.FreeTypeFont:
    while size > 14:
        f = _font(font_kind, size)
        if d.textlength(text, font=f) <= max_w:
            return f
        size -= 1
    return _font(font_kind, 14)


def render(lang: str = "ru") -> Image.Image:
    data = STEPS.get(lang, STEPS["ru"])
    cw, ch = _s(W), _s(H)
    canvas = _vertical_gradient(cw, ch, BG_TOP, BG_BOTTOM).convert("RGBA")
    _glow(canvas, _s(120), _s(160), _s(420), ACCENT_A, 120)
    _glow(canvas, _s(980), _s(1700), _s(520), ACCENT_B, 110)
    _glow(canvas, _s(900), _s(700), _s(260), (34, 211, 238), 40)
    d = ImageDraw.Draw(canvas)

    # header: logo + brand pill
    _logo(canvas, _s(72), _s(84), _s(92))
    d.text((_s(186), _s(96)), "Chat helper", font=_font("bold", 40), fill=TEXT)
    d.text((_s(188), _s(146)), "Telegram Business · Secretary", font=_font("regular", 22), fill=TEXT_DIM)
    title_f = _fit(d, data["title"], "bold", 64, _s(W - 144))
    d.text((_s(72), _s(232)), data["title"], font=title_f, fill=TEXT)
    sub_f = _fit(d, data["subtitle"], "regular", 28, _s(W - 144))
    d.text((_s(72), _s(320)), data["subtitle"], font=sub_f, fill=TEXT_DIM)

    # steps
    top, card_h, gap = 400, 206, 36
    for i, (title, sub) in enumerate(data["steps"]):
        y0 = top + i * (card_h + gap)
        box = (_s(56), _s(y0), _s(W - 56), _s(y0 + card_h))
        glass = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        gd = ImageDraw.Draw(glass)
        gd.rounded_rectangle(box, radius=_s(36), fill=(255, 255, 255, 18), outline=(255, 255, 255, 46), width=_s(2))
        canvas.alpha_composite(glass)
        # number badge
        bx, by, br = _s(110), _s(y0 + card_h / 2), _s(34)
        badge = _diag_gradient(br * 2, ACCENT_A, ACCENT_B).convert("RGBA")
        bm = Image.new("L", (br * 2, br * 2), 0)
        ImageDraw.Draw(bm).ellipse((0, 0, br * 2 - 1, br * 2 - 1), fill=255)
        badge.putalpha(bm)
        canvas.alpha_composite(badge, (bx - br, by - br))
        num_f = _font("bold", 32)
        n = str(i + 1)
        tw = d.textlength(n, font=num_f)
        d.text((bx - tw / 2, by - _s(21)), n, font=num_f, fill=(255, 255, 255))
        # icon tile
        ts = _s(108)
        tx, ty = _s(166), _s(y0 + (card_h - 108) / 2)
        tile = Image.new("RGBA", (ts, ts), (0, 0, 0, 0))
        tdraw = ImageDraw.Draw(tile)
        tdraw.rounded_rectangle((0, 0, ts - 1, ts - 1), radius=_s(26), fill=(255, 255, 255, 26), outline=(255, 255, 255, 60), width=_s(2))
        _icon(ICONS[i], tdraw, int(ts * .12), int(ts * .12), int(ts * .76))
        canvas.alpha_composite(tile, (tx, ty))
        # text
        text_x = _s(300)
        max_w = _s(W - 56 - 300 - 32)
        tf = _fit(d, title, "semibold", 38, max_w)
        sf = _fit(d, sub, "regular", 26, max_w)
        d.text((text_x, _s(y0 + 52)), title, font=tf, fill=TEXT)
        d.text((text_x, _s(y0 + 112)), sub, font=sf, fill=TEXT_DIM)
        # arrow to the next card
        if i < len(data["steps"]) - 1:
            ax, ay = _s(110), _s(y0 + card_h + gap / 2)
            d.polygon([(ax - _s(14), ay - _s(8)), (ax + _s(14), ay - _s(8)), (ax, ay + _s(10))], fill=(*ACCENT_B, 255))

    foot_f = _fit(d, data["footer"], "regular", 24, _s(W - 144))
    fw = d.textlength(data["footer"], font=foot_f)
    d.text(((cw - fw) / 2, _s(H - 84)), data["footer"], font=foot_f, fill=TEXT_DIM)
    return canvas.convert("RGB").resize((W, H), Image.LANCZOS)


def png_bytes(lang: str = "ru") -> bytes:
    """Pre-rendered asset if present, otherwise render now."""
    path = ASSETS / f"connect_{'uz' if lang == 'uz' else 'ru'}.png"
    if path.exists():
        return path.read_bytes()
    buf = io.BytesIO()
    render(lang).save(buf, "PNG", optimize=True)
    return buf.getvalue()


def save_assets() -> list[Path]:
    ASSETS.mkdir(parents=True, exist_ok=True)
    out = []
    for lang in ("ru", "uz"):
        p = ASSETS / f"connect_{lang}.png"
        render(lang).save(p, "PNG", optimize=True)
        out.append(p)
    return out
