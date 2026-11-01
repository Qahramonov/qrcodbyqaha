"""Command dispatcher: resolve → authorize (owner/role/plan/rights/module) → rate-limit → run → record."""
from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Any

from aiogram.types import Message

from ..business.rights import explain_command_failure
from ..localization import p, tr
from ..security.sanitize import esc
from .context import CommandContext, CommandError, UsageError
from .parser import ParsedCommand, parse
from .registry import PLAN_RANK, CommandSpec, Registry

if TYPE_CHECKING:  # pragma: no cover
    from ..business.connections import Conn
    from ..core.context import AppContext

log = logging.getLogger(__name__)

HANDLER_TIMEOUT = 300
# v3: before a Business connection exists only these commands work in the private chat with the bot
PRE_CONNECT_COMMANDS = frozenset({"help", "lang", "support", "menu", "about", "privacy"})


def locked_reply(lang: str) -> tuple[str, Any]:
    from ..keyboards import kb
    text = tr(lang, "🔒 Ваш Telegram-аккаунт ещё не подключён.\nПодключите Chat helper, чтобы использовать команды.",
              "🔒 Telegram akkauntingiz hali ulanmagan.\nBuyruqlardan foydalanish uchun Chat helper'ni ulang.")
    markup = kb([[(tr(lang, "🔗 Подключить", "🔗 Ulash"), "m:connect")],
                 [(tr(lang, "📖 Инструкция", "📖 Yo'riqnoma"), "ob:guide")],
                 [(tr(lang, "🔄 Проверить подключение", "🔄 Ulanishni tekshirish"), "ob:check")]])
    return text, markup


