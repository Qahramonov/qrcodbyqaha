"""Media Studio manager and Games manager endpoints."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from starlette.background import BackgroundTask

from ...games.games import GAME_CLASSES
from ...media.ffmpeg import MediaError
from ...media.image import FRAME_STYLES
from ..deps import APIError, Principal, admin, get_app, principal, super_admin

router = APIRouter()

DEMO_EFFECTS = ["reverse", "speed", "volume", "normalize", "circle", "gif", "blur", "pixel", "bw", "sepia", "mirror", "rotate", "noise",
                "sharpen", "brightness", "contrast", "meme", "watermark", "sticker", *[f"ramka:{s}" for s in FRAME_STYLES]]


@router.get("/media/settings", tags=["media"])
async def media_settings(p: Principal = Depends(principal), app: Any = Depends(get_app)) -> dict[str, Any]:
    c = app.config
    s = await app.settings.all(p.user_id)
    return {"enabled": s["media_enabled"], "delete_commands": s["delete_commands"], "ffmpeg": app.health.ffmpeg_ok,
            "ffmpeg_version": app.health.ffmpeg_version, "max_input_mb": c.media_max_input_mb, "max_duration": c.media_max_duration,
            "max_reverse_video": c.media_max_reverse_video, "timeout": c.media_timeout, "concurrency": c.media_concurrency,
            "daily_limit": await app.subs.limit(p.user_id, "media_jobs_day"), "used_today": await app.quotas.used(f"media:{p.user_id}"),
            "paused_global": app.runtime.is_module_paused("media"), "demo_effects": DEMO_EFFECTS, "frames": list(FRAME_STYLES)}


class MediaSystemPatch(BaseModel):
    max_input_mb: int | None = Field(default=None, ge=1, le=20)
    max_duration: int | None = Field(default=None, ge=5, le=1800)
    max_reverse_video: int | None = Field(default=None, ge=5, le=180)
    timeout: int | None = Field(default=None, ge=10, le=900)


@router.patch("/media/settings", tags=["media"])
async def media_system(body: MediaSystemPatch, p: Principal = Depends(super_admin), app: Any = Depends(get_app)) -> dict[str, Any]:
    c = app.config
    if body.max_input_mb is not None:
        c.media_max_input_mb = body.max_input_mb
    if body.max_duration is not None:
        c.media_max_duration = body.max_duration
    if body.max_reverse_video is not None:
        c.media_max_reverse_video = app.media.av.max_reverse = body.max_reverse_video
    if body.timeout is not None:
        c.media_timeout = app.media.ff.timeout = body.timeout
    app.runtime.extra["media"] = body.model_dump(exclude_none=True)
    await app.runtime.save()
    await app.audit.log("media.settings", actor_id=p.user_id, actor_type="app", **body.model_dump(exclude_none=True))
    return {"ok": True}


@router.get("/media/stats", tags=["media"])
async def media_stats(scope: str = "self", p: Principal = Depends(principal), app: Any = Depends(get_app)) -> dict[str, Any]:
    glob = scope == "global" and p.is_admin
    return await app.media.stats(None if glob else p.user_id)


@router.get("/media/jobs", tags=["media"])
async def media_jobs(status: str | None = None, scope: str = "self", p: Principal = Depends(principal), app: Any = Depends(get_app)) -> dict[str, Any]:
    glob = scope == "global" and p.is_admin
    return {"items": await app.media.jobs(None if glob else p.user_id, 100, status), "queue": app.media.queue.status()}


@router.post("/media/jobs/{job_id}/cancel", tags=["media"])
async def media_cancel(job_id: int, p: Principal = Depends(principal), app: Any = Depends(get_app)) -> dict[str, Any]:
    ok = await app.media.queue.cancel(job_id, None if p.is_admin else p.user_id)
    if not ok:
        raise APIError(404, "not_found", "Active job not found")
    return {"ok": True}


@router.post("/media/cleanup", tags=["media"])
async def media_cleanup(p: Principal = Depends(admin), app: Any = Depends(get_app)) -> dict[str, Any]:
    removed, freed = app.media.files.cleanup(max_age_sec=0 if not app.media.queue.jobs else 1800)
    await app.audit.log("media.cleanup", actor_id=p.user_id, actor_type="app", removed=removed)
    return {"removed": removed, "freed_bytes": freed}


@router.get("/media/demo/{effect}", tags=["media"])
async def media_demo(effect: str, arg: str | None = None, p: Principal = Depends(principal), app: Any = Depends(get_app)):
    if effect not in DEMO_EFFECTS and effect.replace(":", "") not in [e.replace(":", "") for e in DEMO_EFFECTS]:
        raise APIError(404, "unknown_effect", "Unknown effect")
    ok, retry = app.limiter.check(f"demo:{p.user_id}", 10, 60)
    if not ok:
        raise APIError(429, "rate_limited", "Too many demo requests", {"Retry-After": str(retry)})
    try:
        path, mime = await app.media.demo(effect, arg)
    except MediaError as e:
        raise APIError(503, "media_unavailable", str(e)) from None
    return FileResponse(path, media_type=mime, filename=path.name, background=BackgroundTask(app.media.files.discard, path))


# ---- games -----------------------------------------------------------------------------------

GAME_INFO = {
    "duel": "Reaction duel", "revo": "Virtual roulette", "ttt": "Tic-tac-toe", "rps": "Rock-paper-scissors", "quiz": "Quiz",
    "guess": "Guess the number", "mathgame": "Math race", "wordgame": "Word chain", "reaction": "Reaction test",
    "dice": "Telegram dice", "slot": "Slot machine", "coin": "Coin flip", "rd": "Random", "challenge": "Random challenge",
}


@router.get("/games", tags=["games"])
async def games(p: Principal = Depends(principal), app: Any = Depends(get_app)) -> dict[str, Any]:
    s = await app.settings.all(p.user_id)
    disabled = set(s.get("disabled_commands") or [])
    items = [{"id": g, "title": t, "enabled": g not in disabled, "session_game": g in {c.id for c in GAME_CLASSES}} for g, t in GAME_INFO.items()]
    return {"enabled": s["games_enabled"], "items": items,
            "settings": {k: s[k] for k in ("duel_min_delay", "duel_max_delay", "game_timeout_sec", "games_enabled")}}


class GameSettings(BaseModel):
    games_enabled: bool | None = None
    duel_min_delay: int | None = Field(default=None, ge=1, le=10)
    duel_max_delay: int | None = Field(default=None, ge=2, le=20)
    game_timeout_sec: int | None = Field(default=None, ge=30, le=900)


@router.patch("/games/settings", tags=["games"])
async def games_settings(body: GameSettings, p: Principal = Depends(principal), app: Any = Depends(get_app)) -> dict[str, Any]:
    vals = body.model_dump(exclude_none=True)
    if vals.get("duel_min_delay") and vals.get("duel_max_delay") and vals["duel_min_delay"] >= vals["duel_max_delay"]:
        raise APIError(422, "invalid_range", "min delay must be < max delay")
    await app.settings.update(p.user_id, vals)
    return {"ok": True}


@router.get("/games/sessions", tags=["games"])
async def game_sessions(scope: str = "self", p: Principal = Depends(principal), app: Any = Depends(get_app)) -> dict[str, Any]:
    glob = scope == "global" and p.is_admin
    return {"items": app.games.active(None if glob else p.user_id)}


@router.post("/games/sessions/{sid}/end", tags=["games"])
async def game_end(sid: str, p: Principal = Depends(principal), app: Any = Depends(get_app)) -> dict[str, Any]:
    if not await app.games.end(sid, None if p.is_admin else p.user_id):
        raise APIError(404, "not_found", "Session not found")
    return {"ok": True}


@router.get("/games/leaderboard", tags=["games"])
async def leaderboard(game: str | None = None, p: Principal = Depends(principal), app: Any = Depends(get_app)) -> dict[str, Any]:
    return {"items": await app.games.leaderboard(p.user_id, game, 50)}


@router.get("/games/history", tags=["games"])
async def game_history(p: Principal = Depends(principal), app: Any = Depends(get_app)) -> dict[str, Any]:
    rows = await app.games.history(p.user_id, 100)
    stats = await app.db.fetchall("SELECT game, COUNT(*) AS n, SUM(CASE WHEN winner_id=? THEN 1 ELSE 0 END) AS my_wins FROM game_results "
                                  "WHERE owner_id=? GROUP BY game", (p.user_id, p.user_id))
    return {"items": rows, "by_game": stats}


@router.delete("/games/history", tags=["games"])
async def clear_games(p: Principal = Depends(principal), app: Any = Depends(get_app)) -> dict[str, Any]:
    return {"deleted": await app.games.clear_history(p.user_id)}
