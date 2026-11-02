"""Owner-scoped endpoints: dashboard, settings, AFK, connections, chats, notifications, live events, inbox."""
from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from ... import __version__
from ...business.rights import inspect
from ...core.timeutil import today
from ...modules.afk import render_afk
from ...services.settings import SettingsError, schema_for_api
from ..deps import APIError, Page, Principal, get_app, principal

router = APIRouter()

CHANGELOG = [
    {"version": "1.0.0", "date": "2026-11-01", "items": [
        "Telegram Business engine (connections, rights, multi-account isolation)",
        "Command engine with 150+ commands, AFK, Smart Auto Reply, No-code automation",
        "AI Ultra Engine (OpenAI, Gemini, Anthropic, OpenAI-compatible) with memory, drafts and playground",
        "Media Studio (FFmpeg/Pillow) with job queue, Voice Studio, Mini games, Text tools",
        "Chat helper Control Android app with secure pairing"]},
]


@router.get("/dashboard", tags=["dashboard"])
async def dashboard(p: Principal = Depends(principal), app: Any = Depends(get_app), scope: str = Query("auto")) -> dict[str, Any]:
    glob = p.is_admin and scope != "self"
    uid = 0 if glob else p.user_id
    m = app.metrics
    d = today()

    async def tot(metric: str) -> float:
        return await m.total(metric, uid, d)
    data: dict[str, Any] = {
        "scope": "global" if glob else "self", "version": __version__, "generated_at": int(time.time()),
        "bot": {"polling": app.polling_active, "username": getattr(app.bot_info, "username", None), "emergency_stop": app.runtime.emergency_stop,
                "maintenance": app.runtime.maintenance},
        "backend": {"uptime_sec": app.uptime, "status": "ok"},
        "today": {"messages_in": await tot("messages_in"), "messages_out": await tot("messages_out"), "auto_replies": await tot("auto_replies"),
                  "commands": await tot("commands"), "ai_requests": await tot("ai_requests"), "ai_cost_usd": round(await tot("ai_cost_usd"), 5),
                  "media_jobs": await tot("media_jobs"), "errors": await tot("errors"), "games": await tot("games_played")},
        "charts": {"messages": await m.series("messages_in", 14, uid), "ai_requests": await m.series("ai_requests", 14, uid),
                   "ai_cost": await m.series("ai_cost_usd", 14, uid), "errors": await m.series("errors", 14, uid),
                   "commands": await m.series("commands", 14, uid)},
        "media_queue": app.media.queue.status(),
        "recent_events": app.events.since(0, p.user_id, glob, 15),
    }
    if glob:
        data["users"] = {"total": await app.users.count(),
                         "active_today": await app.db.fetchval("SELECT COUNT(*) FROM user_activity WHERE day=?", (d,), 0)}
        data["connections"] = await app.connections.counts()
        data["subscriptions"] = await app.subs.stats()
        data["resources"] = app.health.resources()
        data["charts"]["active_users"] = [{"day": x["day"], "value": x["value"]} for x in
                                          (await app.analytics.active_series(*app.analytics.range(None, None, 14)))["dau"]]
        data["module_usage"] = await app.analytics.module_usage(*app.analytics.range(None, None, 14))
    else:
        conns = await app.connections.for_user(p.user_id)
        data["connections"] = {"total": len(conns), "active": sum(1 for c in conns if c.is_enabled),
                               "status": conns[0].status if conns else "none"}
        afk = await app.afk.active(p.user_id)
        s = await app.settings.all(p.user_id)
        data["me"] = {"mode": s["mode"], "afk": bool(afk), "automation_paused": s["automation_paused"], "plan": await app.subs.plan_of(p.user_id)}
        data["unanswered"] = len(await app.inbox.unanswered(p.user_id, 100))
    return data


# ---- settings ---------------------------------------------------------------------------

class SettingsPatch(BaseModel):
    values: dict[str, Any] = Field(default_factory=dict)


@router.get("/settings", tags=["settings"])
async def get_settings(p: Principal = Depends(principal), app: Any = Depends(get_app)) -> dict[str, Any]:
    return {"values": await app.settings.all(p.user_id), "schema": schema_for_api()}


@router.patch("/settings", tags=["settings"])
async def patch_settings(body: SettingsPatch, p: Principal = Depends(principal), app: Any = Depends(get_app)) -> dict[str, Any]:
    values = dict(body.values)
    mode = values.pop("mode", None)
    try:
        if values:
            await app.settings.update(p.user_id, values)
        if mode is not None:
            await app.autoreply.set_mode(p.user_id, mode)
    except (SettingsError, ValueError) as e:
        raise APIError(422, "invalid_setting", str(e)) from None
    if "clock_enabled" in values:
        await app.profile.on_clock_toggled(p.user_id, bool(values["clock_enabled"]))
    await app.audit.log("settings.update", actor_id=p.user_id, actor_type="app", target_type="settings", keys=list(body.values))
    return {"values": await app.settings.all(p.user_id)}


# ---- AFK ------------------------------------------------------------------------------------

