"""Profile Manager for the connected business account (official setBusinessAccount* methods only).
Every change shows a preview and needs confirmation; history and backups are kept."""
from __future__ import annotations

import io
import logging
import time
from typing import TYPE_CHECKING, Any

from aiogram.exceptions import TelegramRetryAfter
from aiogram.types import BufferedInputFile, CallbackQuery, InputProfilePhotoStatic, Message

from ..commands.context import CommandContext, CommandError, UsageError
from ..commands.registry import LIMITED_BY_TELEGRAM, NOT_SUPPORTED, registry
from ..core.timeutil import local_dt
from ..database.db import dumps, loads
from ..keyboards import kb
from ..localization import p, tr
from ..security.sanitize import esc

if TYPE_CHECKING:  # pragma: no cover
    from ..core.context import AppContext

log = logging.getLogger(__name__)
FIELD_RIGHT = {"name": "can_edit_name", "bio": "can_edit_bio", "avatar": "can_edit_profile_photo", "restore": "can_edit_name"}


class ProfileService:
    def __init__(self, app: "AppContext") -> None:
        self.app = app
        self.pending: dict[int, dict[str, Any]] = {}
        self._cache: dict[int, tuple[float, dict[str, Any]]] = {}
        self._clock_next: dict[int, float] = {}

    async def current(self, uid: int, fresh: bool = False) -> dict[str, Any]:
        c = self._cache.get(uid)
        if c and not fresh and time.time() - c[0] < 120:
            return c[1]
        info: dict[str, Any] = {}
        u = await self.app.users.get(uid) or {}
        info.update({"first_name": u.get("first_name"), "last_name": u.get("last_name"), "username": u.get("username")})
        if self.app.bot is not None:
            try:
                chat = await self.app.bot.get_chat(uid)
                info.update({"first_name": chat.first_name, "last_name": chat.last_name, "bio": chat.bio, "username": chat.username})
            except Exception:
                pass
        self._cache[uid] = (time.time(), info)
        return info

    async def _settings_blob(self, uid: int, module: str) -> dict[str, Any]:
        row = await self.app.db.fetchone("SELECT config_json FROM module_settings WHERE user_id=? AND module=?", (uid, module))
        return loads(row["config_json"], {}) if row else {}

    async def _save_blob(self, uid: int, module: str, data: dict[str, Any]) -> None:
        await self.app.db.execute(
            "INSERT INTO module_settings(user_id, module, enabled, config_json, updated_at) VALUES (?,?,1,?,?) "
            "ON CONFLICT(user_id, module) DO UPDATE SET config_json=excluded.config_json, updated_at=excluded.updated_at",
            (uid, module, dumps(data), int(time.time())))

    async def backup(self, uid: int) -> dict[str, Any] | None:
        info = await self.current(uid, fresh=True)
        snap = {"first_name": info.get("first_name"), "last_name": info.get("last_name"), "bio": info.get("bio"), "ts": int(time.time())}
        await self._save_blob(uid, "profile_backup", snap)
        await self._history(uid, "backup", None, f"{snap['first_name']} {snap['last_name'] or ''} | {snap['bio'] or ''}", "backup")
        return snap

    async def history(self, uid: int, limit: int = 20) -> list[dict[str, Any]]:
        return await self.app.db.fetchall("SELECT * FROM profile_history WHERE user_id=? ORDER BY id DESC LIMIT ?", (uid, limit))

    async def _history(self, uid: int, field: str, old: str | None, new: str | None, source: str) -> None:
        await self.app.db.execute("INSERT INTO profile_history(user_id, field, old_value, new_value, source, created_at) VALUES (?,?,?,?,?,?)",
                                  (uid, field, (old or "")[:500], (new or "")[:500], source, int(time.time())))

    async def propose(self, uid: int, field: str, values: dict[str, Any], target: Message | None = None) -> None:
        s = await self.app.settings.all(uid)
        lang = s["lang"]
        conn = await self.app.connections.primary_for_user(uid)
        if conn is None or not conn.is_enabled:
            await self.app.sender.send_text(uid, tr(lang, "profile.snachala_podklyuchite_biznes_akkaunt"))
            return
        if not conn.can(FIELD_RIGHT[field]):
            await self.app.sender.send_text(uid, tr(lang, "profile.net_prava_izmenenie_vklyuchite_ego"))
            return
        if field == "name" and not (values.get("first_name") or "").strip():
            await self.app.sender.send_text(uid, tr(lang, "profile.imya_mozhet_byt_pustym"))
            return
        if field == "bio" and len(values.get("bio") or "") > 140:
            await self.app.sender.send_text(uid, tr(lang, "profile.bio_maksimum_140_simvolov"))
            return
        cur = await self.current(uid)
        self.pending[uid] = {"field": field, "values": values, "conn": conn.id, "ts": time.time(), "old": cur}
        if field == "name":
            preview = f"{esc(values['first_name'])} {esc(values.get('last_name') or '')}"
            before = f"{esc(cur.get('first_name') or '')} {esc(cur.get('last_name') or '')}"
        elif field == "bio":
            preview, before = esc(values.get("bio") or "—"), esc(cur.get("bio") or "—")
        elif field == "restore":
            preview = f"{esc(values.get('first_name') or '')} {esc(values.get('last_name') or '')} | {esc(values.get('bio') or '—')}"
            before = f"{esc(cur.get('first_name') or '')} {esc(cur.get('last_name') or '')} | {esc(cur.get('bio') or '—')}"
        else:
            preview, before = tr(lang, "profile.novoe_foto_profilya"), tr(lang, "profile.tekuschee_foto")
        text = tr(lang, "profile.predprosmotr_izmeneniya_profilya_bylo_stanet", b=before, a=preview)
        markup = kb([[(p(lang, "confirm"), "pr:ok"), (p(lang, "cancel"), "pr:no")]])
        if field == "avatar":
            await self.app.sender.send_media(uid, "photo", values["file_id"], caption=text, markup=markup)
        else:
            await self.app.sender.send_text(uid, text, markup=markup)

    async def confirm_callback(self, uid: int, cb: CallbackQuery, ok: bool) -> None:
        item = self.pending.pop(uid, None)
        lang = (await self.app.settings.all(uid))["lang"]
        if not item or time.time() - item["ts"] > 600:
            await cb.answer("⌛")
            return
        if not ok:
            await cb.answer("✖️")
            try:
                await cb.message.edit_reply_markup(reply_markup=None)
            except Exception:
                pass
            return
        try:
            await self.apply(uid, item, "manual")
            await cb.answer(p(lang, "done"), show_alert=False)
            await self.app.sender.send_text(uid, tr(lang, "profile.profil_obnovlyon"))
        except Exception as e:
            await cb.answer(tr(lang, "profile.oshibka", e=str(e)[:150]), show_alert=True)
        try:
            await cb.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass

    async def apply(self, uid: int, item: dict[str, Any], source: str) -> None:
        conn = await self.app.connections.get(item["conn"])
        if conn is None or conn.user_id != uid:
            raise PermissionError("connection mismatch")
        bot = self.app.bot
        field, v, old = item["field"], item["values"], item.get("old") or {}
        if field in ("name", "restore"):
            await bot.set_business_account_name(business_connection_id=conn.id, first_name=v["first_name"][:64],
                                                last_name=(v.get("last_name") or None))
            await self._history(uid, "name", f"{old.get('first_name') or ''} {old.get('last_name') or ''}",
                                f"{v['first_name']} {v.get('last_name') or ''}", source)
        if field == "bio" or (field == "restore" and "bio" in v and conn.can("can_edit_bio")):
            await bot.set_business_account_bio(business_connection_id=conn.id, bio=v.get("bio") or "")
            await self._history(uid, "bio", old.get("bio"), v.get("bio"), source)
        if field == "avatar":
            buf = io.BytesIO()
            await bot.download(v["file_id"], destination=buf)
            await bot.set_business_account_profile_photo(business_connection_id=conn.id,
                                                         photo=InputProfilePhotoStatic(photo=BufferedInputFile(buf.getvalue(), "avatar.jpg")))
            await self._history(uid, "avatar", None, "new photo", source)
        self._cache.pop(uid, None)
        await self.app.audit.log(f"profile.{field}", actor_id=uid, target_type="user", target_id=uid, source=source)

    async def apply_change(self, uid: int, field: str, value: str, source: str) -> bool:
        """Apply an already-confirmed name/bio change (delegation flow). False if rights or connection are missing."""
        conn = await self.app.connections.primary_for_user(uid)
        if conn is None or not conn.is_enabled or field not in ("name", "bio") or not conn.can(FIELD_RIGHT[field]):
            return False
        values = {"first_name": value[:64]} if field == "name" else {"bio": value[:140]}
        await self.apply(uid, {"field": field, "values": values, "conn": conn.id, "old": await self.current(uid)}, source)
        return True

    async def restore_flow(self, uid: int, target: Message) -> None:
        snap = await self._settings_blob(uid, "profile_backup")
        lang = (await self.app.settings.all(uid))["lang"]
        if not snap:
            await self.app.sender.send_text(uid, tr(lang, "profile.rezervnoy_kopii_net_nazhmite_bekap"))
            return
        await self.propose(uid, "restore", {"first_name": snap.get("first_name") or "", "last_name": snap.get("last_name"), "bio": snap.get("bio")}, target)

    # ---- profile clock -----------------------------------------------------------------
    async def on_clock_toggled(self, uid: int, enabled: bool) -> None:
        if enabled:
            await self.backup(uid)
            self._clock_next[uid] = 0
            return
        snap = await self._settings_blob(uid, "profile_backup")
        conn = await self.app.connections.primary_for_user(uid)
        if not snap or conn is None:
            return
        s = await self.app.settings.all(uid)
        try:
            if s["clock_field"] == "bio" and conn.can("can_edit_bio"):
                await self.app.bot.set_business_account_bio(business_connection_id=conn.id, bio=snap.get("bio") or "")
            elif s["clock_field"] == "last_name" and conn.can("can_edit_name"):
                await self.app.bot.set_business_account_name(business_connection_id=conn.id, first_name=snap.get("first_name") or "-",
                                                             last_name=snap.get("last_name"))
        except Exception as e:
            log.info("clock restore failed: %s", type(e).__name__)

    async def clock_tick(self) -> int:
        """Updates the profile clock no more often than the user's interval (min 15 min) to respect Telegram limits."""
        rows = await self.app.db.fetchall("SELECT user_id FROM user_settings WHERE key='clock_enabled' AND value_json='true'")
        n = 0
        for r in rows:
            uid = r["user_id"]
            if time.time() < self._clock_next.get(uid, 0):
                continue
            s = await self.app.settings.all(uid)
            conn = await self.app.connections.primary_for_user(uid)
            if conn is None or not conn.active:
                continue
            right = "can_edit_bio" if s["clock_field"] == "bio" else "can_edit_name"
            if not conn.can(right):
                continue
            stamp = local_dt(None, s.get("timezone") or self.app.config.timezone).strftime("%H:%M")
            text = (s.get("clock_format") or "🕒 {time}").replace("{time}", stamp)[:64]
            try:
                if s["clock_field"] == "bio":
                    snap = await self._settings_blob(uid, "profile_backup")
                    base = (snap.get("bio") or "").strip()
                    bio = (f"{text} · {base}" if base else text)[:140]
                    await self.app.bot.set_business_account_bio(business_connection_id=conn.id, bio=bio)
                else:
                    info = await self.current(uid)
                    await self.app.bot.set_business_account_name(business_connection_id=conn.id, first_name=info.get("first_name") or "-",
                                                                 last_name=text)
                self._clock_next[uid] = time.time() + max(15, int(s["clock_interval_min"])) * 60
                n += 1
            except TelegramRetryAfter as e:
                self._clock_next[uid] = time.time() + e.retry_after + 60
                log.info("profile clock flood wait %ss for a user", e.retry_after)
            except Exception as e:
                self._clock_next[uid] = time.time() + 3600
                log.info("profile clock failed: %s", type(e).__name__)
        return n


