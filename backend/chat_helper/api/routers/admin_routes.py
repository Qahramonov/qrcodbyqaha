"""Admin & owner-of-system endpoints: users, subscriptions, payments, broadcasts, analytics, security, system, flags."""
from __future__ import annotations

import json
import time
from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

from ...core.context import MODULES
from ...core.logging import ring_handler
from ...subscriptions.service import LIMIT_KEYS
from ..deps import APIError, Page, Principal, admin, get_app, principal, super_admin

router = APIRouter()


# ---- users -----------------------------------------------------------------------------------

@router.get("/users", tags=["users"])
async def users(q: str | None = None, plan: str | None = None, active_days: int | None = Query(None, ge=1, le=365),
                connected: bool | None = None, status: str | None = None, sort: str = "last_seen", page: Page = Depends(),
                p: Principal = Depends(admin), app: Any = Depends(get_app)) -> dict[str, Any]:
    return await app.users.list(q, plan, active_days, connected, status, sort, page.page, page.page_size)


@router.get("/users/{uid}", tags=["users"])
async def user_detail(uid: int, p: Principal = Depends(principal), app: Any = Depends(get_app)) -> dict[str, Any]:
    if uid != p.user_id and not p.is_admin:
        raise APIError(403, "forbidden", "You can only access your own data")
    u = await app.users.get(uid)
    if u is None:
        raise APIError(404, "not_found", "User not found")
    conns = await app.connections.for_user(uid)
    ai = await app.db.fetchone("SELECT COALESCE(SUM(requests),0) AS requests, COALESCE(SUM(cost_usd),0) AS cost FROM ai_costs WHERE user_id=?", (uid,))
    return {"user": u, "role": await app.users.role(uid), "plan": await app.subs.plan_of(uid), "limits": await app.subs.limits(uid),
            "subscription": await app.subs.active_subscription(uid), "subscriptions": await app.subs.history(uid),
            "connections": [{"id": c.id, "status": c.status, "is_enabled": c.is_enabled, "connected_at": c.connected_at,
                             "last_event_at": c.last_event_at, "rights": c.rights} for c in conns],
            "usage": {"ai_requests_total": ai["requests"], "ai_cost_total": round(ai["cost"], 4),
                      "ai_today": await app.quotas.used(f"ai:{uid}"), "media_today": await app.quotas.used(f"media:{uid}"),
                      "commands_total": await app.db.fetchval("SELECT COUNT(*) FROM command_history WHERE user_id=?", (uid,), 0)},
            "note": "Private chat contents are never exposed to administrators."}


class RestrictIn(BaseModel):
    reason: str = Field(min_length=2, max_length=300)


@router.post("/users/{uid}/restrict", tags=["users"])
async def restrict(uid: int, body: RestrictIn, p: Principal = Depends(admin), app: Any = Depends(get_app)) -> dict[str, Any]:
    if await app.users.role(uid) != "user" and not p.is_super:
        raise APIError(403, "forbidden", "Only the super admin can restrict administrators")
    try:
        await app.users.restrict(uid, body.reason)
    except ValueError as e:
        raise APIError(400, "bad_request", str(e)) from None
    await app.auth.revoke_all(uid, reason="restricted")
    await app.audit.log("user.restrict", actor_id=p.user_id, actor_type="app", target_type="user", target_id=uid, reason=body.reason)
    return {"ok": True}


@router.post("/users/{uid}/restore", tags=["users"])
async def restore(uid: int, p: Principal = Depends(admin), app: Any = Depends(get_app)) -> dict[str, Any]:
    await app.users.restore(uid)
    await app.audit.log("user.restore", actor_id=p.user_id, actor_type="app", target_type="user", target_id=uid)
    return {"ok": True}


class GrantIn(BaseModel):
    plan_id: str
    days: int = Field(ge=1, le=3650)
    note: str | None = Field(default=None, max_length=200)


