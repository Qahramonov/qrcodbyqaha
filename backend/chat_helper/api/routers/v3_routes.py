"""v3 endpoints for Chat helper Control: onboarding, chat controls, mute/protect, AI twin, animations, reminders,
permissions, delegation. Every endpoint is owner-scoped through the session principal; admin endpoints require the
super admin *and* (for user data) an active delegation granted by that user."""
from __future__ import annotations

import time
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from ...ai.service import AIError
from ...ai.twin import LENGTHS, MODES, PERSONAS, STYLES
from ...business.rights import RIGHT_FLAGS, RIGHT_TITLES, command_dependencies, inspect
from ...modules.animations import SPEEDS, TYPE_TITLES, frames_preview
from ...modules.chat_filters import MUTE_TYPES, NOGIF_TYPES
from ...modules.controls import refresh_cards, set_mute
from ...services.delegation import SCOPES
from ...services.settings import ANIM_TYPES
from ..deps import APIError, Principal, get_app, principal, super_admin

router = APIRouter()


# ---- onboarding ------------------------------------------------------------------------------------------------------
@router.get("/onboarding", tags=["onboarding"])
async def onboarding(p: Principal = Depends(principal), app: Any = Depends(get_app)) -> dict[str, Any]:
    conns = await app.connections.for_user(p.user_id)
    enabled = [c for c in conns if c.is_enabled]
    username = getattr(app.bot_info, "username", None)
    return {"connected": bool(enabled), "known_connections": len(conns), "bot_username": username,
            "settings_link": "tg://settings/edit", "is_super_admin": p.is_super,
            "steps": ["copy_username", "open_settings", "chat_automation", "add_bot", "choose_chats", "grant_rights", "check"],
            "recommended_rights": ["can_reply", "can_read_messages", "can_delete_sent_messages", "can_delete_all_messages"],
            "never_grant": ["can_transfer_stars", "can_transfer_and_upgrade_gifts", "can_convert_gifts_to_stars"]}


# ---- chat controls ---------------------------------------------------------------------------------------------------
async def _own_chat(app: Any, uid: int, chat_id: int) -> dict[str, Any]:
    row = await app.chats.get(uid, chat_id)
    if row is None:
        raise APIError(404, "not_found", "Chat not found")
    return row


@router.get("/chats/{chat_id}/controls", tags=["chat-controls"])
async def chat_controls(chat_id: int, p: Principal = Depends(principal), app: Any = Depends(get_app)) -> dict[str, Any]:
    row = await _own_chat(app, p.user_id, chat_id)
    states = await app.controls.states(p.user_id, chat_id)
    out = {}
    for m in ("mute", "protect", "nogif", "nomute"):
        st = states.get(m)
        out[m] = {"enabled": await app.controls.is_on(p.user_id, chat_id, m), "until_at": (st or {}).get("until_at"),
                  "state": {k: v for k, v in ((st or {}).get("state") or {}).items() if not k.startswith("pending")}}
    s = await app.settings.all(p.user_id)
    return {"chat_id": chat_id, "title": row.get("title"), "username": row.get("username"), "modules": out,
            "chat": {"ai_enabled": row.get("ai_enabled"), "afk_enabled": row.get("afk_enabled"), "autoreply_enabled": row.get("autoreply_enabled"),
                     "ignored": bool(row.get("ignored")), "language": row.get("language")},
            "mute_settings": await app.filters.mute_settings(p.user_id, chat_id), "mute_confirm_required": not s.get("mute_confirmed"),
            "media_enabled": bool(s.get("media_enabled", True))}


class ControlIn(BaseModel):
    module: Literal["mute", "protect", "nogif", "nomute"]
    enabled: bool
    until_for: int | None = Field(default=None, ge=60, le=30 * 86400)
    types: list[str] | None = None
    words: list[str] | None = Field(default=None, max_length=50)
    confirm: bool = False


