"""AFK system: away status with reason, timer, themed day-part messages, per-chat exceptions,
cooldowns, auto-off on owner activity, away summary and optional AI replies."""
from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any

from ..commands.context import CommandContext, UsageError
from ..commands.registry import registry
from ..core.timeutil import day_part, fmt_dt, human_duration, next_occurrence, parse_duration, parse_hhmm
from ..database.db import dumps, loads
from ..localization import tr
from ..security.sanitize import esc

if TYPE_CHECKING:  # pragma: no cover
    from ..core.context import AppContext

log = logging.getLogger(__name__)

GREETINGS = {
    "morning": ("afk.greetings.dobroe_utro"),
    "day": ("afk.greetings.zdravstvuyte"),
    "evening": ("afk.greetings.dobryy_vecher"),
    "night": ("afk.greetings.dobroy_nochi"),
}


def render_afk(theme: str, lang: str, *, name: str, reason: str | None, away: int, until_ts: int | None,
               tz_name: str, part: str, kind: str = "afk") -> str:
    g = tr(lang, GREETINGS[part])
    dur = human_duration(away, lang)
    until = fmt_dt(until_ts, tz_name, with_date=False) if until_ts else None
    reason_e = esc(reason) if reason else None
    if kind == "sleep":
        head = tr(lang, "afk.spit", name=esc(name))
        lines = [g, "", head]
        if until:
            lines.append(tr(lang, "afk.prosnyotsya_primerno", u=until))
        lines.append(tr(lang, "afk.vashe_soobschenie_budet_prochitano_utrom"))
        return "\n".join(lines)
    if theme == "minimal":
        s = tr(lang, "afk.seychas_nedostupen", name=esc(name), dur=dur)
        if reason_e:
            s += f" {reason_e}."
        return s + tr(lang, "afk.otvechu_pozzhe")
    if theme == "fancy":
        rows = [tr(lang, "afk.net_meste"),
                f"│ 👤 {esc(name)}"]
        if reason_e:
            rows.append(f"│ 📝 {reason_e}")
        rows.append(f"│ ⏳ {dur}")
        if until:
            rows.append(tr(lang, "afk.vernyotsya", u=until))
        rows.append("╰──────────────")
        rows.append(tr(lang, "afk.soobschenie_budet_prochitano_pozzhe"))
        return g + "\n\n" + "\n".join(rows)
    if theme == "emoji":
        s = f"{g}\n💤💤💤\n👤 {esc(name)} → 🚶‍♂️💨\n⏳ {dur}"
        if reason_e:
            s += f"\n📝 {reason_e}"
        return s + "\n📩✅"
    # classic
    lines = [g, "", tr(lang, "afk.seychas_otsutstvuet", name=esc(name))]
    if reason_e:
        lines.append(tr(lang, "afk.prichina", r=reason_e))
    lines.append(tr(lang, "afk.vremya_otsutstviya", d=dur))
    if until:
        lines.append(tr(lang, "afk.vernyotsya_primerno", u=until))
    lines.append("")
    lines.append(tr(lang, "afk.vashe_soobschenie_budet_prochitano_pozzhe"))
    return "\n".join(lines)


def fill_custom(template: str, *, name: str, reason: str | None, away: int, until_ts: int | None, tz_name: str,
                lang: str) -> str:
    values = {"name": esc(name), "reason": esc(reason or "—"), "duration": human_duration(away, lang),
              "until": fmt_dt(until_ts, tz_name, with_date=False) if until_ts else "—"}
    out = esc(template)
    for k, v in values.items():
        out = out.replace("{" + k + "}", v)
    return out


