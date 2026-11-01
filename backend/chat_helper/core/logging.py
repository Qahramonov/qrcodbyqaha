"""Safe logging: secrets are redacted from every record, logs rotate, recent lines kept in RAM."""
from __future__ import annotations

import collections
import logging
import logging.handlers
import re
import time
from pathlib import Path
from typing import Any

# no \b before the digits: the token is usually glued to "bot" in URLs (…/bot123:ABC…/getMe)
_TOKEN_RE = re.compile(r"(?<![0-9])\d{6,12}:[A-Za-z0-9_-]{30,}(?![A-Za-z0-9_-])")
_KEY_RES = [
    re.compile(r"\bsk-[A-Za-z0-9_\-]{16,}"),
    re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{16,}"),
    re.compile(r"\bAIza[0-9A-Za-z_\-]{30,}"),
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._\-]{16,}"),
    re.compile(r"(?i)([?&]key=)[A-Za-z0-9_\-]{16,}"),
    re.compile(r"\bch[ar]_[A-Za-z0-9_\-]{20,}"),   # Chat helper access/refresh tokens
]


class Redactor:
    def __init__(self) -> None:
        self.values: list[str] = []

    def set_values(self, values: list[str]) -> None:
        self.values = sorted({v for v in values if v}, key=len, reverse=True)

    def __call__(self, text: str) -> str:
        if not text:
            return text
        for v in self.values:
            if v in text:
                text = text.replace(v, "***")
        text = _TOKEN_RE.sub("<bot-token>", text)
        for rx in _KEY_RES:
            if rx.groups:
                text = rx.sub(lambda m: m.group(1) + "***", text)
            else:
                text = rx.sub("***", text)
        return text


redact = Redactor()


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:  # pragma: no cover
            return True
        clean = redact(msg)
        if clean != msg or record.args:
            record.msg = clean
            record.args = None
        if record.exc_info and not record.exc_text:
            record.exc_text = redact(logging.Formatter().formatException(record.exc_info))
            record.exc_info = None
        elif record.exc_text:
            record.exc_text = redact(record.exc_text)
        return True


class RingBufferHandler(logging.Handler):
    """Keeps the most recent log lines in memory for the API / Live Monitor."""

    def __init__(self, capacity: int = 2000) -> None:
        super().__init__()
        self.buffer: collections.deque[dict[str, Any]] = collections.deque(maxlen=capacity)
        self._seq = 0

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._seq += 1
            self.buffer.append({
                "id": self._seq,
                "ts": int(record.created),
                "level": record.levelname,
                "logger": record.name,
                "message": redact(self.format(record))[:4000],
            })
        except Exception:  # pragma: no cover
            self.handleError(record)

    def query(self, level: str | None = None, q: str | None = None, limit: int = 200,
              after_id: int = 0) -> list[dict[str, Any]]:
        lvl = logging.getLevelName(level.upper()) if level else 0
        if not isinstance(lvl, int):
            lvl = 0
        out = []
        for item in reversed(self.buffer):
            if item["id"] <= after_id:
                break
            if lvl and logging.getLevelName(item["level"]) < lvl:
                continue
            if q and q.lower() not in item["message"].lower():
                continue
            out.append(item)
            if len(out) >= limit:
                break
        return out


ring_handler = RingBufferHandler()
_configured = False


def setup_logging(level: str = "INFO", logs_dir: Path | None = None, secrets: list[str] | None = None) -> None:
    global _configured
    redact.set_values(secrets or [])
    root = logging.getLogger()
    if _configured:
        root.setLevel(level.upper())
        return
    root.setLevel(level.upper())
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s", "%Y-%m-%d %H:%M:%S")
    flt = RedactingFilter()
    console = logging.StreamHandler()
    console.setFormatter(fmt)
    console.addFilter(flt)
    root.addHandler(console)
    ring_handler.setFormatter(logging.Formatter("%(message)s"))
    ring_handler.addFilter(flt)
    root.addHandler(ring_handler)
    if logs_dir is not None:
        logs_dir.mkdir(parents=True, exist_ok=True)
        fh = logging.handlers.RotatingFileHandler(logs_dir / "chat_helper.log", maxBytes=2_000_000,
                                                  backupCount=5, encoding="utf-8")
        fh.setFormatter(fmt)
        fh.addFilter(flt)
        root.addHandler(fh)
    for noisy in ("aiogram.event", "httpx", "httpcore", "uvicorn.access", "aiosqlite"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    _configured = True


def uptime_start() -> float:
    return _START


_START = time.time()