# ------------------------------------------------------------------------------------------------
# commands
# ------------------------------------------------------------------------------------------------

@registry.command("profile", "profile", aliases=["профиль", "profil"], )
async def cmd_profile(ctx: CommandContext) -> None:
    r = ctx.reply
    if r is not None and r.from_user is not None and r.from_user.id != ctx.user_id:
        u = r.from_user
        await ctx.answer(ctx.t("profile.id_pokazany_tolko_publichnye_dannye",
                               n=esc(u.full_name), un=esc(u.username or "—"), i=u.id), private=True)
        return
    info = await ctx.app.profile.current(ctx.user_id, fresh=True)
    await ctx.answer(ctx.t("profile.text", f=esc(info.get("first_name") or ""),
                           l=esc(info.get("last_name") or ""), u=esc(info.get("username") or "—"), b=esc(info.get("bio") or "—")), private=True)


@registry.command("name", "profile", aliases=["имя", "ism"], rights=["can_edit_name"], status=LIMITED_BY_TELEGRAM)
async def cmd_name(ctx: CommandContext) -> None:
    if not ctx.raw:
        raise UsageError()
    parts = [x.strip() for x in ctx.raw.split("|", 1)]
    await ctx.app.profile.propose(ctx.user_id, "name", {"first_name": parts[0][:64], "last_name": parts[1][:64] if len(parts) > 1 else ""})
    await ctx.cleanup_command(fallback_text="👤")
    if not ctx.is_business:
        return