class AFKService:
    def __init__(self, app: "AppContext") -> None:
        self.app = app
        self._last_reply: dict[tuple[int, int], float] = {}
        self._active_cache: dict[int, dict[str, Any] | None] = {}

    async def active(self, user_id: int) -> dict[str, Any] | None:
        if user_id in self._active_cache:
            return self._active_cache[user_id]
        row = await self.app.db.fetchone(
            "SELECT * FROM afk_sessions WHERE user_id=? AND ended_at IS NULL ORDER BY id DESC LIMIT 1", (user_id,))
        if row:
            row["chats"] = loads(row.pop("chats_json"), {})
        self._active_cache[user_id] = row
        return row

    async def _sync_cards(self, user_id: int) -> None:
        """Keep every AFK / auto-reply control card in sync, whatever changed the state (command, button, panel, API, timer)."""
        try:
            from .controls import refresh_owner_module
            await refresh_owner_module(self.app, user_id, "afk")
            await refresh_owner_module(self.app, user_id, "auto")
        except Exception:  # pragma: no cover - cards are best-effort UI
            pass

    async def enable(self, user_id: int, reason: str | None = None, duration: int | None = None,
                     kind: str = "afk", ends_at: int | None = None) -> dict[str, Any]:
        await self.disable(user_id, notify=False, restore_mode=False, sync=False)
        now = int(time.time())
        if ends_at is None and duration:
            ends_at = now + duration
        await self.app.db.execute(
            "INSERT INTO afk_sessions(user_id, reason, kind, started_at, ends_at) VALUES (?,?,?,?,?)",
            (user_id, (reason or "")[:300] or None, kind, now, ends_at))
        settings = await self.app.settings.all(user_id)
        if settings["mode"] != "afk":
            await self._store_prev_mode(user_id, settings["mode"])
            await self.app.settings.set(user_id, "mode", "afk")
        self._active_cache.pop(user_id, None)
        self._clear_cooldowns(user_id)
        self.app.events.emit("afk_on", user_id=user_id, reason=reason, ends_at=ends_at)
        await self.app.metrics.incr("afk_sessions", user_id)
        await self._sync_cards(user_id)
        return await self.active(user_id)  # type: ignore[return-value]

    async def _store_prev_mode(self, user_id: int, mode: str) -> None:
        await self.app.db.execute(
            "INSERT INTO module_settings(user_id, module, enabled, config_json, updated_at) VALUES (?,?,1,?,?) "
            "ON CONFLICT(user_id, module) DO UPDATE SET config_json=excluded.config_json, updated_at=excluded.updated_at",
            (user_id, "afk", dumps({"prev_mode": mode}), int(time.time())))

    async def _load_prev_mode(self, user_id: int) -> str:
        row = await self.app.db.fetchone("SELECT config_json FROM module_settings WHERE user_id=? AND module='afk'", (user_id,))
        mode = (loads(row["config_json"], {}) if row else {}).get("prev_mode") or "manual"
        return mode if mode != "afk" else "manual"

    async def disable(self, user_id: int, *, notify: bool = True, reason: str = "manual",
                      restore_mode: bool = True, sync: bool = True) -> dict[str, Any] | None:
        sess = await self.active(user_id)
        now = int(time.time())
        summary = None
        if sess:
            await self.app.db.execute("UPDATE afk_sessions SET ended_at=? WHERE id=?", (now, sess["id"]))
            summary = {"duration": now - sess["started_at"], "messages": sess["messages_received"],
                       "replies": sess["replies_sent"], "chats": len(sess["chats"]), "reason": sess["reason"],
                       "ended_by": reason, "chat_counts": sess["chats"]}
            self.app.events.emit("afk_off", user_id=user_id, by=reason)
        self._active_cache.pop(user_id, None)
        if restore_mode:
            settings = await self.app.settings.all(user_id)
            if settings["mode"] == "afk":
                await self.app.settings.set(user_id, "mode", await self._load_prev_mode(user_id))
        if summary and notify:
            settings = await self.app.settings.all(user_id)
            if settings.get("afk_notify_summary", True):
                await self.app.sender.send_text(user_id, await self.summary_text(user_id, summary, settings["lang"]))
        if sync and sess:
            await self._sync_cards(user_id)
        return summary

    async def summary_text(self, user_id: int, s: dict[str, Any], lang: str) -> str:
        by = {"manual": tr(lang, "afk.vruchnuyu"), "timer": tr(lang, "afk.taymeru"),
              "activity": tr(lang, "afk.vy_nachali_pisat")}.get(s["ended_by"], s["ended_by"])
        lines = [tr(lang, "afk.vozvrascheniem_afk_vyklyuchen", by=by),
                 tr(lang, "afk.vas_bylo", d=human_duration(s["duration"], lang)),
                 tr(lang, "afk.soobscheniy_chatov", m=s["messages"], c=s["chats"]),
                 tr(lang, "afk.avtootvetov_otpravleno", r=s["replies"])]
        if s["chat_counts"]:
            top = sorted(s["chat_counts"].items(), key=lambda kv: kv[1], reverse=True)[:5]
            lines.append("")
            lines.append(tr(lang, "afk.kto_pisal"))
            for chat_id, n in top:
                row = await self.app.chats.get(user_id, int(chat_id))
                title = esc((row or {}).get("title") or chat_id)
                lines.append(f"• {title} — {n}")
        return "\n".join(lines)

    def _clear_cooldowns(self, user_id: int) -> None:
        for k in [k for k in self._last_reply if k[0] == user_id]:
            self._last_reply.pop(k, None)

    async def build_reply(self, user_id: int, chat_id: int, settings: dict[str, Any], owner_name: str,
                          chat_lang: str | None = None) -> str:
        sess = await self.active(user_id)
        now = int(time.time())
        lang = chat_lang or settings["lang"]
        tz_name = settings.get("timezone") or self.app.config.timezone
        part = day_part(tz_name)
        reason = sess["reason"] if sess else None
        started = sess["started_at"] if sess else now
        until = sess["ends_at"] if sess else None
        kind = sess["kind"] if sess else "afk"
        custom = settings.get(f"afk_text_{part}") or ""
        if custom.strip():
            return fill_custom(custom, name=owner_name, reason=reason, away=now - started, until_ts=until,
                               tz_name=tz_name, lang=lang)
        return render_afk(settings.get("msg_theme", "classic"), lang, name=owner_name, reason=reason,
                          away=now - started, until_ts=until, tz_name=tz_name, part=part, kind=kind)

    def cooldown_ok(self, user_id: int, chat_id: int, minutes: int) -> bool:
        last = self._last_reply.get((user_id, chat_id), 0)
        return time.time() - last >= minutes * 60

    def mark_replied(self, user_id: int, chat_id: int) -> None:
        self._last_reply[(user_id, chat_id)] = time.time()

    async def record_incoming(self, user_id: int, chat_id: int, replied: bool) -> None:
        sess = await self.active(user_id)
        if not sess:
            return
        chats = dict(sess["chats"])
        chats[str(chat_id)] = chats.get(str(chat_id), 0) + 1
        await self.app.db.execute(
            "UPDATE afk_sessions SET messages_received=messages_received+1, replies_sent=replies_sent+?, chats_json=? WHERE id=?",
            (1 if replied else 0, dumps(chats), sess["id"]))
        sess["messages_received"] += 1
        sess["replies_sent"] += 1 if replied else 0
        sess["chats"] = chats

    async def expire_due(self) -> int:
        """Called by the scheduler: turn off sessions whose timer ended."""
        rows = await self.app.db.fetchall(
            "SELECT user_id FROM afk_sessions WHERE ended_at IS NULL AND ends_at IS NOT NULL AND ends_at <= ?", (int(time.time()),))
        for r in rows:
            await self.disable(r["user_id"], reason="timer")
        return len(rows)

    async def history(self, user_id: int, limit: int = 20) -> list[dict[str, Any]]:
        rows = await self.app.db.fetchall("SELECT * FROM afk_sessions WHERE user_id=? ORDER BY id DESC LIMIT ?", (user_id, limit))
        for r in rows:
            r["chats"] = loads(r.pop("chats_json"), {})
        return rows

    async def stats(self, user_id: int) -> dict[str, Any]:
        row = await self.app.db.fetchone(
            "SELECT COUNT(*) AS sessions, COALESCE(SUM(COALESCE(ended_at, strftime('%s','now')) - started_at),0) AS total_sec, "
            "COALESCE(SUM(messages_received),0) AS messages, COALESCE(SUM(replies_sent),0) AS replies "
            "FROM afk_sessions WHERE user_id=?", (user_id,))
        return row or {}