@router.post("/users/{uid}/subscription", tags=["users"])
async def grant(uid: int, body: GrantIn, p: Principal = Depends(super_admin), app: Any = Depends(get_app)) -> dict[str, Any]:
    sub = await app.subs.grant(uid, body.plan_id, body.days, source="admin", granted_by=p.user_id, note=body.note)
    await app.audit.log("subscription.grant", actor_id=p.user_id, actor_type="app", target_type="user", target_id=uid, plan=body.plan_id, days=body.days)
    await app.notifications.notify(uid, "subscription", "💎 Подписка / Obuna", f"{body.plan_id.upper()} +{body.days}d", push=True)
    return sub


@router.delete("/users/{uid}/subscription", tags=["users"])
async def revoke_sub(uid: int, p: Principal = Depends(super_admin), app: Any = Depends(get_app)) -> dict[str, Any]:
    n = await app.subs.revoke(uid, p.user_id)
    await app.audit.log("subscription.revoke", actor_id=p.user_id, actor_type="app", target_type="user", target_id=uid)
    return {"revoked": n}


class RoleIn(BaseModel):
    role: str = Field(pattern="^(user|moderator)$")


@router.put("/users/{uid}/role", tags=["users"])
async def set_role(uid: int, body: RoleIn, p: Principal = Depends(super_admin), app: Any = Depends(get_app)) -> dict[str, Any]:
    try:
        await app.users.set_role(uid, body.role, p.user_id)
    except ValueError as e:
        raise APIError(400, "bad_request", str(e)) from None
    await app.audit.log("user.role", actor_id=p.user_id, actor_type="app", target_type="user", target_id=uid, role=body.role)
    return {"ok": True}


@router.get("/users/{uid}/audit", tags=["users"])
async def user_audit(uid: int, p: Principal = Depends(admin), app: Any = Depends(get_app)) -> dict[str, Any]:
    return {"items": await app.audit.query(target_type="user", target_id=uid, limit=200)}


# ---- subscriptions -----------------------------------------------------------------------

@router.get("/subscriptions/plans", tags=["subscriptions"])
async def plans(p: Principal = Depends(principal), app: Any = Depends(get_app)) -> dict[str, Any]:
    return {"items": app.subs.plans(include_inactive=p.is_super), "limit_keys": list(LIMIT_KEYS), "payments_enabled": app.payments.enabled}


@router.put("/subscriptions/plans/{plan_id}", tags=["subscriptions"])
async def upsert_plan(plan_id: str, body: dict[str, Any], p: Principal = Depends(super_admin), app: Any = Depends(get_app)) -> dict[str, Any]:
    plan = await app.subs.upsert_plan({**body, "id": plan_id})
    await app.audit.log("plan.upsert", actor_id=p.user_id, actor_type="app", target_type="plan", target_id=plan_id)
    return plan


@router.get("/subscriptions/me", tags=["subscriptions"])
async def my_sub(p: Principal = Depends(principal), app: Any = Depends(get_app)) -> dict[str, Any]:
    return {"plan": await app.subs.plan_of(p.user_id), "subscription": await app.subs.active_subscription(p.user_id),
            "history": await app.subs.history(p.user_id), "limits": await app.subs.limits(p.user_id)}


@router.post("/subscriptions/trial", tags=["subscriptions"])
async def trial(p: Principal = Depends(principal), app: Any = Depends(get_app)) -> dict[str, Any]:
    try:
        return await app.subs.start_trial(p.user_id)
    except ValueError as e:
        raise APIError(409, "trial_unavailable", str(e)) from None


class RedeemIn(BaseModel):
    code: str = Field(min_length=4, max_length=32)


@router.post("/subscriptions/redeem", tags=["subscriptions"])
async def redeem(body: RedeemIn, p: Principal = Depends(principal), app: Any = Depends(get_app)) -> dict[str, Any]:
    ok, retry = app.limiter.check(f"promo:{p.user_id}", 5, 600)
    if not ok:
        raise APIError(429, "rate_limited", "Too many attempts", {"Retry-After": str(retry)})
    try:
        return await app.subs.redeem(p.user_id, body.code)
    except ValueError as e:
        raise APIError(400, "invalid_code", str(e)) from None


class PromoIn(BaseModel):
    plan_id: str
    days: int = Field(ge=1, le=3650)
    max_uses: int = Field(default=1, ge=1, le=100000)
    code: str | None = Field(default=None, max_length=32)
    expires_at: int | None = None


