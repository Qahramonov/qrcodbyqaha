"""Media Studio service: job queue (progress, cancel, limits, timeouts), Telegram I/O, TTS, demo."""
from __future__ import annotations

import asyncio
import logging
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Awaitable, Callable

from ..database.db import dumps
from . import image as I
from .av import AV
from .ffmpeg import Cancelled, FFmpeg, MediaError
from .files import TempFiles

if TYPE_CHECKING:  # pragma: no cover
    from ..core.context import AppContext

log = logging.getLogger(__name__)
MAX_ACTIVE_PER_USER = 3


@dataclass
class Job:
    id: int
    user_id: int
    chat_id: int | None
    kind: str
    runner: Callable[["Job"], Awaitable[Any]]
    cancel: asyncio.Event = field(default_factory=asyncio.Event)
    status: str = "queued"
    progress: int = 0
    created: float = field(default_factory=time.time)
    started: float | None = None
    error: str | None = None
    result: Any = None
    done: asyncio.Event = field(default_factory=asyncio.Event)


class MediaQueue:
    def __init__(self, app: "AppContext", workers: int = 1, timeout: int = 300) -> None:
        self.app = app
        self.workers_n = workers
        self.timeout = timeout
        self.q: asyncio.Queue[Job] = asyncio.Queue()
        self.jobs: dict[int, Job] = {}
        self._workers: list[asyncio.Task] = []
        self.processed = 0
        self.failed = 0
        self.paused = False

    def start(self) -> None:
        self._workers = [w for w in self._workers if not w.done()]
        while len(self._workers) < self.workers_n:
            self._workers.append(asyncio.create_task(self._worker(len(self._workers)), name=f"media-worker-{len(self._workers)}"))

    async def stop(self) -> None:
        for j in list(self.jobs.values()):
            j.cancel.set()
        for w in self._workers:
            w.cancel()
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers = []

    async def restart(self) -> None:
        await self.stop()
        self.start()

    async def recover(self) -> int:
        return await self.app.db.rowcount("UPDATE media_jobs SET status='failed', error='interrupted by restart', finished_at=? "
                                          "WHERE status IN ('queued','running')", (int(time.time()),))

    def active_for(self, user_id: int) -> int:
        return sum(1 for j in self.jobs.values() if j.user_id == user_id and j.status in ("queued", "running"))

    async def submit(self, user_id: int, chat_id: int | None, kind: str, params: dict[str, Any],
                     runner: Callable[[Job], Awaitable[Any]], input_size: int = 0) -> Job:
        if self.paused or self.app.runtime.is_module_paused("media"):
            raise MediaError("media module is paused")
        if self.active_for(user_id) >= MAX_ACTIVE_PER_USER:
            raise MediaError("too many active jobs")
        jid = await self.app.db.execute(
            "INSERT INTO media_jobs(user_id, chat_id, kind, params_json, status, input_size, created_at) VALUES (?,?,?,?,?,?,?)",
            (user_id, chat_id, kind, dumps(params), "queued", input_size, int(time.time())))
        job = Job(jid, user_id, chat_id, kind, runner)
        self.jobs[jid] = job
        await self.q.put(job)
        self.app.events.emit("media_job", user_id=user_id, job_id=jid, kind=kind, status="queued")
        return job

    def position(self, job: Job) -> int:
        return sum(1 for j in self.jobs.values() if j.status == "queued" and j.created <= job.created)

    async def _set(self, job: Job, status: str, error: str | None = None, output_size: int | None = None) -> None:
        job.status = status
        now = int(time.time())
        if status == "running":
            await self.app.db.execute("UPDATE media_jobs SET status=?, started_at=?, progress=10 WHERE id=?", (status, now, job.id))
        else:
            await self.app.db.execute("UPDATE media_jobs SET status=?, error=?, output_size=COALESCE(?, output_size), finished_at=?, progress=? "
                                      "WHERE id=?", (status, error, output_size, now, 100 if status == "done" else job.progress, job.id))
        self.app.events.emit("media_job", user_id=job.user_id, job_id=job.id, kind=job.kind, status=status,
                             level="warning" if status == "failed" else "info")

    async def _worker(self, idx: int) -> None:
        while True:
            job = await self.q.get()
            try:
                if job.cancel.is_set():
                    await self._set(job, "cancelled")
                    continue
                job.started = time.time()
                await self._set(job, "running")
                try:
                    job.result = await asyncio.wait_for(job.runner(job), timeout=self.timeout)
                    await self._set(job, "done", output_size=(job.result or {}).get("size") if isinstance(job.result, dict) else None)
                    self.processed += 1
                    await self.app.metrics.incr("media_jobs", job.user_id)
                    await self.app.metrics.incr(f"media:{job.kind}")
                except Cancelled:
                    await self._set(job, "cancelled")
                except asyncio.TimeoutError:
                    self.failed += 1
                    job.error = "timeout"
                    await self._set(job, "failed", "timeout")
                except MediaError as e:
                    self.failed += 1
                    job.error = str(e)
                    await self._set(job, "failed", str(e)[:300])
                except Exception as e:  # isolation
                    self.failed += 1
                    job.error = f"{type(e).__name__}"
                    log.exception("media job %s crashed", job.id)
                    await self._set(job, "failed", job.error)
                    await self.app.metrics.incr("errors", job.user_id)
            finally:
                job.done.set()
                self.q.task_done()
                self.jobs.pop(job.id, None)

    async def cancel(self, job_id: int, user_id: int | None = None) -> bool:
        job = self.jobs.get(job_id)
        if job is None or (user_id is not None and job.user_id != user_id):
            if user_id is None:
                return await self.app.db.rowcount("UPDATE media_jobs SET status='cancelled' WHERE id=? AND status IN ('queued','running')",
                                                  (job_id,)) > 0
            return False
        job.cancel.set()
        self.app.media.ff.kill(job_id)
        if job.status == "queued":
            await self._set(job, "cancelled")
        return True

    def status(self) -> dict[str, Any]:
        return {"running": any(not w.done() for w in self._workers), "workers": self.workers_n,
                "queued": sum(1 for j in self.jobs.values() if j.status == "queued"),
                "active": sum(1 for j in self.jobs.values() if j.status == "running"),
                "processed": self.processed, "failed": self.failed, "paused": self.paused}


