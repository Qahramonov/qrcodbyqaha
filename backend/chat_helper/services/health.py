"""Health checks & diagnostics: FFmpeg, disk, memory, CPU, DB, Telegram API, AI providers, workers."""
from __future__ import annotations

import asyncio
import os
import shutil
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover
    from ..core.context import AppContext


def _read(path: str) -> str:
    try:
        return Path(path).read_text()
    except OSError:
        return ""


def process_memory_mb() -> float | None:
    for line in _read("/proc/self/status").splitlines():
        if line.startswith("VmRSS:"):
            try:
                return round(int(line.split()[1]) / 1024, 1)
            except (IndexError, ValueError):
                return None
    try:
        import resource
        return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1)
    except Exception:  # pragma: no cover
        return None


def system_memory() -> dict[str, Any] | None:
    info = {}
    for line in _read("/proc/meminfo").splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0] in ("MemTotal:", "MemAvailable:"):
            info[parts[0][:-1]] = int(parts[1]) // 1024
    if "MemTotal" not in info:
        return None
    return {"total_mb": info["MemTotal"], "available_mb": info.get("MemAvailable")}


class CpuSampler:
    """Process CPU % from /proc/self/stat deltas (system-wide /proc/stat is blocked on modern Android)."""

    def __init__(self) -> None:
        self._last: tuple[float, float] | None = None

    def sample(self) -> float | None:
        try:
            t = os.times()
            proc = t.user + t.system
        except Exception:  # pragma: no cover
            return None
        now = time.monotonic()
        if self._last is None:
            self._last = (now, proc)
            return None
        dt = now - self._last[0]
        dp = proc - self._last[1]
        self._last = (now, proc)
        if dt <= 0:
            return None
        return round(100.0 * dp / dt / (os.cpu_count() or 1), 1)


class HealthService:
    def __init__(self, app: "AppContext") -> None:
        self.app = app
        self.ffmpeg_ok = False
        self.ffprobe_ok = False
        self.ffmpeg_version = ""
        self.cpu = CpuSampler()
        self.telegram_latency_ms: int | None = None
        self.telegram_ok: bool | None = None
        self.last_telegram_check = 0

    async def check_ffmpeg(self) -> dict[str, Any]:
        cfg = self.app.config
        self.ffmpeg_ok = shutil.which(cfg.ffmpeg_bin) is not None
        self.ffprobe_ok = shutil.which(cfg.ffprobe_bin) is not None
        if self.ffmpeg_ok:
            try:
                proc = await asyncio.create_subprocess_exec(cfg.ffmpeg_bin, "-hide_banner", "-version",
                                                            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
                out, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
                self.ffmpeg_version = out.decode(errors="ignore").splitlines()[0][:80] if out else ""
            except Exception:
                self.ffmpeg_ok = False
        return {"ok": self.ffmpeg_ok and self.ffprobe_ok, "ffmpeg": self.ffmpeg_ok, "ffprobe": self.ffprobe_ok,
                "version": self.ffmpeg_version}

    def disk(self) -> dict[str, Any]:
        try:
            du = shutil.disk_usage(self.app.config.data_dir)
            return {"ok": du.free > 200 * 1024 * 1024, "free_mb": du.free // 1048576, "total_mb": du.total // 1048576}
        except OSError:
            return {"ok": False, "free_mb": None, "total_mb": None}

    def tmp_usage_mb(self) -> float:
        total = 0
        for root, _dirs, files in os.walk(self.app.config.tmp_dir):
            for f in files:
                try:
                    total += os.path.getsize(os.path.join(root, f))
                except OSError:
                    pass
        return round(total / 1048576, 2)

    async def check_telegram(self) -> dict[str, Any]:
        if self.app.bot is None:
            return {"ok": False, "error": "bot not configured"}
        t0 = time.monotonic()
        try:
            me = await asyncio.wait_for(self.app.bot.get_me(), timeout=15)
            self.telegram_latency_ms = int((time.monotonic() - t0) * 1000)
            self.telegram_ok = True
            self.last_telegram_check = int(time.time())
            return {"ok": True, "latency_ms": self.telegram_latency_ms, "username": me.username,
                    "can_connect_to_business": getattr(me, "can_connect_to_business", None)}
        except Exception as e:
            self.telegram_ok = False
            return {"ok": False, "error": type(e).__name__}

    def resources(self) -> dict[str, Any]:
        return {"process_rss_mb": process_memory_mb(), "system_memory": system_memory(), "cpu_percent": self.cpu.sample(),
                "disk": self.disk(), "tmp_mb": self.tmp_usage_mb(), "uptime_sec": self.app.uptime,
                "pid": os.getpid(), "cpu_count": os.cpu_count()}

    async def full(self, include_remote: bool = True) -> dict[str, Any]:
        app = self.app
        checks: dict[str, Any] = {}
        checks["database"] = await app.db.integrity_check()
        checks["database"].update(await app.db.size_info())
        checks["ffmpeg"] = await self.check_ffmpeg()
        checks["disk"] = self.disk()
        if include_remote:
            checks["telegram"] = await self.check_telegram()
            checks["ai"] = await app.ai.check_providers() if app.ai else {"ok": False}
        checks["scheduler"] = {"ok": app.scheduler.running if app.scheduler else False}
        checks["media_queue"] = app.media.queue.status() if app.media else {"ok": False}
        if "ok" not in checks["media_queue"]:
            checks["media_queue"]["ok"] = checks["media_queue"].get("running", False)
        checks["polling"] = {"ok": app.polling_active}
        checks["emergency_stop"] = {"ok": not app.runtime.emergency_stop, "active": app.runtime.emergency_stop}
        overall = all(v.get("ok", True) for k, v in checks.items() if k not in ("ai",))
        return {"ok": overall, "checks": checks, "resources": self.resources(), "ts": int(time.time())}
