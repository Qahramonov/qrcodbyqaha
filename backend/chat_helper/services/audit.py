"""Audit log, metrics counters and notification center."""
from __future__ import annotations

import logging
import time
from typing import Any

from ..core.timeutil import today
from ..database.db import Database, dumps, loads

log = logging.getLogger(__name__)


class AuditService:
    def __init__(self, db: Database) -> None:
        self.db = db

    async def log(self, action: str, actor_id: int | None = None, actor_type: str = "user",
                  target_type: str | None = None, target_id: Any = None, ip: str | None = None,
                  **details: Any) -> None:
        try:
            await self.db.execute(
                "INSERT INTO audit_logs(actor_id, actor_type, action, target_type, target_id, details_json, ip, created_at) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (actor_id, actor_type, action, target_type, None if target_id is None else str(target_id),
                 dumps(details), ip, int(time.time())))
        except Exception:  # pragma: no cover
            log.exception("audit write failed")

    async def query(self, actor_id: int | None = None, target_type: str | None = None, target_id: Any = None,
                    action: str | None = None, limit: int = 100, before_id: int | None = None) -> list[dict[str, Any]]:
        where, params = ["1=1"], []
        if actor_id is not None:
            where.append("actor_id=?")
            params.append(actor_id)
        if target_type:
            where.append("target_type=?")
            params.append(target_type)
        if target_id is not None:
            where.append("target_id=?")
            params.append(str(target_id))
        if action:
            where.append("action LIKE ?")
            params.append(action + "%")
        if before_id:
            where.append("id < ?")
            params.append(before_id)
        rows = await self.db.fetchall(f"SELECT * FROM audit_logs WHERE {' AND '.join(where)} ORDER BY id DESC LIMIT ?",
                                      params + [max(1, min(limit, 500))])
        for r in rows:
            r["details"] = loads(r.pop("details_json"), {})
        return rows


class MetricsService:
    """Daily counters. user_id=0 holds global aggregates."""

    def __init__(self, db: Database) -> None:
        self.db = db

    async def incr(self, metric: str, user_id: int | None = None, value: float = 1.0) -> None:
        d = today()
        rows = [(d, 0, metric, value)]
        if user_id:
            rows.append((d, int(user_id), metric, value))
        try:
            async with self.db.transaction() as tx:
                for r in rows:
                    await tx.execute(
                        "INSERT INTO daily_metrics(day, user_id, metric, value) VALUES (?,?,?,?) "
                        "ON CONFLICT(day, user_id, metric) DO UPDATE SET value = value + excluded.value", r)
        except Exception:  # pragma: no cover
            log.exception("metric write failed")

    async def series(self, metric: str, days: int = 30, user_id: int = 0, end_day: str | None = None) -> list[dict[str, Any]]:
        import datetime as dt
        end = dt.date.fromisoformat(end_day) if end_day else dt.datetime.now(dt.timezone.utc).date()
        start = end - dt.timedelta(days=days - 1)
        rows = await self.db.fetchall(
            "SELECT day, value FROM daily_metrics WHERE metric=? AND user_id=? AND day BETWEEN ? AND ? ORDER BY day",
            (metric, user_id, start.isoformat(), end.isoformat()))
        by_day = {r["day"]: r["value"] for r in rows}
        out = []
        for i in range(days):
            d = (start + dt.timedelta(days=i)).isoformat()
            out.append({"day": d, "value": by_day.get(d, 0)})
        return out

    async def total(self, metric: str, user_id: int = 0, since_day: str | None = None) -> float:
        if since_day:
            return float(await self.db.fetchval("SELECT SUM(value) FROM daily_metrics WHERE metric=? AND user_id=? AND day>=?",
                                                (metric, user_id, since_day), 0))
        return float(await self.db.fetchval("SELECT SUM(value) FROM daily_metrics WHERE metric=? AND user_id=?",
                                            (metric, user_id), 0))

    async def breakdown(self, prefix: str, days: int = 30, user_id: int = 0) -> dict[str, float]:
        import datetime as dt
        since = (dt.datetime.now(dt.timezone.utc).date() - dt.timedelta(days=days - 1)).isoformat()
        rows = await self.db.fetchall(
            "SELECT metric, SUM(value) AS v FROM daily_metrics WHERE metric LIKE ? AND user_id=? AND day>=? GROUP BY metric",
            (prefix + "%", user_id, since))
        return {r["metric"][len(prefix):]: r["v"] for r in rows}


class NotificationService:
    """Notification center: stored in DB, optionally delivered to the owner's private chat with the bot."""

    def __init__(self, db: Database, events: Any) -> None:
        self.db = db
        self.events = events
        self.sender = None  # set later: async callable(user_id, text) -> None

    async def notify(self, user_id: int, kind: str, title: str, body: str = "", level: str = "info",
                     push: bool = False) -> int:
        nid = await self.db.execute(
            "INSERT INTO notification_events(user_id, level, kind, title, body, created_at) VALUES (?,?,?,?,?,?)",
            (user_id, level, kind, title[:200], body[:2000], int(time.time())))
        self.events.emit("notification", user_id=user_id, level=level, kind=kind, title=title)
        if push and self.sender is not None:
            try:
                await self.sender(user_id, f"<b>{_esc(title)}</b>\n{_esc(body)}" if body else f"<b>{_esc(title)}</b>")
            except Exception:  # pragma: no cover
                log.warning("notification push failed for %s", user_id)
        return nid

    async def list(self, user_id: int, unread_only: bool = False, limit: int = 100) -> list[dict[str, Any]]:
        sql = "SELECT * FROM notification_events WHERE user_id=?"
        if unread_only:
            sql += " AND read_at IS NULL"
        return await self.db.fetchall(sql + " ORDER BY id DESC LIMIT ?", (user_id, max(1, min(limit, 500))))

    async def mark_read(self, user_id: int, ids: list[int] | None = None) -> int:
        now = int(time.time())
        if ids:
            q = ",".join("?" * len(ids))
            return await self.db.rowcount(f"UPDATE notification_events SET read_at=? WHERE user_id=? AND id IN ({q}) "
                                          "AND read_at IS NULL", [now, user_id, *ids])
        return await self.db.rowcount("UPDATE notification_events SET read_at=? WHERE user_id=? AND read_at IS NULL",
                                      (now, user_id))

    async def unread_count(self, user_id: int) -> int:
        return int(await self.db.fetchval("SELECT COUNT(*) FROM notification_events WHERE user_id=? AND read_at IS NULL",
                                          (user_id,), 0))


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