class CommandExecutor:
    def __init__(self, app: "AppContext", registry: Registry) -> None:
        self.app = app
        self.registry = registry

    async def sync_registry(self) -> None:
        """Mirror code-defined commands into the DB (keeps admin toggles & counters)."""
        now = int(time.time())
        async with self.app.db.transaction() as tx:
            for spec in self.registry.commands.values():
                await tx.execute(
                    "INSERT INTO command_registry(command_id, name, category, min_plan, status, synced_at) VALUES (?,?,?,?,?,?) "
                    "ON CONFLICT(command_id) DO UPDATE SET name=excluded.name, category=excluded.category, "
                    "status=excluded.status, synced_at=excluded.synced_at",
                    (spec.id, spec.id, spec.category, spec.min_plan, spec.status, now))
        rows = await self.app.db.fetchall("SELECT command_id, enabled_global, min_plan FROM command_registry")
        self._global = {r["command_id"]: (bool(r["enabled_global"]), r["min_plan"]) for r in rows}

    def _global_state(self, spec: CommandSpec) -> tuple[bool, str]:
        return getattr(self, "_global", {}).get(spec.id, (True, spec.min_plan))

    async def set_global(self, command_id: str, enabled: bool | None = None, min_plan: str | None = None) -> None:
        if enabled is not None:
            await self.app.db.execute("UPDATE command_registry SET enabled_global=? WHERE command_id=?",
                                      (1 if enabled else 0, command_id))
        if min_plan is not None:
            if min_plan not in PLAN_RANK:
                raise ValueError("invalid plan")
            await self.app.db.execute("UPDATE command_registry SET min_plan=? WHERE command_id=?", (min_plan, command_id))
        await self.sync_registry()

    # ---------------------------------------------------------------------------------
    async def try_handle(self, message: Message, *, user_id: int, source: str, conn: "Conn | None",
                         settings: dict[str, Any]) -> bool:
        """Returns True if the message was a command (handled or rejected)."""
        text = message.text or message.caption or ""
        parsed = parse(text, settings.get("prefix", "."))
        if parsed is None:
            return False
        if parsed.prefix == "/" and source == "business":
            return False  # in business chats only the configured prefix is a command
        spec = self.registry.resolve(parsed.name)
        lang = settings.get("lang", "ru")
        if source == "private":
            from ..handlers.ui import access
            acc = await access(self.app, user_id)
            if acc.locked and (spec is None or spec.id not in PRE_CONNECT_COMMANDS):
                text, markup = locked_reply(lang)
                await message.answer(text, reply_markup=markup)
                await self.app.metrics.incr("locked_command", user_id)
                return True
        if spec is None:
            custom = await self.app.custom_commands.find(user_id, parsed.name) if self.app.custom_commands else None
            if custom is not None:
                await self.app.custom_commands.run(custom, message=message, user_id=user_id, source=source,
                                                   conn=conn, settings=settings, parsed=parsed)
                return True
            if source == "private":
                sugg = self.registry.suggestions(parsed.name)
                hint = p(lang, "unknown_cmd", cmd=esc(parsed.prefix + parsed.name), prefix=settings.get("prefix", "."))
                if sugg:
                    hint += "\n" + tr(lang, "Возможно: ", "Balki: ") + ", ".join(settings.get("prefix", ".") + s for s in sugg)
                await message.answer(hint)
                return True
            return False  # unknown ".word" in a real chat is just text
        await self.execute(spec, parsed, message=message, user_id=user_id, source=source, conn=conn,
                           settings=settings, chat_id=message.chat.id)
        return True

    async def execute(self, spec: CommandSpec, parsed: ParsedCommand, *, message: Message | None, user_id: int,
                      source: str, conn: "Conn | None", settings: dict[str, Any], chat_id: int) -> CommandContext:
        app = self.app
        lang = settings.get("lang", "ru")
        role = await app.users.role(user_id)
        plan = await app.subs.plan_of(user_id) if app.subs else "free"
        ctx = CommandContext(app, spec, parsed, user_id=user_id, source=source, message=message, conn=conn,
                             chat_id=chat_id, settings=settings, role=role, plan=plan)
        started = time.monotonic()
        ok, error = False, None
        try:
            denial = await self.authorize(ctx)
            if denial:
                error = "denied"
                await self._reject(ctx, denial)
                return ctx
            allowed, retry = app.limiter.check(f"cmd:{user_id}:{spec.id}", *spec.rate)
            if allowed:
                allowed, retry = app.limiter.check(f"cmd:{user_id}:*", 60, 60)
            if not allowed:
                error = "rate_limited"
                await self._reject(ctx, p(lang, "rate_limited", sec=retry))
                return ctx
            if spec.needs_reply and ctx.reply is None and source != "sandbox":
                error = "needs_reply"
                await self._reject(ctx, p(lang, "need_reply") + "\n" + ctx.usage())
                return ctx
            await asyncio.wait_for(spec.handler(ctx), timeout=HANDLER_TIMEOUT)
            ok = True
        except UsageError as e:
            error = "usage"
            msg = (f"⚠️ {e}\n" if str(e) else "") + ctx.usage()
            if spec.examples:
                msg += "\n" + tr(lang, "Пример: ", "Misol: ") + "<code>" + esc(spec.examples[0].replace(".", ctx.prefix, 1)) + "</code>"
            await self._reject(ctx, msg)
        except CommandError as e:
            error = str(e)[:200]
            await self._reject(ctx, str(e))
        except asyncio.TimeoutError:
            error = "timeout"
            await self._reject(ctx, tr(lang, "⏱ Команда выполнялась слишком долго и была остановлена.",
                                       "⏱ Buyruq juda uzoq bajarildi va to'xtatildi."))
        except Exception as e:  # isolation: one broken command never breaks the bot
            error = f"{type(e).__name__}: {str(e)[:150]}"
            log.exception("command %s failed", spec.id)
            await self._reject(ctx, tr(lang, "⚠️ Внутренняя ошибка команды. Она записана в журнал.",
                                       "⚠️ Buyruqning ichki xatosi. U jurnalga yozildi."))
        finally:
            if source != "sandbox":
                await self._record(ctx, ok, error, int((time.monotonic() - started) * 1000))
        return ctx

    async def authorize(self, ctx: CommandContext) -> str | None:
        app, spec, lang = self.app, ctx.spec, ctx.lang
        if await app.users.is_restricted(ctx.user_id):
            return tr(lang, "⛔ Доступ к Chat helper ограничен администратором.", "⛔ Chat helper'ga kirish administrator tomonidan cheklangan.")
        if app.runtime.emergency_stop and ctx.is_business and spec.id not in ("status", "ping"):
            return p(lang, "emergency")
        if spec.admin_only and not ctx.is_admin:
            return p(lang, "not_allowed")
        if spec.where == "business" and ctx.source == "private":
            return tr(lang, "💬 Эта команда работает в чатах подключённого бизнес-аккаунта.",
                      "💬 Bu buyruq ulangan biznes akkaunt chatlarida ishlaydi.")
        if spec.where == "private" and ctx.is_business:
            return tr(lang, "🔒 Эта команда доступна только в личном чате с Chat helper.",
                      "🔒 Bu buyruq faqat Chat helper bilan shaxsiy chatda mavjud.")
        enabled, min_plan = self._global_state(spec)
        if not enabled:
            return tr(lang, "⏸ Команда {cmd} отключена администратором.", "⏸ {cmd} buyrug'i administrator tomonidan o'chirilgan.",
                      cmd=ctx.prefix + spec.id)
        if spec.id in (ctx.settings.get("disabled_commands") or []):
            return tr(lang, "⏸ Вы отключили команду {cmd}. Включить: меню → Команды.",
                      "⏸ Siz {cmd} buyrug'ini o'chirgansiz. Yoqish: menyu → Buyruqlar.", cmd=ctx.prefix + spec.id)
        if app.runtime.is_module_paused(spec.module):
            return p(lang, "module_off", module=spec.module)
        if spec.module == "games" and not ctx.settings.get("games_enabled", True):
            return p(lang, "module_off", module="games")
        if spec.module == "media" and not ctx.settings.get("media_enabled", True):
            return p(lang, "module_off", module="media")
        if not ctx.is_super and PLAN_RANK.get(ctx.plan, 0) < PLAN_RANK.get(min_plan, 0):
            return p(lang, "plan_required", plan=min_plan.upper())
        if ctx.is_business and spec.rights and ctx.conn is not None:
            why = explain_command_failure(spec.rights, ctx.conn.rights, lang)
            if why:
                return why
        for dep in spec.deps:
            if dep == "ffmpeg" and not app.health.ffmpeg_ok:
                return tr(lang, "🎞 FFmpeg не найден. Установите: pkg install ffmpeg", "🎞 FFmpeg topilmadi. O'rnating: pkg install ffmpeg")
            if dep == "ai" and not app.ai.available():
                return p(lang, "requires_ai")
            if dep == "ai_stt" and not app.ai.available("stt"):
                return tr(lang, "🎙 Распознавание речи требует ключ OpenAI или Gemini (STT).",
                          "🎙 Nutqni aniqlash uchun OpenAI yoki Gemini kaliti kerak (STT).")
        return None

    async def _reject(self, ctx: CommandContext, text: str) -> None:
        if ctx.source == "sandbox":
            ctx.outputs.append({"type": "error", "text": text})
            return
        if ctx.is_business:
            # never spam the counterpart with errors: show them privately to the owner
            await ctx.app.sender.send_text(ctx.user_id, f"<b>{esc(ctx.prefix + ctx.spec.id)}</b>: {text}")
            await ctx.cleanup_command()
        else:
            await ctx.answer(text)

    async def _record(self, ctx: CommandContext, ok: bool, error: str | None, ms: int) -> None:
        app = self.app
        try:
            await app.db.execute(
                "INSERT INTO command_history(user_id, connection_id, chat_id, command_id, source, ok, error, duration_ms, created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (ctx.user_id, ctx.conn.id if ctx.conn else None, ctx.chat_id, ctx.spec.id, ctx.source, 1 if ok else 0,
                 error, ms, int(time.time())))
            await app.db.execute(
                "UPDATE command_registry SET calls=calls+1, errors=errors+?, last_error=COALESCE(?, last_error), last_used_at=? "
                "WHERE command_id=?", (0 if ok else 1, None if ok or error in ("denied", "usage", "rate_limited", "needs_reply") else error,
                                       int(time.time()), ctx.spec.id))
            await app.metrics.incr("commands", ctx.user_id)
            await app.metrics.incr(f"cmd:{ctx.spec.id}")
            if not ok and error not in ("denied", "usage", "rate_limited", "needs_reply"):
                await app.metrics.incr("errors", ctx.user_id)
            app.events.emit("command", user_id=ctx.user_id, command=ctx.spec.id, ok=ok, source=ctx.source, ms=ms)
        except Exception:  # pragma: no cover
            log.exception("failed to record command history")

    async def sandbox(self, user_id: int, text: str, settings: dict[str, Any]) -> dict[str, Any]:
        """APK 'test command' button: runs sandbox-safe commands, captures output, sends nothing."""
        parsed = parse(text, settings.get("prefix", "."))
        if parsed is None:
            return {"ok": False, "error": "not_a_command", "outputs": []}
        spec = self.registry.resolve(parsed.name)
        if spec is None:
            return {"ok": False, "error": "unknown_command", "outputs": [], "suggestions": self.registry.suggestions(parsed.name)}
        if not spec.sandbox_safe:
            return {"ok": False, "error": "not_sandbox_safe", "outputs": [],
                    "message": "This command interacts with chats/media and cannot be simulated safely."}
        ctx = await self.execute(spec, parsed, message=None, user_id=user_id, source="sandbox", conn=None,
                                 settings=settings, chat_id=user_id)
        errors = [o for o in ctx.outputs if o["type"] == "error"]
        return {"ok": not errors, "command": spec.id, "outputs": ctx.outputs}
