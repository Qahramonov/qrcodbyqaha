"""Duplicate-update protection and auto-reply loop protection."""
from __future__ import annotations

import collections
import hashlib
import time
from typing import Any

from ..database.db import Database


class Deduplicator:
    """Two layers: in-memory LRU (fast) + SQLite (survives restarts / re-delivered updates)."""

    def __init__(self, db: Database | None = None, capacity: int = 20000) -> None:
        self.db = db
        self.capacity = capacity
        self._seen: collections.OrderedDict[str, float] = collections.OrderedDict()

    async def seen(self, key: str, persist: bool = True) -> bool:
        if key in self._seen:
            self._seen.move_to_end(key)
            return True
        self._seen[key] = time.time()
        if len(self._seen) > self.capacity:
            self._seen.popitem(last=False)
        if persist and self.db is not None:
            existed = await self.db.fetchval("SELECT 1 FROM processed_updates WHERE key=?", (key,))
            if existed:
                return True
            await self.db.execute("INSERT OR IGNORE INTO processed_updates(key, created_at) VALUES (?,?)",
                                  (key, int(time.time())))
        return False

    async def cleanup(self, max_age_sec: int = 3 * 86400) -> int:
        if self.db is None:
            return 0
        return await self.db.rowcount("DELETE FROM processed_updates WHERE created_at < ?",
                                      (int(time.time()) - max_age_sec,))


class LoopGuard:
    """Stops runaway auto-reply ping-pong (e.g. with another bot or an auto-responder)."""

    def __init__(self, max_replies: int = 6, window_sec: int = 600, repeat_threshold: int = 3) -> None:
        self.max_replies = max_replies
        self.window_sec = window_sec
        self.repeat_threshold = repeat_threshold
        self._replies: dict[tuple[int, int], collections.deque[float]] = {}
        self._incoming: dict[tuple[int, int], collections.deque[str]] = {}
        self._tripped: dict[tuple[int, int], float] = {}

    def note_incoming(self, user_id: int, chat_id: int, text: str | None) -> None:
        h = hashlib.sha1((text or "").strip().lower().encode()).hexdigest()[:12]
        dq = self._incoming.setdefault((user_id, chat_id), collections.deque(maxlen=6))
        dq.append(h)

    def allow(self, user_id: int, chat_id: int, sender_is_bot: bool = False) -> tuple[bool, str]:
        key = (user_id, chat_id)
        now = time.time()
        if sender_is_bot:
            return False, "counterpart_is_bot"
        tripped = self._tripped.get(key)
        if tripped and now - tripped < self.window_sec:
            return False, "loop_cooldown"
        dq = self._replies.setdefault(key, collections.deque())
        while dq and now - dq[0] > self.window_sec:
            dq.popleft()
        if len(dq) >= self.max_replies:
            self._tripped[key] = now
            return False, "too_many_auto_replies"
        inc = self._incoming.get(key)
        if inc and len(inc) >= self.repeat_threshold and len(set(list(inc)[-self.repeat_threshold:])) == 1:
            self._tripped[key] = now
            return False, "repeated_identical_messages"
        return True, ""

    def record_reply(self, user_id: int, chat_id: int) -> None:
        self._replies.setdefault((user_id, chat_id), collections.deque()).append(time.time())

    def reset(self, user_id: int, chat_id: int) -> None:
        key = (user_id, chat_id)
        self._replies.pop(key, None)
        self._incoming.pop(key, None)
        self._tripped.pop(key, None)

    def stats(self) -> dict[str, Any]:
        now = time.time()
        return {"tripped_chats": sum(1 for t in self._tripped.values() if now - t < self.window_sec)}
