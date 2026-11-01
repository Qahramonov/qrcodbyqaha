"""Plans, subscriptions, limits, trials and promo codes."""
from __future__ import annotations

import logging
import secrets
import time
from typing import Any

from ..database.db import Database, dumps, loads

log = logging.getLogger(__name__)

UNLIMITED = -1
LIMIT_KEYS = ("ai_requests_day", "media_jobs_day", "max_media_mb", "autoreply_rules", "automation_rules",
              "custom_commands", "ai_memory_facts", "ai_profiles", "stt_minutes_day")

DEFAULT_PLANS: list[dict[str, Any]] = [
    {"id": "free", "name": "Free", "price_stars": 0, "duration_days": 0, "sort": 0,
     "description": "Базовые команды, AFK, автоответы, медиа и игры с лимитами",
     "limits": {"ai_requests_day": 20, "media_jobs_day": 15, "max_media_mb": 20, "autoreply_rules": 10,
                "automation_rules": 3, "custom_commands": 3, "ai_memory_facts": 20, "ai_profiles": 2, "stt_minutes_day": 5}},
    {"id": "plus", "name": "Plus", "price_stars": 150, "duration_days": 30, "sort": 1,
     "description": "Больше AI и медиа, AI-режим автоответчика",
     "limits": {"ai_requests_day": 100, "media_jobs_day": 60, "max_media_mb": 20, "autoreply_rules": 40,
                "automation_rules": 15, "custom_commands": 15, "ai_memory_facts": 100, "ai_profiles": 5, "stt_minutes_day": 30}},
    {"id": "pro", "name": "Pro", "price_stars": 350, "duration_days": 30, "sort": 2,
     "description": "Профессиональные лимиты, Hybrid-режим, сравнение моделей",
     "limits": {"ai_requests_day": 400, "media_jobs_day": 200, "max_media_mb": 20, "autoreply_rules": 150,
                "automation_rules": 50, "custom_commands": 50, "ai_memory_facts": 500, "ai_profiles": 15, "stt_minutes_day": 120}},
    {"id": "vip", "name": "VIP", "price_stars": 800, "duration_days": 30, "sort": 3,
     "description": "Максимальные лимиты и приоритет",
     "limits": {"ai_requests_day": 1500, "media_jobs_day": 600, "max_media_mb": 20, "autoreply_rules": UNLIMITED,
                "automation_rules": UNLIMITED, "custom_commands": UNLIMITED, "ai_memory_facts": 2000, "ai_profiles": 50,
                "stt_minutes_day": 480}},
]