@router.patch("/chats/{chat_id}/controls", tags=["chat-controls"])
async def set_chat_control(chat_id: int, body: ControlIn, p: Principal = Depends(principal), app: Any = Depends(get_app)) -> dict[str, Any]:
    await _own_chat(app, p.user_id, chat_id)
    conn = next((c for c in await app.connections.for_user(p.user_id) if c.is_enabled), None)
    if body.enabled and body.module in ("mute", "nogif", "nomute") and not (conn and conn.can("can_delete_all_messages")):
        raise APIError(409, "missing_right", "Business right «delete incoming messages» (can_delete_all_messages) is required")
    s = await app.settings.all(p.user_id)
    if body.module == "mute":
        if body.enabled and not s.get("mute_confirmed") and not body.confirm:
            raise APIError(409, "confirmation_required", "Mute deletes real messages — confirm first (confirm=true)")
        types = [t for t in (body.types or []) if t in MUTE_TYPES] or None
        await set_mute(app, p.user_id, chat_id, body.enabled, until_for=body.until_for, types=types, conn_id=conn.id if conn else None)
        if body.enabled:
            await app.controls.update_state(p.user_id, chat_id, "mute", confirmed_at=int(time.time()))
    else:
        state: dict[str, Any] = {}
        if body.module == "nogif" and body.types is not None:
            state["types"] = [t for t in body.types if t in NOGIF_TYPES] or ["gif", "sticker"]
        if body.module == "nomute" and body.words is not None:
            state["words"] = [w.strip().lower()[:40] for w in body.words if w.strip()]
        until = int(time.time()) + body.until_for if body.until_for else None
        await app.controls.set(p.user_id, chat_id, body.module, body.enabled, until_at=until, state=state or None,
                               connection_id=conn.id if conn else None)
        await refresh_cards(app, p.user_id, chat_id, body.module)
    await app.audit.log(f"{body.module}.{'enabled' if body.enabled else 'disabled'}", actor_id=p.user_id, target_type="chat",
                        target_id=chat_id, source="api")
    return await chat_controls(chat_id, p, app)


@router.get("/mute", tags=["mute"])
async def mute_overview(p: Principal = Depends(principal), app: Any = Depends(get_app)) -> dict[str, Any]:
    s = await app.settings.all(p.user_id)
    active = [r for r in await app.controls.active(p.user_id) if r["module"] in ("mute", "nogif", "nomute")]
    for r in active:
        r["title"] = ((await app.chats.get(p.user_id, r["chat_id"])) or {}).get("title")
        r["state"] = {k: v for k, v in r["state"].items() if not k.startswith("pending")}
    return {"defaults": await app.filters.mute_settings(p.user_id, 0), "active": active, "types": list(MUTE_TYPES),
            "stats_24h": await app.filters.stats(p.user_id, since=int(time.time()) - 86400),
            "confirm_required": not s.get("mute_confirmed"), "controls_place": s.get("controls_place")}


class MuteSettingsIn(BaseModel):
    types: list[str] | None = None
    keep: list[str] | None = None
    whitelist: list[str] | None = Field(default=None, max_length=30)
    report: bool | None = None
    ask_confirmation: bool | None = None


@router.put("/mute/settings", tags=["mute"])
async def mute_settings(body: MuteSettingsIn, p: Principal = Depends(principal), app: Any = Depends(get_app)) -> dict[str, Any]:
    await app.filters.set_mute_settings(p.user_id, 0, types=body.types, keep=body.keep, whitelist=body.whitelist, report=body.report)
    if body.ask_confirmation is not None:
        await app.settings.set(p.user_id, "mute_confirmed", not body.ask_confirmation)
    return await mute_overview(p, app)


@router.get("/protect", tags=["protect"])
async def protect_overview(p: Principal = Depends(principal), app: Any = Depends(get_app)) -> dict[str, Any]:
    items = await app.controls.active(p.user_id, module="protect")
    return {"items": [{"chat_id": r["chat_id"], "title": ((await app.chats.get(p.user_id, r["chat_id"])) or {}).get("title"),
                       "since": r["updated_at"]} for r in items],
            "note": "Protect applies to messages sent by Chat helper; it does not block screenshots."}