# ------------------------------------------------------------------------------------------------
# commands
# ------------------------------------------------------------------------------------------------

def _status_text(ctx: CommandContext, sess: dict[str, Any] | None) -> str:
    if not sess:
        return ctx.t("afk.afk_vyklyuchen_vklyuchit_afk_prichina",
                     p=ctx.prefix)
    tz_name = ctx.settings.get("timezone") or ctx.app.config.timezone
    lines = [ctx.t("afk.afk_vklyuchyon")]
    if sess.get("reason"):
        lines.append(ctx.t("afk.prichina", r=esc(sess["reason"])))
    lines.append(ctx.t("afk.text", d=human_duration(time.time() - sess["started_at"], ctx.lang)))
    if sess.get("ends_at"):
        lines.append(ctx.t("afk.vyklyuchitsya", t=fmt_dt(sess["ends_at"], tz_name)))
    lines.append(ctx.t("afk.soobscheniy_otvetov",
                       m=sess["messages_received"], r=sess["replies_sent"]))
    return "\n".join(lines)


@registry.command("afk", "afk", aliases=["афк", "away"],
                  )
async def cmd_afk(ctx: CommandContext) -> None:
    afk: AFKService = ctx.app.afk
    sub = ctx.parsed.first
    if sub in ("status", "статус", "holat"):
        await ctx.answer(_status_text(ctx, await afk.active(ctx.user_id)))
        return
    if sub in ("time", "время", "vaqt"):
        sess = await afk.active(ctx.user_id)
        if not sess:
            await ctx.answer(ctx.t("afk.afk_aktiven"))
        else:
            await ctx.answer(ctx.t("afk.vy_otsutstvuete",
                                   d=human_duration(time.time() - sess["started_at"], ctx.lang, 3)))
        return
    if sub in ("off", "выкл", "stop", "o'chir"):
        await cmd_unafk(ctx)
        return
    args = list(ctx.args)
    duration = None
    if args:
        d = parse_duration(args[0])
        if d and d >= 60:
            duration = min(d, 30 * 86400)
            args = args[1:]
    reason = " ".join(args).strip() or None
    if reason and len(reason) > 300:
        raise UsageError(ctx.t("afk.prichina_slishkom_dlinnaya_300_simvolov"))
    await afk.enable(ctx.user_id, reason, duration)
    from .controls import post_card
    if ctx.source == "sandbox":
        await ctx.answer(ctx.t("afk.afk_vklyuchyon_2"))
        return
    await post_card(ctx.app, ctx.user_id, ctx.chat_id if ctx.is_business else ctx.user_id, "afk",
                    conn=ctx.conn if ctx.is_business else None, ctx=ctx if ctx.is_business else None)