class AfkIn(BaseModel):
    reason: str | None = Field(default=None, max_length=300)
    minutes: int | None = Field(default=None, ge=1, le=43200)
    kind: str = Field(default="afk", pattern="^(afk|sleep)$")


@router.get("/afk", tags=["afk"])
async def afk_status(p: Principal = Depends(principal), app: Any = Depends(get_app)) -> dict[str, Any]:
    return {"active": await app.afk.active(p.user_id), "stats": await app.afk.stats(p.user_id)}


@router.post("/afk/enable", tags=["afk"])
async def afk_enable(body: AfkIn, p: Principal = Depends(principal), app: Any = Depends(get_app)) -> dict[str, Any]:
    sess = await app.afk.enable(p.user_id, body.reason, body.minutes * 60 if body.minutes else None, kind=body.kind)
    return {"active": sess}


@router.post("/afk/disable", tags=["afk"])
async def afk_disable(p: Principal = Depends(principal), app: Any = Depends(get_app)) -> dict[str, Any]:
    return {"summary": await app.afk.disable(p.user_id, reason="manual")}


@router.get("/afk/history", tags=["afk"])
async def afk_history(p: Principal = Depends(principal), app: Any = Depends(get_app)) -> dict[str, Any]:
    return {"items": await app.afk.history(p.user_id, 50)}


@router.get("/afk/preview", tags=["afk"])
async def afk_preview(theme: str = Query("classic"), p: Principal = Depends(principal), app: Any = Depends(get_app)) -> dict[str, Any]:
    s = await app.settings.all(p.user_id)
    if theme not in ("classic", "minimal", "fancy", "emoji"):
        raise APIError(422, "invalid_theme", "Unknown theme")
    from ...core.timeutil import day_part
    sess = await app.afk.active(p.user_id) or {}
    user = await app.users.get(p.user_id) or {}
    html = render_afk(theme, s["lang"], name=user.get("first_name") or "Owner", reason=sess.get("reason") or "…",
                      away=int(time.time() - sess.get("started_at", time.time() - 3600)), until_ts=sess.get("ends_at"),
                      tz_name=s["timezone"], part=day_part(s["timezone"]))
    return {"html": html}


# ---- business connections --------------------------------------------------------------

async def _own_conn(app: Any, p: Principal, conn_id: str):
    conn = await app.connections.get(conn_id)
    if conn is None or (conn.user_id != p.user_id and not p.is_admin):
        raise APIError(404, "not_found", "Connection not found")
    return conn


@router.get("/connections", tags=["connections"])
async def connections(all: bool = False, p: Principal = Depends(principal), app: Any = Depends(get_app)) -> dict[str, Any]:
    conns = await app.connections.all() if (all and p.is_admin) else await app.connections.for_user(p.user_id)
    s = await app.settings.all(p.user_id)
    items = []
    for c in conns:
        rep = inspect(c.rights, c.is_enabled, s["lang"], c.paused)
        u = await app.users.get(c.user_id) or {}
        items.append({**c.as_dict(), "status_title": rep["status_title"], "username": u.get("username"),
                      "available_modules": sum(1 for x in rep["capabilities"] if x["available"]),
                      "total_modules": len(rep["capabilities"])})
    return {"items": items}


@router.get("/connections/{conn_id}/inspector", tags=["connections"])
async def inspector(conn_id: str, p: Principal = Depends(principal), app: Any = Depends(get_app)) -> dict[str, Any]:
    conn = await _own_conn(app, p, conn_id)
    s = await app.settings.all(p.user_id)
    rep = inspect(conn.rights, conn.is_enabled, s["lang"], conn.paused)
    cmd_issues = []
    for spec in app.registry.visible(admin=p.is_super):
        missing = [r for r in spec.rights if not conn.rights.get(r)]
        if missing:
            cmd_issues.append({"command": spec.id, "missing_rights": missing})
    rep["commands_blocked"] = cmd_issues
    return rep


@router.post("/connections/{conn_id}/refresh", tags=["connections"])
async def refresh_conn(conn_id: str, p: Principal = Depends(principal), app: Any = Depends(get_app)) -> dict[str, Any]:
    conn = await _own_conn(app, p, conn_id)
    if app.bot is None:
        raise APIError(503, "bot_unavailable", "Telegram bot is not running")
    try:
        bc = await app.bot.get_business_connection(business_connection_id=conn.id)
        ch = await app.connections.upsert(bc.id, bc.user.id, bc.user_chat_id, bc.is_enabled, bc.rights)
        return {"connection": ch.conn.as_dict(), "change": ch.kind}
    except Exception as e:
        await app.connections.mark_status(conn.id, "reconnection_required")
        raise APIError(502, "telegram_error", f"Telegram: {type(e).__name__}") from None


@router.post("/connections/{conn_id}/{action}", tags=["connections"])
async def pause_conn(conn_id: str, action: str, p: Principal = Depends(principal), app: Any = Depends(get_app)) -> dict[str, Any]:
    if action not in ("pause", "resume"):
        raise APIError(404, "not_found", "Unknown action")
    conn = await _own_conn(app, p, conn_id)
    res = await app.connections.set_paused(conn.id, conn.user_id, action == "pause")
    await app.audit.log(f"connection.{action}", actor_id=p.user_id, actor_type="app", target_type="connection", target_id=conn.id)
    return {"connection": res.as_dict() if res else None}


