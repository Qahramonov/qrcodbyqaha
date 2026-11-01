"""/api/v1/auth/* and /api/v1/health."""
from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from ... import APP_NAME, __version__
from ...auth.service import AuthError
from ..deps import APIError, Principal, client_ip, get_app, principal

router = APIRouter(tags=["auth"])


class PairIn(BaseModel):
    code: str = Field(min_length=4, max_length=16)
    device_id: str = Field(min_length=4, max_length=64)
    device_name: str | None = Field(default=None, max_length=64)
    platform: str | None = Field(default="android", max_length=32)
    app_version: str | None = Field(default=None, max_length=16)


class RefreshIn(BaseModel):
    refresh_token: str = Field(min_length=10, max_length=160)


@router.get("/health")
async def health(app: Any = Depends(get_app)) -> dict[str, Any]:
    return {"status": "ok", "name": APP_NAME, "version": __version__, "time": int(time.time()), "api": "v1",
            "bot_polling": bool(app.polling_active), "maintenance": app.runtime.maintenance}


async def _me(app: Any, uid: int, role: str) -> dict[str, Any]:
    user = await app.users.get(uid) or {"id": uid}
    plan = await app.subs.plan_of(uid)
    conns = await app.connections.for_user(uid)
    caps = ["dashboard", "settings", "afk", "ai", "autoreply", "automation", "chats", "commands", "media", "games", "connections",
            "notifications", "analytics_self", "security_self", "subscription"]
    if role == "super_admin":  # v3: admin capabilities only for the configured super admin
        caps += ["users", "analytics_global", "system", "security_admin", "broadcast_view",
                 "subscriptions_admin", "payments_admin", "broadcast", "ai_system", "flags", "emergency_stop", "backups"]
    return {"user": {k: user.get(k) for k in ("id", "username", "first_name", "last_name", "language", "status", "created_at", "last_seen_at")},
            "role": role, "plan": plan, "limits": await app.subs.limits(uid), "capabilities": caps,
            "connections": [{"id": c.id, "status": c.status, "is_enabled": c.is_enabled} for c in conns],
            "settings": await app.settings.all(uid), "server": {"name": APP_NAME, "version": __version__}}


@router.post("/auth/pair")
async def pair(body: PairIn, request: Request, app: Any = Depends(get_app)) -> dict[str, Any]:
    try:
        tokens = await app.auth.pair(body.code, device_id=body.device_id, device_name=body.device_name, platform=body.platform,
                                     app_version=body.app_version, ip=client_ip(request))
    except AuthError as e:
        raise APIError(e.status, e.code, e.message, {"Retry-After": str(e.retry_after)} if e.retry_after else None) from None
    tokens["me"] = await _me(app, tokens["user_id"], tokens["role"])
    return tokens


@router.post("/auth/refresh")
async def refresh(body: RefreshIn, request: Request, app: Any = Depends(get_app)) -> dict[str, Any]:
    try:
        return await app.auth.refresh(body.refresh_token, client_ip(request))
    except AuthError as e:
        raise APIError(e.status, e.code, e.message) from None


@router.post("/auth/logout")
async def logout(p: Principal = Depends(principal), app: Any = Depends(get_app)) -> dict[str, Any]:
    await app.auth.revoke(p.session_id, actor_id=p.user_id, actor_role=p.role, reason="logout")
    return {"ok": True}


@router.get("/auth/me")
async def me(p: Principal = Depends(principal), app: Any = Depends(get_app)) -> dict[str, Any]:
    out = await _me(app, p.user_id, p.role)
    out["session"] = {"id": p.session_id, "device_name": p.device_name}
    return out


@router.get("/auth/sessions")
async def sessions(p: Principal = Depends(principal), app: Any = Depends(get_app)) -> dict[str, Any]:
    items = await app.auth.sessions(p.user_id)
    for s in items:
        s["current"] = s["id"] == p.session_id
    return {"items": items}


@router.delete("/auth/sessions/{session_id}")
async def revoke_session(session_id: int, p: Principal = Depends(principal), app: Any = Depends(get_app)) -> dict[str, Any]:
    try:
        ok = await app.auth.revoke(session_id, actor_id=p.user_id, actor_role=p.role, reason="revoked_in_app")
    except AuthError as e:
        raise APIError(e.status, e.code, e.message) from None
    if not ok:
        raise APIError(404, "not_found", "Session not found")
    return {"ok": True}
