"""Rate limiting: in-memory sliding windows for bursts + persistent daily quotas in SQLite."""
from __future__ import annotations

import collections
import time
from typing import Any

from ..core.timeutil import today
from ..database.db import Database


class SlidingWindowLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, collections.deque[float]] = {}
        self.blocked = 0

    def check(self, key: str, limit: int, window: float) -> tuple[bool, int]:
        """Returns (allowed, retry_after_seconds)."""
        now = time.monotonic()
        dq = self._hits.setdefault(key, collections.deque())
        while dq and now - dq[0] > window:
            dq.popleft()
        if len(dq) >= limit:
            self.blocked += 1
            return False, max(1, int(window - (now - dq[0])) + 1)
        dq.append(now)
        if len(self._hits) > 20000:
            for k in [k for k, v in self._hits.items() if not v or now - v[-1] > 3600][:5000]:
                self._hits.pop(k, None)
        return True, 0

    def reset(self, key: str) -> None:
        self._hits.pop(key, None)

    def snapshot(self, prefix: str = "") -> list[dict[str, Any]]:
        now = time.monotonic()
        return [{"key": k, "hits_last_min": sum(1 for t in v if now - t < 60)}
                for k, v in self._hits.items() if k.startswith(prefix) and v][:200]


class QuotaService:
    """Daily counters (e.g. AI requests/day, media jobs/day) stored in rate_limits table."""

    def __init__(self, db: Database) -> None:
        self.db = db

    async def used(self, key: str) -> int:
        row = await self.db.fetchone("SELECT window_start, count FROM rate_limits WHERE key=?", (f"{key}:{today()}",))
        return int(row["count"]) if row else 0

    async def consume(self, key: str, limit: int | None, amount: int = 1) -> tuple[bool, int]:
        """Atomically consume quota. limit None/<0 = unlimited. Returns (allowed, used_after)."""
        k = f"{key}:{today()}"
        async with self.db.transaction() as tx:
            cur = int(await tx.fetchval("SELECT count FROM rate_limits WHERE key=?", (k,), 0))
            if limit is not None and limit >= 0 and cur + amount > limit:
                return False, cur
            await tx.execute("INSERT INTO rate_limits(key, window_start, count) VALUES (?,?,?) "
                             "ON CONFLICT(key) DO UPDATE SET count=count+excluded.count", (k, int(time.time()), amount))
            return True, cur + amount

    async def cleanup(self, days: int = 3) -> int:
        cutoff = int(time.time()) - days * 86400
        return await self.db.rowcount("DELETE FROM rate_limits WHERE window_start < ?", (cutoff,))
