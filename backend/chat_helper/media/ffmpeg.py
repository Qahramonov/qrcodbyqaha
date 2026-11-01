"""Safe FFmpeg/FFprobe runner: argument lists only (no shell), timeouts, cancellation, thread limits."""
from __future__ import annotations

import asyncio
import json
import logging
import shutil
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


class MediaError(Exception):
    """User-facing media processing error."""


class Cancelled(MediaError):
    pass


class FFmpeg:
    def __init__(self, ffmpeg: str = "ffmpeg", ffprobe: str = "ffprobe", timeout: int = 120, threads: int = 2) -> None:
        self.ffmpeg = ffmpeg
        self.ffprobe = ffprobe
        self.timeout = timeout
        self.threads = threads
        self.running: dict[int, asyncio.subprocess.Process] = {}

    def available(self) -> bool:
        return shutil.which(self.ffmpeg) is not None and shutil.which(self.ffprobe) is not None

    async def run(self, args: list[str], *, timeout: int | None = None, job_id: int | None = None,
                  cancel: asyncio.Event | None = None) -> None:
        cmd = [self.ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-y", *args]
        if "-threads" not in args:
            cmd[1:1] = ["-threads", str(self.threads)]
        proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE)
        if job_id is not None:
            self.running[job_id] = proc
        try:
            comm = asyncio.ensure_future(proc.communicate())
            waiters = [comm]
            cancel_task = None
            if cancel is not None:
                cancel_task = asyncio.ensure_future(cancel.wait())
                waiters.append(cancel_task)
            done, _ = await asyncio.wait(waiters, timeout=timeout or self.timeout, return_when=asyncio.FIRST_COMPLETED)
            if comm not in done:
                proc.kill()
                await proc.wait()
                comm.cancel()
                if cancel is not None and cancel.is_set():
                    raise Cancelled("cancelled")
                raise MediaError("timeout")
            if cancel_task:
                cancel_task.cancel()
            _, err = comm.result()
            if proc.returncode != 0:
                msg = (err or b"").decode(errors="ignore").strip().splitlines()
                log.info("ffmpeg failed rc=%s: %s", proc.returncode, (msg[-1] if msg else "")[:300])
                raise MediaError("ffmpeg_failed: " + (msg[-1][:200] if msg else "unknown error"))
        finally:
            if job_id is not None:
                self.running.pop(job_id, None)
            if proc.returncode is None:
                proc.kill()

    async def probe(self, path: Path) -> dict[str, Any]:
        proc = await asyncio.create_subprocess_exec(self.ffprobe, "-v", "error", "-print_format", "json", "-show_format",
                                                    "-show_streams", str(path), stdout=asyncio.subprocess.PIPE,
                                                    stderr=asyncio.subprocess.PIPE)
        try:
            out, _ = await asyncio.wait_for(proc.communicate(), timeout=30)
        except asyncio.TimeoutError:
            proc.kill()
            raise MediaError("probe timeout") from None
        if proc.returncode != 0:
            raise MediaError("cannot read media file")
        data = json.loads(out or b"{}")
        streams = data.get("streams") or []
        fmt = data.get("format") or {}
        v = next((s for s in streams if s.get("codec_type") == "video"), None)
        a = next((s for s in streams if s.get("codec_type") == "audio"), None)
        try:
            duration = float(fmt.get("duration") or (v or a or {}).get("duration") or 0)
        except ValueError:
            duration = 0.0
        return {"duration": duration, "has_audio": a is not None, "has_video": v is not None and v.get("disposition", {}).get("attached_pic") != 1,
                "width": int((v or {}).get("width") or 0), "height": int((v or {}).get("height") or 0),
                "vcodec": (v or {}).get("codec_name"), "acodec": (a or {}).get("codec_name"),
                "sample_rate": int((a or {}).get("sample_rate") or 0), "channels": int((a or {}).get("channels") or 0),
                "bitrate": int(fmt.get("bit_rate") or 0), "size": int(fmt.get("size") or 0), "format": fmt.get("format_name")}

    def kill(self, job_id: int) -> bool:
        proc = self.running.get(job_id)
        if proc and proc.returncode is None:
            proc.kill()
            return True
        return False


def atempo_chain(factor: float) -> str:
    """Build an atempo chain; each stage must stay within [0.5, 2.0] for compatibility with old FFmpeg builds."""
    if factor <= 0:
        raise MediaError("invalid speed")
    stages = []
    f = factor
    while f > 2.0:
        stages.append(2.0)
        f /= 2.0
    while f < 0.5:
        stages.append(0.5)
        f /= 0.5
    stages.append(f)
    return ",".join(f"atempo={s:.6f}" for s in stages)


def volume_gain_db(level: float) -> float:
    """.ld scale: 0 = unchanged, each step = +0.3 dB, 25 (default) = +7.5 dB (×2.37 amplitude), 100 = +30 dB (×31.6)."""
    level = max(0.0, min(100.0, float(level)))
    return round(level * 0.3, 2)
