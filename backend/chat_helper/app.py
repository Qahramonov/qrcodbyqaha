"""Application bootstrap: builds the AppContext, aiogram Dispatcher and background jobs."""
from __future__ import annotations

import logging
import time
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware, Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import TelegramObject, Update

from .config import Settings
from .core.context import AppContext, Runtime
from .core.events import EventBus
from .core.logging import setup_logging
from .database.db import Database
from .database.migrations import apply_migrations

log = logging.getLogger(__name__)


def load_modules() -> None:
    """Importing modules registers their commands in the global registry (idempotent)."""
    from .games import games  # noqa: F401
    from .modules import afk, ai_cmds, animations, autoreply, controls, extra_cmds, media_cmds, profile, repeat, system_cmds, text_tools  # noqa: F401


class ActivityMiddleware(BaseMiddleware):
    """Tracks active users, enforces maintenance mode for non-admins in the bot DM."""

    def __init__(self, app: AppContext) -> None:
        self.app = app

    async def __call__(self, handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]], event: TelegramObject,
                      data: dict[str, Any]) -> Any:
        app = self.app
        uid = None
        if isinstance(event, Update):
            if event.message and event.message.from_user and event.message.chat.type == "private":
                uid = event.message.from_user.id
            elif event.callback_query:
                uid = event.callback_query.from_user.id
            elif event.business_connection:
                uid = event.business_connection.user.id
            elif event.business_message and event.business_message.from_user:
                bc = await app.connections.get(event.business_message.business_connection_id or "")
                if bc and event.business_message.from_user.id == bc.user_id:
                    uid = bc.user_id
            if event.update_id and await app.dedup.seen(f"u:{event.update_id}", persist=False):
                return None
        if uid:
            try:
                await app.analytics.touch(uid)
            except Exception:  # pragma: no cover
                pass
            if app.runtime.maintenance and isinstance(event, Update) and event.message and not await app.users.is_admin(uid):
                await event.message.answer("🛠 Chat helper на обслуживании. Попробуйте позже. / Texnik xizmat. Keyinroq urinib ko'ring.")
                return None
        return await handler(event, data)