@router.get("/subscriptions/promo", tags=["subscriptions"])
async def promos(p: Principal = Depends(super_admin), app: Any = Depends(get_app)) -> dict[str, Any]:
    return {"items": await app.subs.list_promos()}


@router.post("/subscriptions/promo", tags=["subscriptions"])
async def create_promo(body: PromoIn, p: Principal = Depends(super_admin), app: Any = Depends(get_app)) -> dict[str, Any]:
    promo = await app.subs.create_promo(body.plan_id, body.days, body.max_uses, body.code, body.expires_at, p.user_id)
    await app.audit.log("promo.create", actor_id=p.user_id, actor_type="app", target_type="promo", target_id=promo["code"])
    return promo


@router.delete("/subscriptions/promo/{code}", tags=["subscriptions"])
async def disable_promo(code: str, p: Principal = Depends(super_admin), app: Any = Depends(get_app)) -> dict[str, Any]:
    return {"ok": await app.subs.disable_promo(code)}


@router.get("/subscriptions/stats", tags=["subscriptions"])
async def sub_stats(p: Principal = Depends(admin), app: Any = Depends(get_app)) -> dict[str, Any]:
    return await app.subs.stats()


# ---- payments ------------------------------------------------------------------------------

@router.get("/payments", tags=["payments"])
async def payments(scope: str = "self", p: Principal = Depends(principal), app: Any = Depends(get_app)) -> dict[str, Any]:
    glob = scope == "global" and p.is_super
    return {"items": await app.payments.list(None if glob else p.user_id, 200), "enabled": app.payments.enabled, "currency": "XTR"}


@router.post("/payments/{pid}/refund", tags=["payments"])
async def refund(pid: int, body: dict[str, Any], p: Principal = Depends(super_admin), app: Any = Depends(get_app)) -> dict[str, Any]:
    if body.get("confirm") is not True:
        raise APIError(400, "confirmation_required", "Pass {\"confirm\": true}")
    try:
        ok = await app.payments.refund(pid, p.user_id)
    except Exception as e:
        raise APIError(502, "telegram_error", type(e).__name__) from None
    if not ok:
        raise APIError(404, "not_found", "Paid payment not found")
    return {"ok": True}


# ---- broadcasts ------------------------------------------------------------------------------

class BroadcastIn(BaseModel):
    text: str | None = Field(default=None, max_length=4096)
    media_type: str | None = None
    media_file_id: str | None = None
    buttons: list[dict[str, str]] = Field(default_factory=list)
    segment: dict[str, Any] = Field(default_factory=dict)
    scheduled_at: int | None = None


@router.get("/broadcasts", tags=["broadcast"])
async def broadcasts(p: Principal = Depends(admin), app: Any = Depends(get_app)) -> dict[str, Any]:
    return {"items": await app.broadcast.list(100)}


@router.post("/broadcasts", tags=["broadcast"])
async def create_broadcast(body: BroadcastIn, p: Principal = Depends(super_admin), app: Any = Depends(get_app)) -> dict[str, Any]:
    bid = await app.broadcast.create(p.user_id, body.text, body.media_type, body.media_file_id, body.buttons, body.segment, body.scheduled_at)
    return {"id": bid, "recipients": len(await app.broadcast.recipients(body.segment))}


@router.post("/broadcasts/estimate", tags=["broadcast"])
async def estimate(segment: dict[str, Any], p: Principal = Depends(admin), app: Any = Depends(get_app)) -> dict[str, Any]:
    return {"recipients": len(await app.broadcast.recipients(segment))}


@router.get("/broadcasts/{bid}", tags=["broadcast"])
async def broadcast_detail(bid: int, p: Principal = Depends(admin), app: Any = Depends(get_app)) -> dict[str, Any]:
    b = await app.broadcast.get(bid)
    if b is None:
        raise APIError(404, "not_found", "Broadcast not found")
    b["errors"] = await app.broadcast.errors(bid)
    return b


