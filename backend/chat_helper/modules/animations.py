"""Animation Engine for ``.a`` — 16 animation types, 4 speeds, cancel, Telegram-friendly pacing.

Telegram allows roughly one message update per second per chat; short bursts of faster edits are tolerated but
endless fast editing ends in FloodWait. The engine therefore keeps animations *short* (a fixed frame budget per
speed), never retries a rate-limited edit (it stops and writes the final text instead), runs one animation per chat
and at most a few in parallel globally, skips identical frames and always leaves the clean final text.
"""
from __future__ import annotations

import asyncio
import logging
import random
import time
from typing import TYPE_CHECKING, Any

from aiogram import F, Router
from aiogram.types import CallbackQuery

from ..commands.context import CommandContext, CommandError, UsageError
from ..commands.registry import registry
from ..keyboards import kb
from ..localization import tr
from ..security.sanitize import esc
from ..services.settings import ANIM_TYPES
from ..utils.unicode import graphemes

if TYPE_CHECKING:  # pragma: no cover
    from ..core.context import AppContext

log = logging.getLogger(__name__)
router = Router(name="animations")

SPEEDS = {"slow": (1.2, 10), "normal": (0.8, 12), "fast": (0.5, 12), "turbo": (0.3, 10)}   # interval s, frame budget
TYPE_ALIASES = {
    "type": "typewriter", "печать": "typewriter", "быстро": "fast", "reverse": "reverse", "обратно": "reverse", "волна": "wave",
    "глитч": "glitch", "матрица": "matrix", "точки": "dots", "loading": "dots", "прогресс": "progress", "отсчёт": "countdown",
    "отсчет": "countdown", "пульс": "pulse", "сердце": "heart", "hearts": "heart", "слайд": "slide", "радуга": "rainbow",
    "счётчик": "counter", "счетчик": "counter", "reveal": "reveal", "появление": "reveal", "свой": "custom",
}
SPEED_ALIASES = {"slow": "slow", "медленно": "slow", "normal": "normal", "обычно": "normal", "turbo": "turbo", "турбо": "turbo",
                 "sekin": "slow", "tez": "turbo"}
TYPE_TITLES = {
    "typewriter": ("animations.type_titles.pechatnaya_mashinka"), "fast": ("animations.type_titles.bystraya_pechat"),
    "reverse": ("animations.type_titles.obratnaya_pechat"), "wave": ("animations.type_titles.volna"), "glitch": ("animations.type_titles.glitch"),
    "matrix": ("animations.type_titles.matritsa"), "dots": ("animations.type_titles.tochki_zagruzki"),
    "progress": ("animations.type_titles.progress_bar"), "countdown": ("animations.type_titles.obratnyy_otschyot"),
    "pulse": ("animations.type_titles.puls_emodzi"), "heart": ("animations.type_titles.serdechki"), "slide": ("animations.type_titles.vyezd_teksta"),
    "rainbow": ("animations.type_titles.raduga"), "counter": ("animations.type_titles.tsifrovoy_schyotchik"),
    "reveal": ("animations.type_titles.plavnoe_poyavlenie"), "custom": ("animations.type_titles.svoi_kadry"),
}
SPEED_TITLES = {"slow": ("animations.speed_titles.medlenno"), "normal": ("animations.speed_titles.obychno"), "fast": ("animations.speed_titles.bystro"),
                "turbo": ("animations.speed_titles.turbo")}
GLITCH = "#$%&@!?▒░▓█<>/\\*"
MATRIX = "01アイウエオカキクケコサシスセソﾊﾐﾋｰｳｼﾅﾓﾆｻﾜﾂｵﾘｱﾎﾃﾏｹﾒｴｶｷﾑﾕﾗｾﾈｽﾀﾇﾍ"
MAX_PARALLEL = 3
_active: dict[tuple[int, int], asyncio.Task] = {}
_sem = asyncio.Semaphore(MAX_PARALLEL)


# ---- frame generators (pure functions → easy to test) -------------------------------------------------------------
def _cuts(n: int, budget: int) -> list[int]:
    budget = max(1, min(budget, n))
    return sorted({max(1, round(n * (i + 1) / budget)) for i in range(budget)})