@registry.command("unafk", "afk", aliases=["анафк", "back", "вернулся"],
                  )
async def cmd_unafk(ctx: CommandContext) -> None:
    summary = await ctx.app.afk.disable(ctx.user_id, notify=False, reason="manual")
    if not summary:
        await ctx.answer(ctx.t("afk.afk_tak_vyklyuchen"))
        return
    await ctx.answer(ctx.t("afk.afk_vyklyuchen_bylo_soobscheniy",
                           d=human_duration(summary["duration"], ctx.lang), m=summary["messages"]))
    if ctx.is_business and summary["messages"]:
        await ctx.app.sender.send_text(ctx.user_id, await ctx.app.afk.summary_text(ctx.user_id, summary, ctx.lang))


@registry.command("sleep", "afk", aliases=["сон", "спать", "uyqu"],
                  )
async def cmd_sleep(ctx: CommandContext) -> None:
    tz_name = ctx.settings.get("timezone") or ctx.app.config.timezone
    arg = ctx.parsed.arg(0)
    hm = parse_hhmm(arg) if arg else (8, 0)
    if hm is None:
        raise UsageError(ctx.t("afk.vremya_formate_chch_mm"))
    ends = next_occurrence(hm[0], hm[1], tz_name)
    await ctx.app.afk.enable(ctx.user_id, ctx.t("afk.son"), kind="sleep", ends_at=ends)
    await ctx.answer(ctx.t("afk.nochnoy_rezhim_spokoynoy_nochi",
                           t=fmt_dt(ends, tz_name, with_date=False)))