async def build_app(cfg: Settings, bot: Bot | None = None, *, with_bot: bool = True) -> tuple[AppContext, Dispatcher]:
    from .ai.auto import AIAutoReply
    from .ai.auto import router as ai_drafts_router
    from .ai.service import AIService
    from .auth.service import AuthService
    from .automation.custom import CustomCommandService
    from .automation.engine import AutomationEngine
    from .business.guard import Deduplicator, LoopGuard
    from .business.sender import BusinessSender
    from .commands.executor import CommandExecutor
    from .commands.registry import registry
    from .games.engine import GameEngine
    from .games.games import register_games
    from .games.games import router as games_router
    from .handlers.business import router as business_router
    from .handlers.chatmgr import router as chatmgr_router
    from .handlers.controls import router as controls_router
    from .modules.animations import router as animations_router
    from .handlers.onboarding import router as onboarding_router
    from .handlers.twin import router as twin_router
    from .handlers.panel import router as panel_router
    from .media.service import MediaService
    from .modules.afk import AFKService
    from .modules.ai_cmds import router as ai_cmds_router
    from .modules.autoreply import AutoReplyService
    from .modules.chat_filters import FilterEngine
    from .services.chat_controls import ChatControlService
    from .modules.media_cmds import router as media_router
    from .modules.pipeline import Pipeline
    from .modules.profile import ProfileService
    from .modules.system_cmds import router as system_router
    from .modules.text_tools import router as text_router
    from .security.ratelimit import QuotaService, SlidingWindowLimiter
    from .services.analytics import AnalyticsService
    from .services.audit import AuditService, MetricsService, NotificationService
    from .services.backups import BackupService
    from .services.broadcast import BroadcastService
    from .services.chats import ChatService
    from .services.health import HealthService
    from .services.inbox import InboxService
    from .services.scheduler import Scheduler
    from .services.settings import SettingsService
    from .services.users import UserService
    from .subscriptions.payments import PaymentService
    from .subscriptions.payments import router as payments_router
    from .subscriptions.service import SubscriptionService

    cfg.ensure_dirs()
    secret = cfg.load_or_create_secret()
    setup_logging(cfg.log_level, cfg.logs_dir, cfg.secret_values())
    load_modules()

    app = AppContext()
    app.config = cfg
    app.db = Database(cfg.database_path)
    await app.db.connect()
    await apply_migrations(app.db, cfg.backups_dir)
    app.events = EventBus()
    app.runtime = Runtime(app.db)
    await app.runtime.load()
    app.users = UserService(app.db, cfg.super_admin_id)
    app.settings = SettingsService(app.db, cfg.default_lang, cfg.command_prefix, cfg.timezone)
    app.chats = ChatService(app.db)
    from .business.connections import ConnectionService
    app.connections = ConnectionService(app.db)
    app.audit = AuditService(app.db)
    app.metrics = MetricsService(app.db)
    app.notifications = NotificationService(app.db, app.events)
    app.quotas = QuotaService(app.db)
    app.limiter = SlidingWindowLimiter()
    app.dedup = Deduplicator(app.db)
    app.loop_guard = LoopGuard()
    app.subs = SubscriptionService(app.db, cfg.super_admin_id, app.notifications)
    await app.subs.seed()
    app.auth = AuthService(app.db, secret, app.users, app.limiter, app.audit, app.notifications,
                           cfg.access_token_ttl, cfg.refresh_token_ttl, cfg.pairing_code_ttl)
    app.registry = registry
    app.executor = CommandExecutor(app, registry)
    await app.executor.sync_registry()
    app.custom_commands = CustomCommandService(app)
    app.ai = AIService(app.db, cfg, app.quotas, app.subs, app.metrics, app.events, app.settings)
    app.ai_auto = AIAutoReply(app)
    from .ai.twin import TwinService
    app.twin = TwinService(app)
    app.health = HealthService(app)
    await app.health.check_ffmpeg()
    app.media = MediaService(app)
    app.games = GameEngine(app)
    register_games(app.games)
    app.afk = AFKService(app)
    app.autoreply = AutoReplyService(app)
    app.automation = AutomationEngine(app)
    app.inbox = InboxService(app)
    app.controls = ChatControlService(app.db)
    app.filters = FilterEngine(app)
    app.pipeline = Pipeline(app)
    app.profile = ProfileService(app)
    app.payments = PaymentService(app)
    app.broadcast = BroadcastService(app)
    app.backups = BackupService(app)
    app.analytics = AnalyticsService(app)
    app.scheduler = Scheduler(app.db)
    from .services.reminders import ReminderService
    app.reminders = ReminderService(app)
    from .modules.repeat import interrupt_running
    await interrupt_running(app)
    await app.db.execute("UPDATE animation_jobs SET status='interrupted', finished_at=? WHERE status='running'", (int(time.time()),))

    if with_bot and bot is None:
        if not cfg.bot_token:
            raise RuntimeError("BOT_TOKEN is not set. Copy backend/.env.example to backend/.env and fill BOT_TOKEN.")
        bot = Bot(cfg.bot_token, default=DefaultBotProperties(parse_mode="HTML"))
    app.bot = bot
    app.sender = BusinessSender(bot, app.events, app.metrics) if bot is not None else None

    async def protect_resolver(bc_id: str, chat_id: int) -> bool:
        conn = await app.connections.get(bc_id)
        return conn is not None and await app.controls.is_on(conn.user_id, chat_id, "protect")
    if app.sender is not None:
        app.sender.protect_resolver = protect_resolver

    async def push(uid: int, text: str) -> None:
        if app.sender is not None:
            await app.sender.send_text(uid, text)
    app.notifications.sender = push

    async def support_message(uid: int, text: str) -> None:
        u = await app.users.get(uid) or {}
        await app.notifications.notify(cfg.super_admin_id, "support", f"Support: {uid}", text[:1500])
        if app.sender is not None:
            from .security.sanitize import esc
            await app.sender.send_text(cfg.super_admin_id, f"✉️ <b>Support</b> от {esc(u.get('first_name') or '')} (@{esc(u.get('username') or '-')}, "
                                                           f"<code>{uid}</code>):\n{esc(text[:3000])}")
    app.support_message = support_message  # type: ignore[attr-defined]

    _register_jobs(app)

    dp = Dispatcher(storage=MemoryStorage())
    dp["app"] = app
    app.fsm_storage = dp.storage
    dp.update.outer_middleware(ActivityMiddleware(app))
    for r in (payments_router, business_router, controls_router, animations_router, ai_drafts_router, ai_cmds_router, media_router, text_router,
              system_router, games_router, onboarding_router, chatmgr_router, twin_router, panel_router):
        if r.parent_router is not None:  # routers are module-level singletons; allow re-binding (tests, restarts)
            r._parent_router = None  # noqa: SLF001
        dp.include_router(r)
    return app, dp