# ---- AI twin ----------------------------------------------------------------------------------------------------------
@router.get("/ai/twin", tags=["ai-twin"])
async def twin_get(p: Principal = Depends(principal), app: Any = Depends(get_app)) -> dict[str, Any]:
    prof = await app.twin.get(p.user_id)
    return {"profile": prof, "options": {"modes": list(MODES), "lengths": list(LENGTHS), "personas": list(PERSONAS), "styles": list(STYLES)}}


class TwinIn(BaseModel):
    mode: str | None = None
    name: str | None = Field(default=None, max_length=60)
    language: str | None = None
    manner: str | None = Field(default=None, max_length=500)
    style: str | None = None
    formality: int | None = Field(default=None, ge=0, le=100)
    humor: int | None = Field(default=None, ge=0, le=100)
    length: str | None = None
    emoji: int | None = Field(default=None, ge=0, le=100)
    slang: int | None = Field(default=None, ge=0, le=100)
    profanity_filter: bool | None = None
    reply_delay_sec: int | None = Field(default=None, ge=0, le=300)
    active_from: str | None = None
    active_to: str | None = None
    model: str | None = Field(default=None, max_length=60)
    custom_prompt: str | None = Field(default=None, max_length=2000)
    persona: str | None = None


@router.put("/ai/twin", tags=["ai-twin"])
async def twin_put(body: TwinIn, p: Principal = Depends(principal), app: Any = Depends(get_app)) -> dict[str, Any]:
    try:
        await app.twin.update(p.user_id, **body.model_dump(exclude_unset=True))
    except ValueError as e:
        raise APIError(422, "validation_error", str(e)) from None
    return await twin_get(p, app)


class TextIn(BaseModel):
    text: str = Field(min_length=1, max_length=1000)


@router.post("/ai/twin/examples", tags=["ai-twin"])
async def twin_example(body: TextIn, p: Principal = Depends(principal), app: Any = Depends(get_app)) -> dict[str, Any]:
    try:
        n = await app.twin.add_example(p.user_id, body.text)
    except ValueError as e:
        raise APIError(422, "validation_error", str(e)) from None
    return {"examples": n}


@router.delete("/ai/twin/examples", tags=["ai-twin"])
async def twin_examples_clear(p: Principal = Depends(principal), app: Any = Depends(get_app)) -> dict[str, Any]:
    await app.twin.clear_examples(p.user_id)
    return {"ok": True}


@router.post("/ai/twin/preview", tags=["ai-twin"])
async def twin_preview(body: TextIn, p: Principal = Depends(principal), app: Any = Depends(get_app)) -> dict[str, Any]:
    if not app.ai.available():
        raise APIError(409, "ai_not_configured", "No AI provider configured")
    try:
        return {"reply": await app.twin.preview(p.user_id, body.text, await app.settings.all(p.user_id)), "sent": False}
    except AIError as e:
        raise APIError(502, e.code, str(e)) from None


# ---- animations -------------------------------------------------------------------------------------------------------
@router.get("/animations", tags=["animations"])
async def animations(p: Principal = Depends(principal), app: Any = Depends(get_app)) -> dict[str, Any]:
    s = await app.settings.all(p.user_id)
    lang = s["lang"]
    return {"types": [{"id": k, "title": TYPE_TITLES[k][1 if lang == "uz" else 0]} for k in ANIM_TYPES],
            "speeds": [{"id": k, "interval_sec": v[0], "frames": v[1]} for k, v in SPEEDS.items()],
            "defaults": {"type": s["anim_type"], "speed": s["anim_speed"], "repeats": s["anim_repeats"]},
            "recent": await app.db.fetchall("SELECT kind, speed, frames, status, created_at FROM animation_jobs WHERE owner_id=? "
                                            "ORDER BY id DESC LIMIT 10", (p.user_id,))}


