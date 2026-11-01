"""Broadcast Center: messages from the bot to its own users who allowed contact.
Business connections are NEVER used for mass messaging. Telegram rate limits are respected."""
from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Any

from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from ..database.db import dumps, loads

if TYPE_CHECKING:  # pragma: no cover
    from ..core.context import AppContext

log = logging.getLogger(__name__)
RATE_PER_SEC = 20


def _markup(buttons: list[dict[str, str]]) -> InlineKeyboardMarkup | None:
    rows = [[InlineKeyboardButton(text=b["text"][:64], url=b["url"])] for b in buttons[:6] if b.get("text") and str(b.get("url", "")).startswith("https://")]
    return InlineKeyboardMarkup(inline_keyboard=rows) if rows else None


class BroadcastService:
    def __init__(self, app: "AppContext") -> None:
        self.app = app
        self._tasks: dict[int, asyncio.Task] = {}

    async def create(self, created_by: int, text: str | None = None, media_type: str | None = None, media_file_id: str | None = None,
                     buttons: list[dict[str, str]] | None = None, segment: dict[str, Any] | None = None, scheduled_at: int | None = None) -> int:
        if not text and not media_file_id:
            raise ValueError("text or media required")
        if media_type not in (None, "photo", "video"):
            raise ValueError("media_type must be photo or video")
        if text and len(text) > (1024 if media_file_id else 4096):
            raise ValueError("text too long")
        for b in buttons or []:
            if not str(b.get("url", "")).startswith("https://"):
                raise ValueError("buttons must use https:// urls")
        return await self.app.db.execute(
            "INSERT INTO broadcasts(created_by, text, media_type, media_file_id, buttons_json, segment_json, status, scheduled_at, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?)", (created_by, text, media_type, media_file_id, dumps(buttons or []), dumps(segment or {}),
                                           "scheduled" if scheduled_at else "draft", scheduled_at, int(time.time())))

    async def get(self, bid: int) -> dict[str, Any] | None:
        row = await self.app.db.fetchone("SELECT * FROM broadcasts WHERE id=?", (bid,))
        if row:
            row["buttons"] = loads(row.pop("buttons_json"), [])
            row["segment"] = loads(row.pop("segment_json"), {})
        return row

    async def list(self, limit: int = 50) -> list[dict[str, Any]]:
        rows = await self.app.db.fetchall("SELECT * FROM broadcasts ORDER BY id DESC LIMIT ?", (limit,))
        for r in rows:
            r["buttons"] = loads(r.pop("buttons_json"), [])
            r["segment"] = loads(r.pop("segment_json"), {})
        return rows

    async def recipients(self, segment: dict[str, Any]) -> list[int]:
        where = ["broadcast_opt_in=1", "bot_blocked=0", "status='active'"]
        params: list[Any] = []
        if segment.get("lang") in ("ru", "uz"):
            where.append("language=?")
            params.append(segment["lang"])
        if segment.get("active_days"):
            where.append("last_seen_at >= ?")
            params.append(int(time.time()) - int(segment["active_days"]) * 86400)
        if segment.get("connected") is True:
            where.append("EXISTS (SELECT 1 FROM business_connections bc WHERE bc.user_id=users.id AND bc.is_enabled=1)")
        rows = await self.app.db.fetchall(f"SELECT id FROM users WHERE {' AND '.join(where)}", params)
        ids = [r["id"] for r in rows]
        if segment.get("plan"):
            ids = [i for i in ids if await self.app.subs.plan_of(i) == segment["plan"]]
        if segment.get("user_ids"):
            allowed = {int(x) for x in segment["user_ids"]}
            ids = [i for i in ids if i in allowed]
        return ids

    async def _send_one(self, b: dict[str, Any], uid: int) -> None:
        bot = self.app.bot
        markup = _markup(b["buttons"])
        if b["media_type"] == "photo":
            await bot.send_photo(uid, b["media_file_id"], caption=b["text"], reply_markup=markup)
        elif b["media_type"] == "video":
            await bot.send_video(uid, b["media_file_id"], caption=b["text"], reply_markup=markup)
        else:
            await bot.send_message(uid, b["text"], reply_markup=markup, disable_web_page_preview=True)

    async def preview(self, bid: int, admin_id: int) -> bool:
        b = await self.get(bid)
        if not b:
            return False
        try:
            await self._send_one(b, admin_id)
            return True
        except Exception as e:
            log.info("broadcast preview failed: %s", e)
            return False

    async def start(self, bid: int, by: int) -> dict[str, Any]:
        b = await self.get(bid)
        if not b or b["status"] not in ("draft", "scheduled"):
            raise ValueError("broadcast cannot be started")
        ids = await self.recipients(b["segment"])
        await self.app.db.execute("UPDATE broadcasts SET status='running', total=?, started_at=? WHERE id=?", (len(ids), int(time.time()), bid))
        await self.app.audit.log("broadcast.start", actor_id=by, target_type="broadcast", target_id=bid, total=len(ids))
        self._tasks[bid] = asyncio.create_task(self._run(bid, ids))
        return {"id": bid, "total": len(ids)}

    async def _run(self, bid: int, ids: list[int]) -> None:
        b = await self.get(bid)
        sent = failed = 0
        try:
            for i, uid in enumerate(ids):
                if bid not in self._tasks:
                    break
                for _attempt in range(3):
                    try:
                        await self._send_one(b, uid)
                        sent += 1
                        break
                    except TelegramRetryAfter as e:
                        await asyncio.sleep(e.retry_after + 1)
                    except TelegramForbiddenError:
                        failed += 1
                        await self.app.users.set_bot_blocked(uid, True)
                        await self.app.db.execute("INSERT INTO broadcast_errors(broadcast_id, user_id, error, created_at) VALUES (?,?,?,?)",
                                                  (bid, uid, "blocked", int(time.time())))
                        break
                    except Exception as e:
                        failed += 1
                        await self.app.db.execute("INSERT INTO broadcast_errors(broadcast_id, user_id, error, created_at) VALUES (?,?,?,?)",
                                                  (bid, uid, str(e)[:200], int(time.time())))
                        break
                if i % 10 == 0:
                    await self.app.db.execute("UPDATE broadcasts SET sent=?, failed=? WHERE id=?", (sent, failed, bid))
                await asyncio.sleep(1 / RATE_PER_SEC)
            status = "done" if bid in self._tasks else "cancelled"
        except asyncio.CancelledError:
            status = "cancelled"
        await self.app.db.execute("UPDATE broadcasts SET sent=?, failed=?, status=?, finished_at=? WHERE id=?",
                                  (sent, failed, status, int(time.time()), bid))
        self._tasks.pop(bid, None)
        self.app.events.emit("broadcast", user_id=b["created_by"], id=bid, status=status, sent=sent, failed=failed)

    async def cancel(self, bid: int, by: int) -> bool:
        t = self._tasks.pop(bid, None)
        if t:
            t.cancel()
        n = await self.app.db.rowcount("UPDATE broadcasts SET status='cancelled' WHERE id=? AND status IN ('draft','scheduled','running')", (bid,))
        await self.app.audit.log("broadcast.cancel", actor_id=by, target_type="broadcast", target_id=bid)
        return n > 0 or t is not None

    async def errors(self, bid: int, limit: int = 100) -> list[dict[str, Any]]:
        return await self.app.db.fetchall("SELECT * FROM broadcast_errors WHERE broadcast_id=? ORDER BY id DESC LIMIT ?", (bid, limit))

    async def run_scheduled(self) -> int:
        rows = await self.app.db.fetchall("SELECT id, created_by FROM broadcasts WHERE status='scheduled' AND scheduled_at <= ?", (int(time.time()),))
        for r in rows:
            try:
                await self.start(r["id"], r["created_by"])
            except ValueError:
                pass
        return len(rows)