def _register_jobs(app: AppContext) -> None:
    sch = app.scheduler


    async def timer_delete(task: dict[str, Any]) -> None:
        p = task["payload"]
        conn = await app.connections.get(p["conn"])
        if conn is None or conn.user_id != task["user_id"]:
            return
        res = await app.sender.delete(p["chat_id"], [int(i) for i in p["ids"]], bc_id=conn.id)
        if not res.ok and res.kind not in ("not_found",):
            raise RuntimeError(res.kind)

    async def resume_automation(task: dict[str, Any]) -> None:
        await app.settings.set(task["user_id"], "automation_paused", False)

    async def broadcast_start(task: dict[str, Any]) -> None:
        await app.broadcast.start(int(task["payload"]["id"]), task["user_id"])

    sch.register("reminder", app.reminders.fire_dm)
    sch.register("reminder_chat", app.reminders.fire_chat)
    sch.register("timer_delete", timer_delete)
    sch.register("resume_automation", resume_automation)
    sch.register("broadcast_start", broadcast_start)
    sch.register("automation_delayed", app.automation.run_delayed)

    async def retention() -> None:
        await app.ai.memory.apply_retention(app.settings)
        await app.dedup.cleanup()
        await app.quotas.cleanup()
        await app.auth.cleanup()
        now = int(time.time())
        keep = app.config.log_retention_days * 86400
        await app.db.execute("DELETE FROM command_history WHERE created_at < ?", (now - 90 * 86400,))
        await app.db.execute("DELETE FROM audit_logs WHERE created_at < ?", (now - 365 * 86400,))
        await app.db.execute("DELETE FROM system_logs WHERE created_at < ?", (now - keep,))
        await app.db.execute("DELETE FROM notification_events WHERE created_at < ? AND read_at IS NOT NULL", (now - 60 * 86400,))
        await app.db.execute("DELETE FROM automation_executions WHERE created_at < ?", (now - 30 * 86400,))
        await app.db.execute("DELETE FROM game_sessions WHERE status='finished' AND updated_at < ?", (now - 30 * 86400,))
        await app.db.execute("DELETE FROM media_jobs WHERE created_at < ?", (now - 60 * 86400,))
        await app.db.execute("DELETE FROM ai_drafts WHERE created_at < ? AND status != 'pending'", (now - 14 * 86400,))
        await app.db.execute("UPDATE chat_settings SET last_preview=NULL WHERE last_incoming_at < ?", (now - 7 * 86400,))
        # v3: stored chat history (for .sum / AI context) follows each user's retention setting
        for r in await app.db.fetchall("SELECT DISTINCT owner_id FROM chat_messages"):
            days = await app.settings.get(r["owner_id"], "history_retention_days")
            await app.db.execute("DELETE FROM chat_messages WHERE owner_id=? AND created_at < ?", (r["owner_id"], now - int(days) * 86400))
        await app.db.execute("DELETE FROM mute_events WHERE created_at < ?", (now - 90 * 86400,))
        await app.db.execute("DELETE FROM permission_snapshots WHERE created_at < ?", (now - 180 * 86400,))
        await app.controls.cleanup(30)

    async def tmp_cleanup() -> None:
        app.media.files.cleanup(3600)

    async def subs_expiry() -> None:
        await app.subs.expire_due()

    async def daily_summary() -> None:
        from .core.timeutil import local_dt
        rows = await app.db.fetchall("SELECT user_id FROM user_settings WHERE key='ai_daily_summary' AND value_json='true'")
        for r in rows:
            s = await app.settings.all(r["user_id"])
            now = local_dt(None, s["timezone"])
            if now.hour == 21 and now.minute < 10:
                key = f"digest:{r['user_id']}:{now.strftime('%Y-%m-%d')}"
                if await app.dedup.seen(key):
                    continue
                await app.sender.send_text(r["user_id"], await app.inbox.digest_text(r["user_id"], s["lang"], use_ai=True))

    async def ai_budget_watch() -> None:
        spent = await app.ai.spent_today(0)
        if spent >= app.config.ai_global_daily_budget_usd * 0.9:
            key = f"budget:{time.strftime('%Y-%m-%d')}"
            if not await app.dedup.seen(key):
                await app.notifications.notify(app.config.super_admin_id, "ai_budget", "AI budget 90%",
                                               f"Spent ${spent:.3f} of ${app.config.ai_global_daily_budget_usd:.2f}", level="warning", push=True)

    async def health_watch() -> None:
        d = app.health.disk()
        if not d["ok"]:
            await app.notifications.notify(app.config.super_admin_id, "disk", "Low disk space", f"free {d['free_mb']} MB", level="error")
        app.media.queue.start()  # self-heal crashed workers

    async def controls_expiry() -> None:
        """Timed Mute / filters end automatically: state off → cards updated → owner informed."""
        from .localization import tr
        from .modules.controls import chat_title, refresh_cards
        for row in await app.controls.due_for_expiry():
            await app.controls.set(row["owner_id"], row["chat_id"], row["module"], False)
            await refresh_cards(app, row["owner_id"], row["chat_id"], row["module"])
            s = await app.settings.all(row["owner_id"])
            from .security.sanitize import esc
            name = esc(await chat_title(app, row["owner_id"], row["chat_id"]))
            text = tr(s["lang"], "⏰ Время режима «{m}» в чате «{n}» истекло — режим выключен.",
                      "⏰ «{n}» chatidagi «{m}» rejimi vaqti tugadi — rejim o'chirildi.", m=row["module"], n=name)
            if row["module"] == "mute":
                text += "\n" + tr(s["lang"], "📊 Удалено сообщений: {d}", "📊 O'chirilgan xabarlar: {d}", d=row["state"].get("deleted", 0))
            await app.sender.send_text(row["owner_id"], text)

    sch.every(20, "controls_expiry", controls_expiry, 10)
    sch.every(30, "afk_expiry", app.afk.expire_due, 5)
    sch.every(30, "games_expiry", app.games.expire_due, 15)
    sch.every(30, "automation_time", app.automation.tick_time, 20)
    sch.every(60, "automation_no_reply", app.automation.tick_no_reply, 40)
    sch.every(60, "profile_clock", app.profile.clock_tick, 30)
    sch.every(60, "broadcast_scheduled", app.broadcast.run_scheduled, 25)
    sch.every(600, "subscriptions_expiry", subs_expiry, 60)
    sch.every(3600, "retention_cleanup", retention, 120)
    sch.every(1800, "tmp_cleanup", tmp_cleanup, 90)
    sch.every(1800, "auto_backup", app.backups.auto, 300)
    sch.every(300, "daily_summary", daily_summary, 200)
    sch.every(600, "ai_budget_watch", ai_budget_watch, 240)
    sch.every(300, "health_watch", health_watch, 150)


async def start_background(app: AppContext) -> None:
    await app.media.queue.recover()
    app.media.queue.start()
    app.scheduler.start()


async def stop_background(app: AppContext) -> None:
    await app.scheduler.stop()
    await app.media.queue.stop()
    await app.ai.close()
