"""Scheduler: persistent one-shot/recurring tasks (SQLite) + periodic maintenance jobs.

Tasks survive restarts. Each handler is isolated: a failing job never stops the loop."""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Awaitable, Callable

from ..database.db import Database, dumps, loads

log = logging.getLogger(__name__)
TaskHandler = Callable[[dict[str, Any]], Awaitable[None]]


class Scheduler:
    def __init__(self, db: Database, tick: float = 5.0) -> None:
        self.db = db
        self.tick = tick
        self.handlers: dict[str, TaskHandler] = {}
        self.periodic: list[dict[str, Any]] = []
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()
        self.last_tick_at = 0.0
        self.runs = 0
        self.failures = 0

    def register(self, kind: str, handler: TaskHandler) -> None:
        self.handlers[kind] = handler

    def every(self, seconds: int, name: str, fn: Callable[[], Awaitable[Any]], initial_delay: int = 10) -> None:
        self.periodic.append({"name": name, "interval": seconds, "fn": fn, "next": time.time() + initial_delay,
                              "last_ok": None, "last_error": None, "runs": 0})

    async def add(self, user_id: int, kind: str, payload: dict[str, Any], run_at: int, *, repeat_sec: int | None = None,
                  dedup_key: str | None = None) -> int:
        now = int(time.time())
        if dedup_key:
            await self.db.execute("DELETE FROM scheduled_tasks WHERE dedup_key=?", (dedup_key,))
        return await self.db.execute(
            "INSERT INTO scheduled_tasks(user_id, kind, payload_json, run_at, repeat_sec, status, dedup_key, created_at) "
            "VALUES (?,?,?,?,?,'pending',?,?)", (user_id, kind, dumps(payload), int(run_at), repeat_sec, dedup_key, now))

    async def cancel(self, task_id: int, user_id: int | None = None) -> bool:
        if user_id is None:
            return await self.db.rowcount("UPDATE scheduled_tasks SET status='cancelled' WHERE id=? AND status='pending'", (task_id,)) > 0
        return await self.db.rowcount("UPDATE scheduled_tasks SET status='cancelled' WHERE id=? AND user_id=? AND status='pending'",
                                      (task_id, user_id)) > 0

    async def list(self, user_id: int | None = None, status: str = "pending", limit: int = 100) -> list[dict[str, Any]]:
        sql = "SELECT * FROM scheduled_tasks WHERE status=?"
        params: list[Any] = [status]
        if user_id is not None:
            sql += " AND user_id=?"
            params.append(user_id)
        rows = await self.db.fetchall(sql + " ORDER BY run_at LIMIT ?", params + [limit])
        for r in rows:
            r["payload"] = loads(r.pop("payload_json"), {})
        return rows

    async def run_due(self) -> int:
        now = int(time.time())
        rows = await self.db.fetchall("SELECT * FROM scheduled_tasks WHERE status='pending' AND run_at <= ? ORDER BY run_at LIMIT 50", (now,))
        for row in rows:
            row["payload"] = loads(row.pop("payload_json"), {})
            handler = self.handlers.get(row["kind"])
            # claim the task first (idempotency: never executed twice)
            claimed = await self.db.rowcount("UPDATE scheduled_tasks SET status='running', attempts=attempts+1 WHERE id=? AND status='pending'",
                                             (row["id"],))
            if not claimed:
                continue
            if handler is None:
                await self.db.execute("UPDATE scheduled_tasks SET status='failed', last_error='no handler' WHERE id=?", (row["id"],))
                continue
            try:
                await asyncio.wait_for(handler(row), timeout=120)
                if row.get("repeat_sec"):
                    await self.db.execute("UPDATE scheduled_tasks SET status='pending', run_at=? WHERE id=?",
                                          (now + int(row["repeat_sec"]), row["id"]))
                else:
                    await self.db.execute("UPDATE scheduled_tasks SET status='done' WHERE id=?", (row["id"],))
                self.runs += 1
            except Exception as e:
                self.failures += 1
                log.warning("scheduled task %s (%s) failed: %s", row["id"], row["kind"], type(e).__name__)
                retry = row["attempts"] + 1 < 3
                await self.db.execute("UPDATE scheduled_tasks SET status=?, run_at=?, last_error=? WHERE id=?",
                                      ("pending" if retry else "failed", now + 60, str(e)[:300], row["id"]))
        return len(rows)

    async def recover(self) -> int:
        """Tasks left 'running' by a crash are safe to retry (handlers are idempotent)."""
        return await self.db.rowcount("UPDATE scheduled_tasks SET status='pending' WHERE status='running'")

    async def _loop(self) -> None:
        await self.recover()
        while not self._stop.is_set():
            self.last_tick_at = time.time()
            try:
                await self.run_due()
            except Exception:
                log.exception("scheduler run_due failed")
            for job in self.periodic:
                if time.time() >= job["next"]:
                    job["next"] = time.time() + job["interval"]
                    try:
                        await asyncio.wait_for(job["fn"](), timeout=max(60, job["interval"]))
                        job["last_ok"] = int(time.time())
                        job["runs"] += 1
                    except Exception as e:
                        job["last_error"] = f"{type(e).__name__}: {str(e)[:120]}"
                        log.warning("periodic job %s failed: %s", job["name"], job["last_error"])
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.tick)
            except asyncio.TimeoutError:
                pass

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._stop.clear()
            self._task = asyncio.create_task(self._loop(), name="scheduler")

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=10)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                self._task.cancel()

    async def restart(self) -> None:
        await self.stop()
        self.start()

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    def status(self) -> dict[str, Any]:
        return {"running": self.running, "last_tick_at": int(self.last_tick_at), "runs": self.runs, "failures": self.failures,
                "jobs": [{k: v for k, v in j.items() if k != "fn"} for j in self.periodic]}
