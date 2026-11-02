"""``.re`` — repeat a message: send it, after 5 s delete the previous copy and send it again (max 2 minutes).

Limits: Free — 3 runs per day; Plus and higher — no plan limit but technical anti-spam limits (one run per chat,
three per user, cooldown). Needs *can_reply* (send) and *can_delete_sent_messages* (delete the bot's previous copy).
Stops automatically on any Telegram error and reports why. A stop button (owner-only) is attached to each copy.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Any

from ..commands.context import CommandContext, CommandError, UsageError
from ..commands.registry import PLAN_RANK, registry
from ..localization import tr
from ..security.sanitize import esc

if TYPE_CHECKING:  # pragma: no cover
    from ..core.context import AppContext

log = logging.getLogger(__name__)

INTERVAL = 5
MAX_DURATION = 120
FREE_RUNS_PER_DAY = 3
MAX_PER_USER = 3
_tasks: dict[tuple[int, int], asyncio.Task] = {}


async def runs_today(app: "AppContext", owner: int) -> int:
    start = int(time.time()) - 86400
    return int(await app.db.fetchval("SELECT COUNT(*) FROM repetition_jobs WHERE owner_id=? AND created_at>=?", (owner, start), 0))


async def stop_repeat(app: "AppContext", owner: int, chat_id: int, reason: str = "manual") -> bool:
    task = _tasks.pop((owner, chat_id), None)
    if task and not task.done():
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass
        return True
    return False


async def _loop(app: "AppContext", job_id: int, owner: int, chat_id: int, bc_id: str, text: str, ends_at: int, token: str) -> None:
    from .controls import build_markup, render_view
    last_id: int | None = None
    status, error, sends = "done", None, 0
    try:
        while time.time() < ends_at:
            card = await app.controls.card(token)
            view = await render_view(app, card)
            res = await app.sender.send_text(chat_id, esc(text), bc_id=bc_id, markup=build_markup(card, view.buttons))
            if not res.ok:
                status, error = "failed", res.kind
                break
            sends += 1
            if last_id is not None:
                d = await app.sender.delete(chat_id, [last_id], bc_id=bc_id)
                if not d.ok and d.kind != "not_found":
                    status, error = "failed", d.kind
                    last_id = res.message_id
                    break
            last_id = res.message_id
            await app.controls.set_card_message(token, last_id)
            await app.db.execute("UPDATE repetition_jobs SET last_message_id=?, sends=? WHERE id=?", (last_id, sends, job_id))
            await asyncio.sleep(min(INTERVAL, max(0.0, ends_at - time.time())))
    except asyncio.CancelledError:
        status = "cancelled"
    finally:
        _tasks.pop((owner, chat_id), None)
        await app.db.execute("UPDATE repetition_jobs SET status=?, error=?, sends=?, finished_at=? WHERE id=?",
                             (status, error, sends, int(time.time()), job_id))
        card = await app.controls.card(token)
        if card and last_id:
            await app.sender.edit_text(chat_id, last_id, esc(text), bc_id=bc_id)     # final copy without buttons
        await app.controls.close_card(token)
        if status == "failed":
            s = await app.settings.all(owner)
            await app.sender.send_text(owner, tr(s["lang"], "repeat.povtor_ostanovlen_telegram_vernul_oshibku", e=error))


@registry.command("re", "chat", aliases=["повтор", "qaytar", "loop"],
                  where="business",
                  rights=["can_reply", "can_delete_sent_messages"], rate=(3, 60))
async def cmd_re(ctx: CommandContext) -> None:
    app, owner, chat_id = ctx.app, ctx.user_id, ctx.chat_id
    if ctx.parsed.first in ("stop", "стоп", "off"):
        stopped = await stop_repeat(app, owner, chat_id, reason="command")
        await ctx.cleanup_command(fallback_text="⏹")
        if not stopped:
            await app.sender.send_text(owner, ctx.t("repeat.etom_chate_povtor_zapuschen"))
        return
    text = ctx.raw.strip()
    if not text or len(text) > 1000:
        raise UsageError(ctx.t("repeat.nuzhen_tekst_1000_simvolov"))
    if (owner, chat_id) in _tasks:
        raise CommandError(ctx.t("repeat.etom_chate_idyot_povtor_ostanovit",
                                 p=ctx.prefix))
    if sum(1 for k in _tasks if k[0] == owner) >= MAX_PER_USER:
        raise CommandError(ctx.t("repeat.bolshe_povtorov_odnovremenno", n=MAX_PER_USER))
    if not ctx.is_super and PLAN_RANK.get(ctx.plan, 0) < PLAN_RANK["plus"] and await runs_today(app, owner) >= FREE_RUNS_PER_DAY:
        raise CommandError(ctx.t("repeat.tarife_free_zapuska_sutki_plus", n=FREE_RUNS_PER_DAY))
    ok, retry = app.limiter.check(f"re:cooldown:{owner}", 1, 10)
    if not ok:
        raise CommandError(ctx.t("repeat.podozhdite", s=retry))
    await ctx.cleanup_command()
    ends_at = int(time.time()) + MAX_DURATION
    job_id = await app.db.execute(
        "INSERT INTO repetition_jobs(owner_id, connection_id, chat_id, text, interval_sec, ends_at, status, created_at) "
        "VALUES (?,?,?,?,?,?,'running',?)", (owner, ctx.conn.id, chat_id, text, INTERVAL, ends_at, int(time.time())))
    token = await app.controls.create_card(owner, chat_id, "re", location="chat", host_chat_id=chat_id, message_id=None,
                                           connection_id=ctx.conn.id)
    _tasks[(owner, chat_id)] = asyncio.create_task(_loop(app, job_id, owner, chat_id, ctx.conn.id, text, ends_at, token))


async def interrupt_running(app: Any) -> int:
    """After a restart in-memory loops are gone: mark them honestly as interrupted."""
    return await app.db.rowcount("UPDATE repetition_jobs SET status='interrupted', finished_at=? WHERE status='running'", (int(time.time()),))