class AnimSettingsIn(BaseModel):
    type: str | None = None
    speed: str | None = None
    repeats: int | None = Field(default=None, ge=1, le=3)


@router.put("/animations/settings", tags=["animations"])
async def animation_settings(body: AnimSettingsIn, p: Principal = Depends(principal), app: Any = Depends(get_app)) -> dict[str, Any]:
    vals = {}
    if body.type is not None:
        if body.type not in ANIM_TYPES:
            raise APIError(422, "validation_error", "unknown animation type")
        vals["anim_type"] = body.type
    if body.speed is not None:
        if body.speed not in SPEEDS:
            raise APIError(422, "validation_error", "unknown speed")
        vals["anim_speed"] = body.speed
    if body.repeats is not None:
        vals["anim_repeats"] = body.repeats
    if vals:
        await app.settings.update(p.user_id, vals)
    return await animations(p, app)


class AnimPreviewIn(BaseModel):
    kind: str
    text: str = Field(min_length=1, max_length=200)


@router.post("/animations/preview", tags=["animations"])
async def animation_preview(body: AnimPreviewIn, p: Principal = Depends(principal)) -> dict[str, Any]:
    if body.kind not in ANIM_TYPES or body.kind == "custom":
        raise APIError(422, "validation_error", "unknown animation type")
    return {"frames": frames_preview(body.kind, body.text)}


# ---- reminders --------------------------------------------------------------------------------------------------------
@router.get("/reminders", tags=["reminders"])
async def reminders(p: Principal = Depends(principal), app: Any = Depends(get_app), status: str = Query("pending")) -> dict[str, Any]:
    return {"items": await app.reminders.list(p.user_id, None if status == "all" else status)}


class ReminderIn(BaseModel):
    text: str = Field(min_length=1, max_length=1000)
    in_sec: int = Field(ge=30, le=365 * 86400)


@router.post("/reminders", tags=["reminders"])
async def reminder_create(body: ReminderIn, p: Principal = Depends(principal), app: Any = Depends(get_app)) -> dict[str, Any]:
    try:
        return await app.reminders.create(p.user_id, body.text, int(time.time()) + body.in_sec)
    except ValueError as e:
        raise APIError(422, "validation_error", str(e)) from None


@router.delete("/reminders/{rid}", tags=["reminders"])
async def reminder_cancel(rid: int, p: Principal = Depends(principal), app: Any = Depends(get_app)) -> dict[str, Any]:
    if not await app.reminders.cancel(p.user_id, rid):
        raise APIError(404, "not_found", "Reminder not found or already done")
    return {"ok": True}


# ---- permissions --------------------------------------------------------------------------------------------------------
@router.get("/permissions", tags=["permissions"])
async def permissions(p: Principal = Depends(principal), app: Any = Depends(get_app)) -> dict[str, Any]:
    s = await app.settings.all(p.user_id)
    lang = s["lang"]
    deps = command_dependencies(app.registry)
    out = []
    for c in await app.connections.for_user(p.user_id):
        snap = await app.db.fetchone("SELECT created_at FROM permission_snapshots WHERE connection_id=? ORDER BY id DESC LIMIT 1", (c.id,))
        rep = inspect(c.rights, c.is_enabled, lang, c.paused)
        out.append({"connection_id": c.id, "status": c.status, "status_title": rep["status_title"], "is_enabled": c.is_enabled,
                    "last_update": (snap or {}).get("created_at") or c.connected_at,
                    "rights": [{"right": r, "title": RIGHT_TITLES[r][1 if lang == "uz" else 0], "granted": bool(c.rights.get(r)),
                                "commands": deps.get(r, [])} for r in RIGHT_FLAGS],
                    "capabilities": rep["capabilities"], "advice": rep["advice"]})
    return {"connections": out}


