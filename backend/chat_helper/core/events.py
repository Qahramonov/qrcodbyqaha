"""In-process event bus: feeds the Live Monitor (APK polling) and the notification center."""
from __future__ import annotations

import asyncio
import collections
import logging
import time
from typing import Any, Awaitable, Callable

log = logging.getLogger(__name__)
Listener = Callable[[dict[str, Any]], Awaitable[None]]


class EventBus:
    def __init__(self, capacity: int = 1000) -> None:
        self._events: collections.deque[dict[str, Any]] = collections.deque(maxlen=capacity)
        self._seq = 0
        self._listeners: list[Listener] = []

    def subscribe(self, listener: Listener) -> None:
        self._listeners.append(listener)

    def emit(self, kind: str, /, user_id: int | None = None, level: str = "info", **data: Any) -> dict[str, Any]:
        self._seq += 1
        ev = {"id": self._seq, "ts": int(time.time()), "kind": kind, "user_id": user_id,
              "level": level, "data": data}
        self._events.append(ev)
        for lst in self._listeners:
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self._safe(lst, ev))
            except RuntimeError:
                pass
        return ev

    async def _safe(self, lst: Listener, ev: dict[str, Any]) -> None:
        try:
            await lst(ev)
        except Exception:  # pragma: no cover
            log.exception("event listener failed")

    def since(self, after_id: int = 0, user_id: int | None = None, is_admin: bool = False,
              limit: int = 200) -> list[dict[str, Any]]:
        out = []
        for ev in self._events:
            if ev["id"] <= after_id:
                continue
            if not is_admin and ev["user_id"] != user_id:
                continue
            out.append(ev)
        return out[-limit:]

    @property
    def last_id(self) -> int:
        return self._seq