class SubscriptionService:
    def __init__(self, db: Database, super_admin_id: int, notifications: Any = None) -> None:
        self.db = db
        self.super_admin_id = int(super_admin_id)
        self.notifications = notifications
        self._plan_cache: dict[int, tuple[float, str]] = {}
        self._plans: dict[str, dict[str, Any]] = {}

    async def seed(self) -> None:
        now = int(time.time())
        for p in DEFAULT_PLANS:
            await self.db.execute(
                "INSERT OR IGNORE INTO subscription_plans(id, name, price_stars, duration_days, limits_json, modules_json, description, "
                "is_active, sort, updated_at) VALUES (?,?,?,?,?,?,?,1,?,?)",
                (p["id"], p["name"], p["price_stars"], p["duration_days"], dumps(p["limits"]), "[]", p["description"], p["sort"], now))
        await self.reload_plans()

    async def reload_plans(self) -> None:
        rows = await self.db.fetchall("SELECT * FROM subscription_plans ORDER BY sort, id")
        self._plans = {}
        for r in rows:
            r["limits"] = loads(r.pop("limits_json"), {})
            r["modules"] = loads(r.pop("modules_json"), [])
            self._plans[r["id"]] = r

    def plans(self, include_inactive: bool = False) -> list[dict[str, Any]]:
        return [p for p in self._plans.values() if include_inactive or p["is_active"]]

    def plan(self, plan_id: str) -> dict[str, Any] | None:
        return self._plans.get(plan_id)

    async def upsert_plan(self, data: dict[str, Any]) -> dict[str, Any]:
        pid = str(data.get("id", "")).strip().lower()
        if not pid or not pid.replace("_", "").isalnum() or len(pid) > 20:
            raise ValueError("invalid plan id")
        limits = data.get("limits") or {}
        bad = [k for k in limits if k not in LIMIT_KEYS]
        if bad:
            raise ValueError(f"unknown limit keys: {bad}")
        price = int(data.get("price_stars", 0))
        days = int(data.get("duration_days", 30))
        if not 0 <= price <= 100000 or not 0 <= days <= 3650:
            raise ValueError("price/duration out of range")
        cur = self._plans.get(pid)
        merged_limits = {**(cur["limits"] if cur else {}), **{k: int(v) for k, v in limits.items()}}
        await self.db.execute(
            "INSERT INTO subscription_plans(id, name, price_stars, duration_days, limits_json, modules_json, description, is_active, sort, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name, price_stars=excluded.price_stars, "
            "duration_days=excluded.duration_days, limits_json=excluded.limits_json, modules_json=excluded.modules_json, "
            "description=excluded.description, is_active=excluded.is_active, sort=excluded.sort, updated_at=excluded.updated_at",
            (pid, str(data.get("name") or (cur or {}).get("name") or pid)[:40], price, days, dumps(merged_limits),
             dumps(data.get("modules", (cur or {}).get("modules", []))), str(data.get("description") or (cur or {}).get("description") or "")[:300],
             1 if data.get("is_active", True) else 0, int(data.get("sort", (cur or {}).get("sort", 10))), int(time.time())))
        await self.reload_plans()
        return self._plans[pid]

    # ---- user plan ---------------------------------------------------------------------
    async def active_subscription(self, user_id: int) -> dict[str, Any] | None:
        return await self.db.fetchone(
            "SELECT * FROM subscriptions WHERE user_id=? AND status='active' AND (expires_at IS NULL OR expires_at > ?) "
            "ORDER BY id DESC LIMIT 1", (user_id, int(time.time())))

    async def plan_of(self, user_id: int) -> str:
        if int(user_id) == self.super_admin_id:
            return "vip"
        cached = self._plan_cache.get(user_id)
        if cached and time.time() - cached[0] < 60:
            return cached[1]
        sub = await self.active_subscription(user_id)
        plan = sub["plan_id"] if sub and sub["plan_id"] in self._plans else "free"
        self._plan_cache[user_id] = (time.time(), plan)
        return plan

    async def limits(self, user_id: int) -> dict[str, int]:
        if int(user_id) == self.super_admin_id:
            return {k: UNLIMITED for k in LIMIT_KEYS}
        plan = self._plans.get(await self.plan_of(user_id)) or self._plans.get("free") or {"limits": {}}
        base = {k: 0 for k in LIMIT_KEYS}
        base.update(plan["limits"])
        return base

    async def limit(self, user_id: int, key: str) -> int | None:
        v = (await self.limits(user_id)).get(key)
        return None if v is None or v == UNLIMITED else int(v)

    def invalidate(self, user_id: int) -> None:
        self._plan_cache.pop(user_id, None)

    # ---- lifecycle -----------------------------------------------------------------------
    async def grant(self, user_id: int, plan_id: str, days: int | None, *, source: str, granted_by: int | None = None,
                    payment_id: int | None = None, note: str | None = None) -> dict[str, Any]:
        if plan_id not in self._plans:
            raise ValueError("unknown plan")
        if source not in ("admin", "payment", "promo", "trial", "referral"):
            raise ValueError("invalid source")
        days = int(days if days is not None else self._plans[plan_id]["duration_days"] or 30)
        if not 0 < days <= 3650:
            raise ValueError("days must be 1..3650")
        now = int(time.time())
        async with self.db.transaction() as tx:
            await tx.execute("INSERT OR IGNORE INTO users(id, created_at) VALUES (?,?)", (user_id, now))
            cur = await tx.fetchone("SELECT * FROM subscriptions WHERE user_id=? AND status='active' AND (expires_at IS NULL OR expires_at > ?) "
                                    "ORDER BY id DESC LIMIT 1", (user_id, now))
            if cur and cur["plan_id"] == plan_id and cur["expires_at"]:
                new_exp = cur["expires_at"] + days * 86400
                await tx.execute("UPDATE subscriptions SET expires_at=?, note=COALESCE(?, note) WHERE id=?", (new_exp, note, cur["id"]))
                sid = cur["id"]
            else:
                if cur:
                    await tx.execute("UPDATE subscriptions SET status='replaced' WHERE id=?", (cur["id"],))
                sid = await tx.execute(
                    "INSERT INTO subscriptions(user_id, plan_id, status, source, started_at, expires_at, granted_by, payment_id, note, created_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?)", (user_id, plan_id, "active", source, now, now + days * 86400, granted_by,
                                                     payment_id, note, now))
        self.invalidate(user_id)
        return await self.db.fetchone("SELECT * FROM subscriptions WHERE id=?", (sid,))  # type: ignore[return-value]

    async def revoke(self, user_id: int, by: int | None = None) -> int:
        n = await self.db.rowcount("UPDATE subscriptions SET status='revoked', note=COALESCE(note,'') || ' revoked by ' || ? "
                                   "WHERE user_id=? AND status='active'", (str(by), user_id))
        self.invalidate(user_id)
        return n

    async def start_trial(self, user_id: int, plan_id: str = "plus", days: int = 3) -> dict[str, Any]:
        had = await self.db.fetchval("SELECT 1 FROM subscriptions WHERE user_id=? AND source='trial'", (user_id,))
        if had:
            raise ValueError("trial already used")
        if await self.plan_of(user_id) != "free":
            raise ValueError("already subscribed")
        return await self.grant(user_id, plan_id, days, source="trial")

    async def history(self, user_id: int) -> list[dict[str, Any]]:
        return await self.db.fetchall("SELECT * FROM subscriptions WHERE user_id=? ORDER BY id DESC LIMIT 50", (user_id,))

    async def expire_due(self) -> list[int]:
        now = int(time.time())
        rows = await self.db.fetchall("SELECT id, user_id FROM subscriptions WHERE status='active' AND expires_at IS NOT NULL AND expires_at <= ?", (now,))
        for r in rows:
            await self.db.execute("UPDATE subscriptions SET status='expired' WHERE id=?", (r["id"],))
            self.invalidate(r["user_id"])
            if self.notifications:
                await self.notifications.notify(r["user_id"], "subscription_expired", "Подписка закончилась / Obuna tugadi",
                                                "Тариф переключён на Free.", level="warning", push=True)
        return [r["user_id"] for r in rows]

    async def expiring_soon(self, within_days: int = 3) -> list[dict[str, Any]]:
        now = int(time.time())
        return await self.db.fetchall("SELECT * FROM subscriptions WHERE status='active' AND expires_at BETWEEN ? AND ?",
                                      (now, now + within_days * 86400))

    # ---- promo codes --------------------------------------------------------------------
    async def create_promo(self, plan_id: str, days: int, max_uses: int = 1, code: str | None = None,
                           expires_at: int | None = None, created_by: int | None = None) -> dict[str, Any]:
        if plan_id not in self._plans:
            raise ValueError("unknown plan")
        if not 1 <= days <= 3650 or not 1 <= max_uses <= 100000:
            raise ValueError("days/max_uses out of range")
        code = (code or ("CH-" + secrets.token_hex(4))).strip().upper()
        if not 4 <= len(code) <= 32 or not all(c.isalnum() or c in "-_" for c in code):
            raise ValueError("invalid code format")
        await self.db.execute("INSERT INTO promo_codes(code, plan_id, days, max_uses, expires_at, created_by, created_at) VALUES (?,?,?,?,?,?,?)",
                              (code, plan_id, days, max_uses, expires_at, created_by, int(time.time())))
        return await self.db.fetchone("SELECT * FROM promo_codes WHERE code=?", (code,))  # type: ignore[return-value]

    async def redeem(self, user_id: int, code: str) -> dict[str, Any]:
        code = (code or "").strip().upper()
        now = int(time.time())
        async with self.db.transaction() as tx:
            promo = await tx.fetchone("SELECT * FROM promo_codes WHERE code=?", (code,))
            if not promo or not promo["is_active"]:
                raise ValueError("invalid code")
            if promo["expires_at"] and promo["expires_at"] < now:
                raise ValueError("code expired")
            if promo["used_count"] >= promo["max_uses"]:
                raise ValueError("code fully used")
            if await tx.fetchval("SELECT 1 FROM promo_redemptions WHERE code=? AND user_id=?", (code, user_id)):
                raise ValueError("code already used by you")
            await tx.execute("INSERT INTO promo_redemptions(code, user_id, redeemed_at) VALUES (?,?,?)", (code, user_id, now))
            await tx.execute("UPDATE promo_codes SET used_count=used_count+1 WHERE code=?", (code,))
        return await self.grant(user_id, promo["plan_id"], promo["days"], source="promo", note=f"promo {code}")

    async def list_promos(self) -> list[dict[str, Any]]:
        return await self.db.fetchall("SELECT * FROM promo_codes ORDER BY created_at DESC LIMIT 200")

    async def disable_promo(self, code: str) -> bool:
        return await self.db.rowcount("UPDATE promo_codes SET is_active=0 WHERE code=?", (code.upper(),)) > 0

    async def stats(self) -> dict[str, Any]:
        now = int(time.time())
        rows = await self.db.fetchall("SELECT plan_id, COUNT(*) AS n FROM subscriptions WHERE status='active' AND "
                                      "(expires_at IS NULL OR expires_at > ?) GROUP BY plan_id", (now,))
        by_plan = {r["plan_id"]: r["n"] for r in rows}
        total_users = await self.db.fetchval("SELECT COUNT(*) FROM users", default=0)
        by_plan["free"] = max(0, total_users - sum(by_plan.values()))
        revenue = await self.db.fetchval("SELECT COALESCE(SUM(amount),0) FROM payments WHERE status='paid' AND currency='XTR'", default=0)
        by_source = {r["source"]: r["n"] for r in await self.db.fetchall(
            "SELECT source, COUNT(*) AS n FROM subscriptions GROUP BY source")}
        return {"active_by_plan": by_plan, "revenue_stars": revenue, "by_source": by_source,
                "expiring_3d": len(await self.expiring_soon(3))}