@registry.command("bio", "profile", aliases=["био"], rights=["can_edit_bio"], status=LIMITED_BY_TELEGRAM)
async def cmd_bio(ctx: CommandContext) -> None:
    if not ctx.raw:
        raise UsageError()
    await ctx.app.profile.propose(ctx.user_id, "bio", {"bio": "" if ctx.raw.strip() == "-" else ctx.raw.strip()})
    await ctx.cleanup_command(fallback_text="👤")


@registry.command("avatar", "profile", aliases=["аватар", "ava"], rights=["can_edit_profile_photo"], status=LIMITED_BY_TELEGRAM)
async def cmd_avatar(ctx: CommandContext) -> None:
    from .media_util import require_media
    ref = require_media(ctx, image=True)
    if ref.kind != "photo":
        raise CommandError(ctx.t("profile.nuzhna_fotografiya_fayl"))
    await ctx.app.profile.propose(ctx.user_id, "avatar", {"file_id": ref.file_id})
    await ctx.cleanup_command(fallback_text="👤")


@registry.command("clock", "profile", aliases=["часы", "soat"],
                  status=LIMITED_BY_TELEGRAM, )
async def cmd_clock(ctx: CommandContext) -> None:
    sub = ctx.parsed.first
    s = ctx.app.settings
    if sub in ("on", "off"):
        await s.set(ctx.user_id, "clock_enabled", sub == "on")
        await ctx.app.profile.on_clock_toggled(ctx.user_id, sub == "on")
    elif sub in ("bio", "last_name"):
        await s.set(ctx.user_id, "clock_field", sub)
    elif sub == "interval" and len(ctx.args) > 1 and ctx.args[1].isdigit():
        try:
            await s.set(ctx.user_id, "clock_interval_min", int(ctx.args[1]))
        except ValueError as e:
            raise CommandError(str(e)) from None
    elif sub == "format" and len(ctx.raw.split(None, 1)) > 1:
        fmt = ctx.raw.split(None, 1)[1][:64]
        if "{time}" not in fmt:
            raise UsageError(ctx.t("profile.format_dolzhen_soderzhat"))
        await s.set(ctx.user_id, "clock_format", fmt)
    elif sub:
        raise UsageError()
    st = await s.all(ctx.user_id)
    await ctx.answer(ctx.t("profile.chasy_pole_kazhdye_min_format",
                           on="on" if st["clock_enabled"] else "off", f=st["clock_field"], i=st["clock_interval_min"], fm=esc(st["clock_format"])),
                     private=True)