def frames_for(kind: str, text: str, budget: int, *, rng: random.Random | None = None, custom: list[str] | None = None) -> list[str]:
    """Return the frames (HTML-safe) ending with the clean text."""
    rng = rng or random.Random()
    g = graphemes(text)
    n = len(g)
    safe = esc(text)
    budget = max(3, budget)
    out: list[str] = []
    if kind in ("typewriter", "fast"):
        b = budget if kind == "typewriter" else max(3, budget // 2)
        out = [esc("".join(g[:c])) + "▌" for c in _cuts(n, b)[:-1]]
    elif kind == "reverse":
        out = ["…" + esc("".join(g[n - c:])) for c in _cuts(n, budget)[:-1]]
    elif kind == "wave":
        step = max(1, n // max(1, budget - 1))
        for start in range(0, n, step):
            out.append(esc("".join(g[:start])) + "<b><u>" + esc("".join(g[start:start + 3])) + "</u></b>" + esc("".join(g[start + 3:])))
            if len(out) >= budget - 1:
                break
    elif kind == "glitch":
        for i in range(budget - 1):
            ratio = 0.6 * (1 - i / max(1, budget - 1))
            out.append(esc("".join(rng.choice(GLITCH) if ch.strip() and rng.random() < ratio else ch for ch in g)))
    elif kind == "matrix":
        for c in _cuts(n, budget)[:-1]:
            out.append("<code>" + esc("".join(g[:c]) + "".join(rng.choice(MATRIX) if ch.strip() else ch for ch in g[c:])) + "</code>")
    elif kind == "dots":
        for i in range(min(budget - 1, 9)):
            out.append(safe + " " + "." * (i % 3 + 1))
    elif kind == "progress":
        steps = min(budget - 1, 10)
        for i in range(steps + 1):
            pct = int(100 * i / steps)
            filled = round(10 * i / steps)
            out.append(f"{safe}\n{'▰' * filled}{'▱' * (10 - filled)} {pct}%")
    elif kind == "countdown":
        nums = ["5️⃣", "4️⃣", "3️⃣", "2️⃣", "1️⃣"][-min(5, budget - 1):]
        out = nums + ["🚀"]
    elif kind == "pulse":
        beats = ["💗", "💖", "💓", "💞", "💕", "💘"]
        out = [f"{beats[i % len(beats)]} {safe} {beats[i % len(beats)]}" for i in range(min(budget - 1, 8))]
    elif kind == "heart":
        hearts = ["🤍", "❤️", "🧡", "💛", "💚", "💙", "💜", "🖤"]
        out = ["".join(hearts[(i + j) % len(hearts)] for j in range(5)) + "\n" + safe for i in range(min(budget - 1, 8))]
    elif kind == "slide":
        pad = min(budget - 1, 8)
        out = ["⠀" * (pad - i) * 2 + safe for i in range(pad)]
    elif kind == "rainbow":
        cols = ["🟥", "🟧", "🟨", "🟩", "🟦", "🟪"]
        out = ["".join(cols[(i + j) % 6] for j in range(6)) + "\n" + safe for i in range(min(budget - 1, 8))]
    elif kind == "counter":
        target = int(text) if text.strip().isdigit() and len(text.strip()) <= 9 else 100
        steps = min(budget - 1, 10)
        out = [f"<code>{int(target * i / steps):0{max(3, len(str(target)))}d}</code>" + ("" if text.strip().isdigit() else "%") for i in range(steps + 1)]
    elif kind == "reveal":
        order = list(range(n))
        rng.shuffle(order)
        shown: set[int] = set()
        for c in _cuts(n, budget)[:-1]:
            shown.update(order[:c])
            out.append(esc("".join(ch if (i in shown or not ch.strip()) else "•" for i, ch in enumerate(g))))
    elif kind == "custom":
        out = [esc(f) for f in (custom or []) if f.strip()][: max(1, budget - 1)]
    # drop consecutive duplicates (Telegram rejects "message is not modified")
    dedup: list[str] = []
    for f in out:
        if f and (not dedup or dedup[-1] != f) and f != safe:
            dedup.append(f)
    return dedup + [safe]


def parse_args(raw: str, defaults: dict[str, Any]) -> tuple[str, str, str, list[str]]:
    """``.a [type] [speed] text`` → (kind, speed, text, custom frames)."""
    words = raw.split(" ")
    kind, speed = defaults.get("anim_type", "typewriter"), defaults.get("anim_speed", "fast")
    while words:
        w = words[0].lower()
        if w in ANIM_TYPES or w in TYPE_ALIASES:
            kind = TYPE_ALIASES.get(w, w)
        elif w in SPEED_ALIASES:
            speed = SPEED_ALIASES[w]
        else:
            break
        words.pop(0)
    text = " ".join(words).strip()
    custom = [x.strip() for x in text.split("|")] if kind == "custom" else []
    if kind == "custom" and custom:
        text = custom[-1]
    return kind, speed, text, custom


async def play(app: "AppContext", *, chat_id: int, message_id: int, bc_id: str | None, frames: list[str], interval: float,
               owner_id: int, job_id: int | None = None) -> str:
    """Edit the message frame by frame. Returns done | cancelled | rate_limited | failed."""
    status = "done"
    async with _sem:
        try:
            for f in frames[:-1]:
                res = await app.sender.edit_text(chat_id, message_id, f, bc_id=bc_id, retries=0)
                if not res.ok:
                    status = "rate_limited" if "flood" in (res.error or "").lower() else "failed"
                    break
                await asyncio.sleep(interval)
        except asyncio.CancelledError:
            status = "cancelled"
        finally:
            await app.sender.edit_text(chat_id, message_id, frames[-1], bc_id=bc_id, retries=1)
            if job_id:
                await app.db.execute("UPDATE animation_jobs SET status=?, finished_at=? WHERE id=?", (status, int(time.time()), job_id))
    return status


async def run_animation(app: "AppContext", *, owner_id: int, chat_id: int, message_id: int, bc_id: str | None, kind: str,
                        speed: str, text: str, custom: list[str] | None = None, repeats: int = 1) -> asyncio.Task:
    interval, budget = SPEEDS.get(speed, SPEEDS["fast"])
    frames = frames_for(kind, text, budget, custom=custom)
    if repeats > 1 and kind in ("dots", "pulse", "heart", "rainbow", "wave", "glitch"):
        loop = frames[:-1]
        frames = (loop * min(repeats, 3))[: budget * 2] + [frames[-1]]
    job_id = await app.db.execute(
        "INSERT INTO animation_jobs(owner_id, connection_id, chat_id, message_id, kind, speed, frames, status, created_at) "
        "VALUES (?,?,?,?,?,?,?,'running',?)", (owner_id, bc_id, chat_id, message_id, kind, speed, len(frames), int(time.time())))
    key = (owner_id, chat_id)
    old = _active.pop(key, None)
    if old and not old.done():
        old.cancel()
    task = asyncio.create_task(play(app, chat_id=chat_id, message_id=message_id, bc_id=bc_id, frames=frames, interval=interval,
                                    owner_id=owner_id, job_id=job_id))
    _active[key] = task
    task.add_done_callback(lambda t, k=key: _active.pop(k, None) if _active.get(k) is t else None)
    return task


def stop_animation(owner_id: int, chat_id: int) -> bool:
    task = _active.pop((owner_id, chat_id), None)
    if task and not task.done():
        task.cancel()
        return True
    return False


# ---- command ---------------------------------------------------------------------------------------------------------
@registry.command("a", "system", aliases=["анимация", "anim", "animatsiya"],
                  rights=["can_reply"], rate=(6, 60))
async def cmd_a(ctx: CommandContext) -> None:
    app = ctx.app
    if ctx.parsed.first in ("stop", "стоп", "cancel"):
        stopped = stop_animation(ctx.user_id, ctx.chat_id)
        await ctx.cleanup_command(fallback_text="⏹")
        if not stopped:
            await app.sender.send_text(ctx.user_id, ctx.t("animations.aktivnoy_animatsii_etom_chate_net"))
        return
    if not ctx.raw.strip():
        await send_studio(app, ctx.user_id)
        await ctx.cleanup_command(fallback_text="🎞")
        return
    kind, speed, text, custom = parse_args(ctx.raw.strip(), ctx.settings)
    if not text or len(text) > 600:
        raise UsageError(ctx.t("animations.nuzhen_tekst_600_simvolov"))
    if kind == "custom" and len(custom) < 2:
        raise UsageError(ctx.t("animations.custom_ukazhite_kadry_cherez_posledniy"))
    if ctx.source == "sandbox":
        ctx.outputs.append({"type": "frames", "text": " ⟶ ".join(frames_for(kind, text, SPEEDS[speed][1], custom=custom))})
        return
    if ctx.message is None:
        raise CommandError("no message")
    if ctx.is_business:
        mid, chat_id, bc = ctx.message.message_id, ctx.chat_id, ctx.bc_id
    else:  # in the bot DM the bot animates its own message
        res = await app.sender.send_text(ctx.user_id, "…")
        if not res.ok:
            raise CommandError(ctx.t("animations.udalos_nachat_animatsiyu"))
        mid, chat_id, bc = res.message_id, ctx.user_id, None
    ctx._edited_in_place = True
    await run_animation(app, owner_id=ctx.user_id, chat_id=chat_id, message_id=mid, bc_id=bc, kind=kind, speed=speed, text=text,
                        custom=custom, repeats=int(ctx.settings.get("anim_repeats", 1)))


# ---- Animation Studio (bot DM) ------------------------------------------------------------------------------------------
def studio(lang: str, s: dict[str, Any]) -> tuple[str, Any]:
    t = lambda key, **kw: tr(lang, key, **kw)  # noqa: E731
    text = "\n".join([t("animations.studiya_animatsiy"),
                      t("animations.tip_umolchaniyu_skorost_povtory",
                        k=tr(lang, TYPE_TITLES[s["anim_type"]]), s=tr(lang, SPEED_TITLES[s["anim_speed"]]), r=s["anim_repeats"]),
                      "", t("animations.chate_tekst_glitch_tekst_ostanovit", p=s["prefix"])])
    types = [(("✅ " if k == s["anim_type"] else "") + tr(lang, TYPE_TITLES[k]), f"an:t:{k}") for k in ANIM_TYPES]
    rows = [types[i:i + 2] for i in range(0, len(types), 2)]
    rows.append([(("✅ " if k == s["anim_speed"] else "") + tr(lang, SPEED_TITLES[k]), f"an:s:{k}") for k in SPEEDS])
    rows.append([(("✅ " if r == s["anim_repeats"] else "") + f"🔁 {r}", f"an:r:{r}") for r in (1, 2, 3)])
    rows.append([(t("animations.predprosmotr"), "an:preview")])
    rows.append([(t("animations.menyu"), "m:home")])
    return text, kb(rows)


async def send_studio(app: "AppContext", owner_id: int) -> None:
    s = await app.settings.all(owner_id)
    text, markup = studio(s["lang"], s)
    await app.sender.send_text(owner_id, text, markup=markup)


@router.callback_query(F.data.startswith("an:"))
async def cb_studio(cb: CallbackQuery, app: Any) -> None:
    uid = cb.from_user.id
    if cb.message is None or cb.message.chat.id != uid:
        await cb.answer()
        return
    parts = (cb.data or "").split(":")
    s = await app.settings.all(uid)
    if len(parts) >= 3 and parts[1] == "t" and parts[2] in ANIM_TYPES:
        await app.settings.set(uid, "anim_type", parts[2])
    elif len(parts) >= 3 and parts[1] == "s" and parts[2] in SPEEDS:
        await app.settings.set(uid, "anim_speed", parts[2])
    elif len(parts) >= 3 and parts[1] == "r" and parts[2] in ("1", "2", "3"):
        await app.settings.set(uid, "anim_repeats", int(parts[2]))
    elif len(parts) >= 2 and parts[1] == "preview":
        await cb.answer("▶️")
        s = await app.settings.all(uid)
        demo = tr(s["lang"], "animations.chat_helper_animatsiya")
        if s["anim_type"] == "counter":
            demo = "2026"
        res = await app.sender.send_text(uid, "…")
        if res.ok:
            await run_animation(app, owner_id=uid, chat_id=uid, message_id=res.message_id, bc_id=None, kind=s["anim_type"],
                                speed=s["anim_speed"], text=demo, custom=["🎬", "🎞", demo] if s["anim_type"] == "custom" else None,
                                repeats=s["anim_repeats"])
        return
    s = await app.settings.all(uid)
    text, markup = studio(s["lang"], s)
    await cb.answer("✅")
    try:
        await cb.message.edit_text(text, reply_markup=markup)
    except Exception:  # pragma: no cover - "not modified"
        pass


def frames_preview(kind: str, text: str) -> list[str]:
    return frames_for(kind, text, SPEEDS["fast"][1], rng=random.Random(7))

