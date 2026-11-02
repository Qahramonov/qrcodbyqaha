"""aiogram handlers for Telegram Business updates."""
from __future__ import annotations

import logging
import time

from aiogram import Router
from aiogram.types import BusinessConnection, BusinessMessagesDeleted, Message

from ..business.rights import inspect, right_title, status_title
from ..core.context import AppContext
from ..localization import tr
from ..security.sanitize import esc

log = logging.getLogger(__name__)
router = Router(name="business")


def _rights_lines(rights: list[str], lang: str) -> str:
    return "\n".join("• " + right_title(r, lang) for r in rights)


@router.business_connection()
async def on_business_connection(bc: BusinessConnection, app: AppContext) -> None:
    u = bc.user
    await app.users.upsert(u.id, u.username, u.first_name, u.last_name, u.language_code, touch=True)
    app.pipeline.forget_owner_name(u.id)
    change = await app.connections.upsert(bc.id, u.id, bc.user_chat_id, bc.is_enabled, bc.rights,
                                          int(bc.date.timestamp()) if hasattr(bc.date, "timestamp") else None)
    conn = change.conn
    if change.kind != "unchanged":
        from ..database.db import dumps
        await app.db.execute("INSERT INTO permission_snapshots(connection_id, owner_id, is_enabled, rights_json, status, change, created_at) "
                             "VALUES (?,?,?,?,?,?,?)", (bc.id, u.id, 1 if conn.is_enabled else 0, dumps(conn.rights), conn.status, change.kind,
                                                       int(time.time())))
    settings = await app.settings.all(u.id)
    lang = settings["lang"]
    app.events.emit("business_connection", user_id=u.id, kind=change.kind, status=conn.status)
    await app.audit.log(f"business.{change.kind}", actor_id=u.id, actor_type="telegram", target_type="connection",
                        target_id=bc.id, status=conn.status)
    if change.kind == "new" or change.kind == "enabled":
        await app.metrics.incr("connections_new", u.id)
        report = inspect(conn.rights, conn.is_enabled, lang)
        lines = [tr(lang, "business.akkaunt_podklyuchyon_chat_helper"),
                 tr(lang, "business.status", s=report["status_title"]), ""]
        avail = [c for c in report["capabilities"] if c["available"]]
        missing = [c for c in report["capabilities"] if not c["available"]]
        if avail:
            lines.append(tr(lang, "business.dostupno"))
            lines += ["• " + c["description"] for c in avail]
        if missing:
            lines.append("")
            lines.append(tr(lang, "business.nedostupno_bez_prav"))
            lines += ["• " + c["description"] for c in missing]
        lines.append("")
        lines += ["ℹ️ " + a for a in report["advice"]]
        lines.append("")
        lines.append(tr(lang, "business.pishite_komandy_pryamo_chatah_naprimer",
                        p=settings["prefix"]))
        await app.notifications.notify(u.id, "connection", tr(lang, "business.novoe_biznes_podklyuchenie"),
                                       report["status_title"])
        from ..keyboards import kb
        await app.sender.send_text(u.id, "\n".join(lines), markup=kb([
            [(tr(lang, "business.otkryt_menyu"), "m:home"), (tr(lang, "business.prava"), "conn:insp:0")]]))
        if u.id != app.config.super_admin_id:
            await app.notifications.notify(app.config.super_admin_id, "connection_admin",
                                           "New business connection", f"user {u.id} (@{u.username or '-'}) → {conn.status}")
    elif change.kind == "disabled":
        await app.metrics.incr("connections_lost", u.id)
        await app.controls.revoke_connection(bc.id)   # old control buttons stop working
        await app.notifications.notify(u.id, "disconnect", tr(lang, "business.biznes_podklyuchenie_otklyucheno"),
                                       level="warning")
        if settings.get("notify_disconnect", True):
            from ..keyboards import kb
            await app.sender.send_text(u.id, tr(lang, "business.chat_helper_otklyuchyon_vashego_akkaunta"),
                                       markup=kb([[(tr(lang, "business.kak_podklyuchit_snova"), "m:connect")]]))
    elif change.kind == "rights_changed":
        lines = [tr(lang, "business.prava_biznes_bota_izmeneny"),
                 tr(lang, "business.status", s=status_title(conn.status, lang))]
        if change.added_rights:
            lines += ["", tr(lang, "business.dobavleno"), _rights_lines(change.added_rights, lang)]
        if change.removed_rights:
            lines += ["", tr(lang, "business.otozvano"), _rights_lines(change.removed_rights, lang)]
        await app.notifications.notify(u.id, "rights", tr(lang, "business.prava_izmeneny"), conn.status)
        await app.sender.send_text(u.id, "\n".join(lines))


async def _conn_for(app: AppContext, bc_id: str | None):
    if not bc_id:
        return None
    conn = await app.connections.get(bc_id)
    if conn is None:
        # unknown connection (e.g. DB restored): fetch it from Telegram once
        try:
            bc = await app.bot.get_business_connection(business_connection_id=bc_id)
            await on_business_connection(bc, app)
            conn = await app.connections.get(bc_id)
        except Exception:
            log.warning("unknown business connection could not be fetched")
            return None
    return conn


@router.business_message()
async def on_business_message(message: Message, app: AppContext) -> None:
    conn = await _conn_for(app, message.business_connection_id)
    if conn is None:
        return
    try:
        await app.pipeline.on_message(conn, message)
    except Exception:
        log.exception("business message pipeline failed")
        await app.metrics.incr("errors", conn.user_id)


@router.edited_business_message()
async def on_edited_business_message(message: Message, app: AppContext) -> None:
    conn = await _conn_for(app, message.business_connection_id)
    if conn is None:
        return
    try:
        await app.pipeline.on_edited(conn, message)
    except Exception:
        log.exception("edited business message failed")


@router.deleted_business_messages()
async def on_deleted_business_messages(event: BusinessMessagesDeleted, app: AppContext) -> None:
    conn = await _conn_for(app, event.business_connection_id)
    if conn is None:
        return
    await app.pipeline.on_deleted(conn, event.chat.id, list(event.message_ids))


def describe_owner(u) -> str:  # pragma: no cover - helper for logs
    return esc(f"{u.first_name} (@{u.username})" if u.username else u.first_name)