@registry.command("profile_backup", "profile", aliases=["бэкаппрофиля", "pbackup"], )
async def cmd_profile_backup(ctx: CommandContext) -> None:
    snap = await ctx.app.profile.backup(ctx.user_id)
    await ctx.answer(ctx.t("profile.sohraneno", f=esc(snap.get("first_name") or ""), l=esc(snap.get("last_name") or ""),
                           b=esc(snap.get("bio") or "—")), private=True)


@registry.command("profile_restore", "profile", aliases=["восстановитьпрофиль", "prestore"], rights=["can_edit_name"])
async def cmd_profile_restore(ctx: CommandContext) -> None:
    await ctx.app.profile.restore_flow(ctx.user_id, ctx.message)  # type: ignore[arg-type]
    await ctx.cleanup_command(fallback_text="👤")


@registry.command("online", "profile", aliases=["онлайн", "offline", "оффлайн"],
                  status=NOT_SUPPORTED, sandbox_safe=True)
async def cmd_online(ctx: CommandContext) -> None:
    if ctx.source == "sandbox":
        await ctx.answer(ctx.t("profile.status_seti_upravlyaetsya_bot_api"))
        return
    from .controls import post_card
    await post_card(ctx.app, ctx.user_id, ctx.chat_id if ctx.is_business else ctx.user_id, "online",
                    conn=ctx.conn if ctx.is_business else None, ctx=ctx if ctx.is_business else None, location="dm")