# ---- chats -----------------------------------------------------------------------------------

class ChatPatch(BaseModel):
    ai_enabled: bool | None = None
    afk_enabled: bool | None = None
    autoreply_enabled: bool | None = None
    language: str | None = Field(default=None, max_length=8)
    style: str | None = Field(default=None, max_length=16)
    reply_limit: int | None = Field(default=None, ge=0, le=500)
    priority: int | None = Field(default=None, ge=-5, le=5)
    manual_confirm: bool | None = None
    muted_until: int | None = None
    ignored: bool | None = None
    whitelisted: bool | None = None
    tags: list[str] | None = None


@router.get("/chats", tags=["chats"])
async def chats(q: str | None = None, sort: str = "recent", unanswered: bool = False, page: Page = Depends(),
                p: Principal = Depends(principal), app: Any = Depends(get_app)) -> dict[str, Any]:
    return await app.chats.list(p.user_id, q, sort, page.page, page.page_size, unanswered)


@router.get("/chats/{chat_id}", tags=["chats"])
async def chat(chat_id: int, p: Principal = Depends(principal), app: Any = Depends(get_app)) -> dict[str, Any]:
    row = await app.chats.get(p.user_id, chat_id)
    if row is None:
        raise APIError(404, "not_found", "Chat not found")
    row["ai_context"] = await app.ai.memory.chat_stats(p.user_id, chat_id)
    row["auto_replies_today"] = await app.chats.auto_replies_today(p.user_id, chat_id)
    return row


@router.patch("/chats/{chat_id}", tags=["chats"])
async def patch_chat(chat_id: int, body: ChatPatch, p: Principal = Depends(principal), app: Any = Depends(get_app)) -> dict[str, Any]:
    values = body.model_dump(exclude_unset=True)
    row = await app.chats.update(p.user_id, chat_id, values)
    if row is None:
        raise APIError(404, "not_found", "Chat not found")
    return row


@router.delete("/chats/{chat_id}/data", tags=["chats"])
async def delete_chat_data(chat_id: int, p: Principal = Depends(principal), app: Any = Depends(get_app)) -> dict[str, Any]:
    await app.chats.delete_data(p.user_id, chat_id)
    await app.audit.log("chat.delete_data", actor_id=p.user_id, actor_type="app", target_type="chat", target_id=chat_id)
    return {"ok": True}


@router.delete("/chats/{chat_id}/history", tags=["chats"])
async def clear_chat_history(chat_id: int, p: Principal = Depends(principal), app: Any = Depends(get_app)) -> dict[str, Any]:
    return {"deleted": await app.ai.memory.clear_chat(p.user_id, chat_id)}


@router.get("/inbox", tags=["chats"])
async def inbox(p: Principal = Depends(principal), app: Any = Depends(get_app)) -> dict[str, Any]:
    return {"items": await app.inbox.unanswered(p.user_id, 50)}


# ---- notifications & live monitor -------------------------------------------------------

class ReadIn(BaseModel):
    ids: list[int] | None = None


@router.get("/notifications", tags=["notifications"])
async def notifications(unread: bool = False, p: Principal = Depends(principal), app: Any = Depends(get_app)) -> dict[str, Any]:
    return {"items": await app.notifications.list(p.user_id, unread, 200), "unread": await app.notifications.unread_count(p.user_id)}


@router.post("/notifications/read", tags=["notifications"])
async def notifications_read(body: ReadIn, p: Principal = Depends(principal), app: Any = Depends(get_app)) -> dict[str, Any]:
    return {"updated": await app.notifications.mark_read(p.user_id, body.ids)}


@router.get("/events", tags=["live"])
async def events(after_id: int = 0, p: Principal = Depends(principal), app: Any = Depends(get_app)) -> dict[str, Any]:
    return {"items": app.events.since(after_id, p.user_id, p.is_admin, 200), "last_id": app.events.last_id}


@router.get("/changelog", tags=["system"])
async def changelog(p: Principal = Depends(principal)) -> dict[str, Any]:
    return {"items": CHANGELOG}


class SupportIn(BaseModel):
    message: str = Field(min_length=3, max_length=2000)


@router.post("/support", tags=["system"])
async def support(body: SupportIn, p: Principal = Depends(principal), app: Any = Depends(get_app)) -> dict[str, Any]:
    ok, retry = app.limiter.check(f"support:{p.user_id}", 3, 3600)
    if not ok:
        raise APIError(429, "rate_limited", "Too many support messages", {"Retry-After": str(retry)})
    await app.support_message(p.user_id, body.message)
    return {"ok": True}


@router.get("/export", tags=["privacy"])
async def export_me(p: Principal = Depends(principal), app: Any = Depends(get_app)) -> dict[str, Any]:
    await app.audit.log("privacy.export", actor_id=p.user_id, actor_type="app", target_type="user", target_id=p.user_id)
    return await app.backups.export_user(p.user_id)