class MediaService:
    def __init__(self, app: "AppContext") -> None:
        self.app = app
        cfg = app.config
        self.ff = FFmpeg(cfg.ffmpeg_bin, cfg.ffprobe_bin, cfg.media_timeout)
        self.av = AV(self.ff, cfg.media_max_reverse_video)
        self.files = TempFiles(cfg.tmp_dir)
        self.queue = MediaQueue(app, cfg.media_concurrency, cfg.media_timeout + 60)
        self.font_path = cfg.media_font or None

    async def image_op(self, fn: Callable[..., Any], *args: Any, timeout: int = 60) -> Any:
        return await asyncio.wait_for(asyncio.to_thread(fn, *args), timeout=timeout)

    async def extract_audio_bytes(self, data: bytes) -> bytes:
        d = self.files.job_dir("stt")
        try:
            src = d / "in.mp4"
            src.write_bytes(data)
            out = await self.av.extract_audio(src, d)
            return out.read_bytes()
        finally:
            self.files.discard(d)

    async def tts(self, user_id: int, text: str, lang: str = "ru") -> Path:
        d = self.files.job_dir("tts")
        out = d / "voice.ogg"
        if self.app.ai.available("tts"):
            try:
                audio = await self.app.ai.tts(user_id, text)
                out.write_bytes(audio)
                return out
            except Exception as e:
                log.info("cloud TTS failed: %s", type(e).__name__)
        binary = shutil.which("espeak-ng") or shutil.which("espeak")
        if binary is None or not self.app.health.ffmpeg_ok:
            self.files.discard(d)
            raise RuntimeError("🔊 TTS: нужен ключ OpenAI или офлайн-движок (pkg install espeak) / OpenAI kaliti yoki espeak kerak.")
        wav = d / "tts.wav"
        voice = {"ru": "ru", "uz": "uz", "en": "en"}.get(lang, "ru")
        proc = await asyncio.create_subprocess_exec(binary, "-v", voice, "-w", str(wav), "--", text[:1000],
                                                    stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
        try:
            await asyncio.wait_for(proc.wait(), timeout=60)
        except asyncio.TimeoutError:
            proc.kill()
            raise RuntimeError("TTS timeout") from None
        if not wav.exists():
            raise RuntimeError("TTS failed")
        await self.ff.run(["-i", str(wav), "-c:a", "libopus", "-b:a", "48k", "-ac", "1", str(out)])
        return out

    async def demo(self, effect: str, arg: str | None = None) -> tuple[Path, str]:
        """Apply an effect to a synthetic sample (APK demo screen). Returns (path, mime)."""
        d = self.files.job_dir("demo")
        img_effects = {"blur": lambda im: I.blur(im, 6), "pixel": lambda im: I.pixelate(im, 14), "bw": I.bw, "sepia": I.sepia,
                       "mirror": I.mirror, "rotate": lambda im: I.rotate(im, 90), "noise": I.noise, "sharpen": I.sharpen,
                       "brightness": lambda im: I.brightness(im, 1.4), "contrast": lambda im: I.contrast(im, 1.5),
                       "meme": lambda im: I.meme(im, "Chat helper", "demo"), "watermark": lambda im: I.watermark(im, "© Chat helper"),
                       "sticker": I.sticker}
        if effect.startswith("ramka") or effect in I.FRAME_STYLES:
            style = arg or (effect.split(":")[1] if ":" in effect else effect if effect in I.FRAME_STYLES else "gold")
            im = await self.image_op(I.frame, I.demo_image(), style)
            return I.save_image(im, d, "demo"), "image/jpeg"
        if effect in img_effects:
            im = await self.image_op(img_effects[effect], I.demo_image())
            path = I.save_image(im, d, "demo")
            return path, "image/png" if path.suffix == ".png" else "image/jpeg"
        if not self.app.health.ffmpeg_ok:
            raise MediaError("ffmpeg not available")
        av_effects = {"reverse": ("voice", lambda s: self.av.reverse(s, "voice", d)),
                      "speed": ("voice", lambda s: self.av.speed(s, "voice", d, float(arg or 2))),
                      "volume": ("voice", lambda s: self.av.volume(s, "voice", d, float(arg or 25))),
                      "normalize": ("voice", lambda s: self.av.normalize(s, "voice", d)),
                      "circle": ("video", lambda s: self.av.to_circle(s, "video", d)),
                      "gif": ("video", lambda s: self.av.to_gif(s, "video", d))}
        if effect not in av_effects:
            raise MediaError("unknown effect")
        kind, op = av_effects[effect]
        src = await self.av.make_test_media(d, kind)
        out, _send, _extra = await op(src)
        return out, "audio/ogg" if out.suffix == ".ogg" else "video/mp4"

    async def stats(self, user_id: int | None = None, days: int = 30) -> dict[str, Any]:
        since = int(time.time()) - days * 86400
        cond = "" if user_id is None else " AND user_id=?"
        params: tuple = (since,) if user_id is None else (since, user_id)
        rows = await self.app.db.fetchall(f"SELECT kind, status, COUNT(*) AS n, AVG(COALESCE(finished_at,0)-COALESCE(started_at,0)) AS avg_sec "
                                          f"FROM media_jobs WHERE created_at > ?{cond} GROUP BY kind, status", params)
        return {"by_kind": rows, "queue": self.queue.status(), "tmp": self.files.usage(), "ffmpeg": self.app.health.ffmpeg_ok}

    async def jobs(self, user_id: int | None = None, limit: int = 50, status: str | None = None) -> list[dict[str, Any]]:
        where, params = ["1=1"], []
        if user_id is not None:
            where.append("user_id=?")
            params.append(user_id)
        if status:
            where.append("status=?")
            params.append(status)
        return await self.app.db.fetchall(f"SELECT * FROM media_jobs WHERE {' AND '.join(where)} ORDER BY id DESC LIMIT ?", params + [limit])