# ---- delegation -----------------------------------------------------------------------------------------------------------
@router.get("/delegation", tags=["delegation"])
async def delegation(p: Principal = Depends(principal), app: Any = Depends(get_app)) -> dict[str, Any]:
    s = await app.settings.all(p.user_id)
    g = await app.delegation.grants(p.user_id)
    return {"scopes": [{"scope": k, "title": v[1 if s["lang"] == "uz" else 0], "granted": bool(g.get(k, {}).get("active")),
                        "expires_at": g.get(k, {}).get("expires_at")} for k, v in SCOPES.items()],
            "history": await app.delegation.history(p.user_id, 30)}


class DelegationIn(BaseModel):
    granted: bool
    days: int | None = Field(default=None, ge=1, le=365)


@router.put("/delegation/{scope}", tags=["delegation"])
async def delegation_set(scope: str, body: DelegationIn, p: Principal = Depends(principal), app: Any = Depends(get_app)) -> dict[str, Any]:
    if scope not in SCOPES:
        raise APIError(404, "not_found", "Unknown scope")
    if body.granted:
        await app.delegation.grant(p.user_id, scope, body.days)
    else:
        await app.delegation.revoke(p.user_id, scope)
    return await delegation(p, app)


@router.get("/admin/delegated/{uid}", tags=["delegation"])
async def admin_delegated(uid: int, p: Principal = Depends(super_admin), app: Any = Depends(get_app)) -> dict[str, Any]:
    from ...services.delegation import SCOPE_KEYS
    g = await app.delegation.grants(uid)
    active = [k for k, v in g.items() if v["active"]]
    data: dict[str, Any] = {"user_id": uid, "granted": active}
    if active:
        s = await app.settings.all(uid)
        data["settings"] = {k: s.get(k) for scope in active for k in SCOPE_KEYS.get(scope, ())}
    if "diagnostics" in active:
        data["diagnostics"] = {"connections": [{"status": c.status, "is_enabled": c.is_enabled, "rights": c.rights}
                                               for c in await app.connections.for_user(uid)]}
    return data


class DelegatedSettingsIn(BaseModel):
    values: dict[str, Any]


@router.patch("/admin/delegated/{uid}/settings", tags=["delegation"])
async def admin_delegated_settings(uid: int, body: DelegatedSettingsIn, p: Principal = Depends(super_admin),
                                   app: Any = Depends(get_app)) -> dict[str, Any]:
    try:
        await app.delegation.admin_update_settings(p.user_id, uid, body.values)
    except PermissionError as e:
        raise APIError(403, "not_delegated", str(e)) from None
    return await admin_delegated(uid, p, app)


class ProfileRequestIn(BaseModel):
    field: Literal["name", "bio"]
    value: str = Field(min_length=1, max_length=140)


@router.post("/admin/delegated/{uid}/profile-request", tags=["delegation"])
async def admin_profile_request(uid: int, body: ProfileRequestIn, p: Principal = Depends(super_admin),
                                app: Any = Depends(get_app)) -> dict[str, Any]:
    try:
        rid = await app.delegation.request_profile_change(p.user_id, uid, body.field, body.value)
    except PermissionError as e:
        raise APIError(403, "not_delegated", str(e)) from None
    return {"request_id": rid, "status": "waiting_for_user_confirmation"}


@router.get("/admin/chat-controls", tags=["chat-controls"])
async def admin_controls(p: Principal = Depends(super_admin), app: Any = Depends(get_app)) -> dict[str, Any]:
    since = int(time.time()) - 86400
    rows = await app.db.fetchall("SELECT source, result, COUNT(*) AS n FROM mute_events WHERE created_at>=? GROUP BY source, result", (since,))
    return {"active": await app.controls.counts(),
            "cards": await app.db.fetchval("SELECT COUNT(*) FROM control_messages WHERE status='active'", default=0),
            "filter_events_24h": rows}