@router.post("/broadcasts/{bid}/{action}", tags=["broadcast"])
async def broadcast_action(bid: int, action: str, body: dict[str, Any] | None = None, p: Principal = Depends(super_admin),
                           app: Any = Depends(get_app)) -> dict[str, Any]:
    if action == "preview":
        return {"ok": await app.broadcast.preview(bid, p.user_id)}
    if action == "start":
        if not (body or {}).get("confirm"):
            raise APIError(400, "confirmation_required", "Pass {\"confirm\": true}")
        return await app.broadcast.start(bid, p.user_id)
    if action == "cancel":
        return {"ok": await app.broadcast.cancel(bid, p.user_id)}
    raise APIError(404, "not_found", "Unknown action")


# ---- analytics ---------------------------------------------------------------------------------

@router.get("/analytics/overview", tags=["analytics"])
async def analytics(date_from: str | None = Query(None, alias="from"), date_to: str | None = Query(None, alias="to"), scope: str = "auto",
                    p: Principal = Depends(principal), app: Any = Depends(get_app)) -> dict[str, Any]:
    glob = p.is_admin and scope != "self"
    return await app.analytics.overview(date_from, date_to, None if glob else p.user_id)


@router.get("/analytics/export", tags=["analytics"])
async def analytics_export(fmt: str = Query("csv", alias="format", pattern="^(csv|json|pdf)$"), date_from: str | None = Query(None, alias="from"),
                           date_to: str | None = Query(None, alias="to"), scope: str = "auto", p: Principal = Depends(principal),
                           app: Any = Depends(get_app)) -> Response:
    glob = p.is_admin and scope != "self"
    data = await app.analytics.overview(date_from, date_to, None if glob else p.user_id)
    name = f"chat_helper_analytics_{data['from']}_{data['to']}"
    if fmt == "json":
        return Response(json.dumps(data, ensure_ascii=False, indent=1).encode(), media_type="application/json",
                        headers={"Content-Disposition": f'attachment; filename="{name}.json"'})
    if fmt == "pdf":
        return Response(await app.analytics.export_pdf(data), media_type="application/pdf",
                        headers={"Content-Disposition": f'attachment; filename="{name}.pdf"'})
    return Response(await app.analytics.export_csv(data), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{name}.csv"'})


# ---- security ------------------------------------------------------------------------------------

@router.get("/security/sessions", tags=["security"])
async def all_sessions(include_revoked: bool = False, p: Principal = Depends(principal), app: Any = Depends(get_app)) -> dict[str, Any]:
    items = await app.auth.sessions(None if p.is_admin else p.user_id, include_revoked, 300)
    return {"items": items}


@router.delete("/security/sessions/{sid}", tags=["security"])
async def kill_session(sid: int, p: Principal = Depends(principal), app: Any = Depends(get_app)) -> dict[str, Any]:
    from ...auth.service import AuthError
    try:
        ok = await app.auth.revoke(sid, actor_id=p.user_id, actor_role=p.role, reason="revoked_security_center")
    except AuthError as e:
        raise APIError(e.status, e.code, e.message) from None
    return {"ok": ok}


@router.post("/security/revoke-all", tags=["security"])
async def revoke_all(p: Principal = Depends(principal), app: Any = Depends(get_app)) -> dict[str, Any]:
    return {"revoked": await app.auth.revoke_all(p.user_id, except_session=p.session_id)}


@router.get("/security/logins", tags=["security"])
async def logins(p: Principal = Depends(principal), app: Any = Depends(get_app)) -> dict[str, Any]:
    return {"items": await app.auth.login_events(None if p.is_admin else p.user_id, 300)}


@router.get("/security/audit", tags=["security"])
async def audit(action: str | None = None, before_id: int | None = None, p: Principal = Depends(principal), app: Any = Depends(get_app)) -> dict[str, Any]:
    if p.is_admin:
        return {"items": await app.audit.query(action=action, before_id=before_id, limit=200)}
    return {"items": await app.audit.query(actor_id=p.user_id, action=action, before_id=before_id, limit=200)}


@router.get("/security/suspicious", tags=["security"])
async def suspicious(p: Principal = Depends(admin), app: Any = Depends(get_app)) -> dict[str, Any]:
    out = await app.auth.suspicious(24)
    out["loop_guard"] = app.loop_guard.stats()
    out["rate_limiter_blocked"] = app.limiter.blocked
    out["api_errors"] = ring_handler.query(level="ERROR", limit=50)
    return out


@router.get("/security/ratelimits", tags=["security"])
async def ratelimits(p: Principal = Depends(admin), app: Any = Depends(get_app)) -> dict[str, Any]:
    return {"items": app.limiter.snapshot(), "blocked_total": app.limiter.blocked}


class EmergencyIn(BaseModel):
    enabled: bool
    confirm: str = Field(description="Type STOP to enable, RESUME to disable")


@router.post("/security/emergency-stop", tags=["security"])
async def emergency(body: EmergencyIn, p: Principal = Depends(super_admin), app: Any = Depends(get_app)) -> dict[str, Any]:
    expected = "STOP" if body.enabled else "RESUME"
    if body.confirm.strip().upper() != expected:
        raise APIError(400, "confirmation_required", f"Type {expected} to confirm")
    app.runtime.emergency_stop = body.enabled
    await app.runtime.save()
    await app.audit.log("system.emergency_stop", actor_id=p.user_id, actor_type="app", enabled=body.enabled)
    await app.notifications.notify(p.user_id, "security", "Emergency stop " + ("ON" if body.enabled else "OFF"), level="error" if body.enabled else "info")
    return {"emergency_stop": app.runtime.emergency_stop}


# ---- system --------------------------------------------------------------------------------------

@router.get("/system/status", tags=["system"])
async def system_status(p: Principal = Depends(admin), app: Any = Depends(get_app)) -> dict[str, Any]:
    return {"runtime": app.runtime.as_dict(), "resources": app.health.resources(), "scheduler": app.scheduler.status(),
            "media_queue": app.media.queue.status(), "polling": app.polling_active, "config": app.config.public_summary(),
            "sender": {"ok": getattr(app.sender, "sent_ok", 0), "failed": getattr(app.sender, "sent_failed", 0)},
            "ai_queue": {"waiting": app.ai.waiting, "in_flight": app.ai.in_flight}}


@router.get("/system/checks", tags=["system"])
async def system_checks(remote: bool = True, p: Principal = Depends(admin), app: Any = Depends(get_app)) -> dict[str, Any]:
    return await app.health.full(include_remote=remote)


@router.get("/system/logs", tags=["system"])
async def logs(level: str | None = None, q: str | None = None, limit: int = Query(200, ge=1, le=1000), after_id: int = 0,
               p: Principal = Depends(admin)) -> dict[str, Any]:
    return {"items": ring_handler.query(level, q, limit, after_id)}


@router.get("/system/logs/export", tags=["system"])
async def logs_export(p: Principal = Depends(admin), app: Any = Depends(get_app)):
    path = app.config.logs_dir / "chat_helper.log"
    if not path.exists():
        raise APIError(404, "not_found", "No log file yet")
    await app.audit.log("system.logs_export", actor_id=p.user_id, actor_type="app")
    return FileResponse(path, media_type="text/plain", filename="chat_helper.log")


@router.post("/system/cleanup", tags=["system"])
async def cleanup(p: Principal = Depends(admin), app: Any = Depends(get_app)) -> dict[str, Any]:
    removed, freed = app.media.files.cleanup(1800)
    n = await app.dedup.cleanup()
    await app.audit.log("system.cleanup", actor_id=p.user_id, actor_type="app", removed=removed)
    return {"tmp_removed": removed, "freed_bytes": freed, "dedup_removed": n}


@router.post("/system/backup", tags=["system"])
async def backup(body: dict[str, Any], p: Principal = Depends(super_admin), app: Any = Depends(get_app)) -> dict[str, Any]:
    if body.get("confirm") is not True:
        raise APIError(400, "confirmation_required", "Pass {\"confirm\": true}")
    path = await app.backups.create("manual")
    return {"name": path.name, "size": path.stat().st_size}


@router.get("/system/backups", tags=["system"])
async def backups(p: Principal = Depends(super_admin), app: Any = Depends(get_app)) -> dict[str, Any]:
    return {"items": app.backups.list(), "keep": app.config.backup_keep, "interval_hours": app.config.backup_interval_hours}


@router.get("/system/db-integrity", tags=["system"])
async def db_integrity(p: Principal = Depends(admin), app: Any = Depends(get_app)) -> dict[str, Any]:
    from ...database.migrations import current_version
    res = await app.db.integrity_check()
    res.update(await app.db.size_info())
    res["schema_version"] = await current_version(app.db)
    return res


class MaintenanceIn(BaseModel):
    enabled: bool


@router.post("/system/maintenance", tags=["system"])
async def maintenance(body: MaintenanceIn, p: Principal = Depends(super_admin), app: Any = Depends(get_app)) -> dict[str, Any]:
    app.runtime.maintenance = body.enabled
    await app.runtime.save()
    await app.audit.log("system.maintenance", actor_id=p.user_id, actor_type="app", enabled=body.enabled)
    return {"maintenance": body.enabled}


class ModulesIn(BaseModel):
    paused: list[str]


@router.get("/system/modules", tags=["system"])
async def modules(p: Principal = Depends(admin), app: Any = Depends(get_app)) -> dict[str, Any]:
    return {"modules": list(MODULES), "paused": sorted(app.runtime.paused_modules)}


@router.put("/system/modules", tags=["system"])
async def set_modules(body: ModulesIn, p: Principal = Depends(super_admin), app: Any = Depends(get_app)) -> dict[str, Any]:
    app.runtime.paused_modules = {m for m in body.paused if m in MODULES}
    app.media.queue.paused = "media" in app.runtime.paused_modules
    await app.runtime.save()
    await app.audit.log("system.modules", actor_id=p.user_id, actor_type="app", paused=sorted(app.runtime.paused_modules))
    return {"paused": sorted(app.runtime.paused_modules)}


@router.post("/system/restart/{component}", tags=["system"])
async def restart(component: str, p: Principal = Depends(super_admin), app: Any = Depends(get_app)) -> dict[str, Any]:
    if component == "media_queue":
        await app.media.queue.restart()
    elif component == "scheduler":
        await app.scheduler.restart()
    elif component == "ai_clients":
        await app.ai.close()
    else:
        raise APIError(400, "not_supported", "Supported: media_queue, scheduler, ai_clients. Restart the whole process with scripts/restart.sh "
                                              "(an API cannot safely restart its own Python process without an external supervisor).")
    await app.audit.log("system.restart", actor_id=p.user_id, actor_type="app", component=component)
    return {"ok": True, "component": component}


# ---- feature flags --------------------------------------------------------------------------------

class FlagIn(BaseModel):
    enabled: bool
    user_ids: list[int] = Field(default_factory=list)
    description: str | None = Field(default=None, max_length=200)


@router.get("/flags", tags=["flags"])
async def flags(p: Principal = Depends(principal), app: Any = Depends(get_app)) -> dict[str, Any]:
    rows = await app.db.fetchall("SELECT * FROM feature_flags ORDER BY key")
    out = []
    for r in rows:
        ids = json.loads(r["user_ids_json"] or "[]")
        active = bool(r["enabled"]) and (not ids or p.user_id in ids)
        out.append({"key": r["key"], "active_for_me": active, **({"enabled": bool(r["enabled"]), "user_ids": ids, "description": r["description"]}
                                                                 if p.is_super else {})})
    return {"items": out}


@router.put("/flags/{key}", tags=["flags"])
async def set_flag(key: str, body: FlagIn, p: Principal = Depends(super_admin), app: Any = Depends(get_app)) -> dict[str, Any]:
    if not key.replace("_", "").isalnum() or len(key) > 40:
        raise APIError(422, "invalid_key", "Flag key must be alphanumeric")
    await app.db.execute("INSERT INTO feature_flags(key, enabled, user_ids_json, description, updated_at) VALUES (?,?,?,?,?) ON CONFLICT(key) DO UPDATE SET "
                         "enabled=excluded.enabled, user_ids_json=excluded.user_ids_json, description=excluded.description, updated_at=excluded.updated_at",
                         (key, 1 if body.enabled else 0, json.dumps(body.user_ids[:1000]), body.description, int(time.time())))
    await app.audit.log("flag.set", actor_id=p.user_id, actor_type="app", target_type="flag", target_id=key, enabled=body.enabled)
    return {"ok": True}
