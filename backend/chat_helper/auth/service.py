"""APK authentication: one-time pairing codes issued in Telegram → hashed, rotating session tokens.

* Codes: 8 random chars (32^8 ≈ 10^12), TTL 5 min, single use, stored as HMAC-SHA256 only.
* Tokens: opaque random strings; only HMAC hashes are stored; access 1h / refresh 30d with rotation.
* Brute force: per-IP sliding windows + global lockout on mass failures; every attempt is logged.
* The Telegram user id is NEVER taken from the client — it comes from the code issued via the bot.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
import time
from dataclasses import dataclass
from typing import Any

from ..database.db import Database

log = logging.getLogger(__name__)

ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
MAX_SESSIONS_PER_USER = 10


class AuthError(Exception):
    def __init__(self, code: str, message: str, status: int = 401, retry_after: int | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.retry_after = retry_after


@dataclass
class Session:
    id: int
    user_id: int
    role: str
    device_id: str
    device_name: str | None
    created_at: int
    access_expires_at: int


def normalize_code(code: str) -> str:
    return "".join(c for c in (code or "").upper() if c in ALPHABET)


class AuthService:
    def __init__(self, db: Database, secret: str, users: Any, limiter: Any, audit: Any, notifications: Any = None,
                 access_ttl: int = 3600, refresh_ttl: int = 30 * 86400, code_ttl: int = 300) -> None:
        self.db = db
        self.secret = secret.encode()
        self.users = users
        self.limiter = limiter
        self.audit = audit
        self.notifications = notifications
        self.access_ttl = access_ttl
        self.refresh_ttl = refresh_ttl
        self.code_ttl = code_ttl
        self._lockout_until = 0.0
        self._touch_cache: dict[int, float] = {}

    def _h(self, value: str) -> str:
        return hmac.new(self.secret, value.encode(), hashlib.sha256).hexdigest()

    # ---- pairing codes ------------------------------------------------------------------
    async def create_pairing_code(self, user_id: int) -> tuple[str, int]:
        ok, retry = self.limiter.check(f"paircode:{user_id}", 6, 3600)
        if not ok:
            raise AuthError("too_many_codes", "Too many codes requested", 429, retry)
        raw = "".join(secrets.choice(ALPHABET) for _ in range(8))
        now = int(time.time())
        expires = now + self.code_ttl
        async with self.db.transaction() as tx:
            await tx.execute("UPDATE pairing_codes SET used_at=? WHERE user_id=? AND used_at IS NULL", (now, user_id))
            await tx.execute("INSERT INTO pairing_codes(user_id, code_hash, created_at, expires_at) VALUES (?,?,?,?)",
                             (user_id, self._h(raw), now, expires))
        await self.audit.log("auth.code_issued", actor_id=user_id, target_type="user", target_id=user_id)
        return f"{raw[:4]}-{raw[4:]}", expires

    async def _fail(self, ip: str, reason: str, device_name: str | None = None, user_id: int | None = None) -> None:
        await self.db.execute("INSERT INTO login_events(user_id, ip, device_name, success, reason, created_at) VALUES (?,?,?,?,?,?)",
                              (user_id, ip, (device_name or "")[:64], 0, reason, int(time.time())))
        fails = await self.db.fetchval("SELECT COUNT(*) FROM login_events WHERE success=0 AND created_at > ?",
                                       (int(time.time()) - 600,), 0)
        if fails >= 50 and time.time() > self._lockout_until:
            self._lockout_until = time.time() + 900
            log.warning("pairing locked for 15 min after %s failures", fails)
            if self.notifications:
                await self.notifications.notify(self.users.super_admin_id, "security", "Pairing lockout",
                                                f"{fails} failed APK pairing attempts in 10 minutes. Pairing disabled for 15 minutes.",
                                                level="error", push=True)

    async def pair(self, code: str, *, device_id: str, device_name: str | None, platform: str | None,
                   app_version: str | None, ip: str) -> dict[str, Any]:
        if time.time() < self._lockout_until:
            raise AuthError("locked", "Pairing temporarily locked", 429, int(self._lockout_until - time.time()))
        for key, limit, window in ((f"pair:ip:{ip}", 5, 60), (f"pair:ip_h:{ip}", 20, 3600)):
            ok, retry = self.limiter.check(key, limit, window)
            if not ok:
                await self._fail(ip, "rate_limited", device_name)
                raise AuthError("rate_limited", "Too many attempts", 429, retry)
        norm = normalize_code(code)
        if len(norm) != 8:
            await self._fail(ip, "bad_format", device_name)
            raise AuthError("invalid_code", "Invalid or expired code")
        h = self._h(norm)
        now = int(time.time())
        async with self.db.transaction() as tx:
            row = await tx.fetchone("SELECT * FROM pairing_codes WHERE code_hash=?", (h,))
            if row is not None:
                await tx.execute("UPDATE pairing_codes SET attempts=attempts+1 WHERE id=?", (row["id"],))
            valid = row is not None and row["used_at"] is None and row["expires_at"] >= now
            if valid:
                await tx.execute("UPDATE pairing_codes SET used_at=? WHERE id=? AND used_at IS NULL", (now, row["id"]))
        if not valid:
            await self._fail(ip, "invalid_or_expired", device_name, row["user_id"] if row else None)
            raise AuthError("invalid_code", "Invalid or expired code")
        user_id = int(row["user_id"])
        if await self.users.is_restricted(user_id):
            await self._fail(ip, "restricted", device_name, user_id)
            raise AuthError("restricted", "Account access is restricted", 403)
        tokens = await self._create_session(user_id, device_id, device_name, platform, app_version, ip)
        await self.db.execute("INSERT INTO login_events(user_id, ip, device_name, success, reason, created_at) VALUES (?,?,?,?,?,?)",
                              (user_id, ip, (device_name or "")[:64], 1, "paired", now))
        await self.audit.log("auth.paired", actor_id=user_id, target_type="session", target_id=tokens["session_id"], ip=ip,
                             device=device_name)
        if self.notifications:
            await self.notifications.notify_t(user_id, "security", "notify.new_device", body=f"Chat helper Control: {device_name or device_id}",
                                              level="warning", push=True)
        return tokens

    async def _create_session(self, user_id: int, device_id: str, device_name: str | None, platform: str | None,
                              app_version: str | None, ip: str) -> dict[str, Any]:
        access = "cha_" + secrets.token_urlsafe(32)
        refresh = "chr_" + secrets.token_urlsafe(48)
        now = int(time.time())
        async with self.db.transaction() as tx:
            sid = await tx.execute(
                "INSERT INTO admin_sessions(user_id, device_id, device_name, platform, app_version, access_hash, refresh_hash, created_at, "
                "last_used_at, last_ip, access_expires_at, refresh_expires_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (user_id, (device_id or "unknown")[:64], (device_name or "")[:64] or None, (platform or "")[:32] or None,
                 (app_version or "")[:16] or None, self._h(access), self._h(refresh), now, now, ip,
                 now + self.access_ttl, now + self.refresh_ttl))
            active = await tx.fetchall("SELECT id FROM admin_sessions WHERE user_id=? AND revoked_at IS NULL ORDER BY id DESC", (user_id,))
            for old in active[MAX_SESSIONS_PER_USER:]:
                await tx.execute("UPDATE admin_sessions SET revoked_at=?, revoke_reason='session_limit' WHERE id=?", (now, old["id"]))
        role = await self.users.role(user_id)
        return {"session_id": sid, "access_token": access, "refresh_token": refresh, "token_type": "bearer",
                "expires_in": self.access_ttl, "refresh_expires_in": self.refresh_ttl, "user_id": user_id, "role": role}

    # ---- token checks ------------------------------------------------------------------
    async def authenticate(self, access_token: str, ip: str | None = None) -> Session:
        if not access_token or not access_token.startswith("cha_") or len(access_token) > 128:
            raise AuthError("invalid_token", "Invalid token")
        row = await self.db.fetchone("SELECT * FROM admin_sessions WHERE access_hash=?", (self._h(access_token),))
        now = int(time.time())
        if row is None or row["revoked_at"] is not None:
            raise AuthError("invalid_token", "Invalid or revoked token")
        if row["access_expires_at"] < now:
            raise AuthError("token_expired", "Access token expired")
        if await self.users.is_restricted(row["user_id"]):
            raise AuthError("restricted", "Account access is restricted", 403)
        if now - self._touch_cache.get(row["id"], 0) > 60:
            self._touch_cache[row["id"]] = now
            await self.db.execute("UPDATE admin_sessions SET last_used_at=?, last_ip=? WHERE id=?", (now, ip, row["id"]))
        return Session(id=row["id"], user_id=row["user_id"], role=await self.users.role(row["user_id"]),
                       device_id=row["device_id"], device_name=row["device_name"], created_at=row["created_at"],
                       access_expires_at=row["access_expires_at"])

    async def refresh(self, refresh_token: str, ip: str) -> dict[str, Any]:
        ok, retry = self.limiter.check(f"refresh:ip:{ip}", 30, 60)
        if not ok:
            raise AuthError("rate_limited", "Too many attempts", 429, retry)
        if not refresh_token or not refresh_token.startswith("chr_") or len(refresh_token) > 160:
            raise AuthError("invalid_token", "Invalid refresh token")
        row = await self.db.fetchone("SELECT * FROM admin_sessions WHERE refresh_hash=?", (self._h(refresh_token),))
        now = int(time.time())
        if row is None or row["revoked_at"] is not None or row["refresh_expires_at"] < now:
            raise AuthError("invalid_token", "Session expired. Pair the app again.")
        if await self.users.is_restricted(row["user_id"]):
            raise AuthError("restricted", "Account access is restricted", 403)
        access = "cha_" + secrets.token_urlsafe(32)
        new_refresh = "chr_" + secrets.token_urlsafe(48)
        n = await self.db.rowcount(
            "UPDATE admin_sessions SET access_hash=?, refresh_hash=?, access_expires_at=?, refresh_expires_at=?, last_used_at=?, last_ip=? "
            "WHERE id=? AND refresh_hash=? AND revoked_at IS NULL",
            (self._h(access), self._h(new_refresh), now + self.access_ttl, now + self.refresh_ttl, now, ip, row["id"],
             self._h(refresh_token)))
        if n != 1:
            raise AuthError("invalid_token", "Refresh token already used")
        return {"session_id": row["id"], "access_token": access, "refresh_token": new_refresh, "token_type": "bearer",
                "expires_in": self.access_ttl, "refresh_expires_in": self.refresh_ttl, "user_id": row["user_id"],
                "role": await self.users.role(row["user_id"])}

    async def revoke(self, session_id: int, *, actor_id: int, actor_role: str, reason: str = "revoked") -> bool:
        row = await self.db.fetchone("SELECT user_id FROM admin_sessions WHERE id=?", (session_id,))
        if row is None:
            return False
        if row["user_id"] != actor_id and actor_role != "super_admin":
            raise AuthError("forbidden", "Cannot revoke another user's session", 403)
        n = await self.db.rowcount("UPDATE admin_sessions SET revoked_at=?, revoke_reason=? WHERE id=? AND revoked_at IS NULL",
                                   (int(time.time()), reason[:64], session_id))
        await self.audit.log("auth.revoked", actor_id=actor_id, target_type="session", target_id=session_id, reason=reason)
        return n > 0

    async def revoke_all(self, user_id: int, except_session: int | None = None, reason: str = "revoke_all") -> int:
        return await self.db.rowcount(
            "UPDATE admin_sessions SET revoked_at=?, revoke_reason=? WHERE user_id=? AND revoked_at IS NULL AND id != ?",
            (int(time.time()), reason, user_id, except_session or -1))

    async def sessions(self, user_id: int | None = None, include_revoked: bool = False, limit: int = 100) -> list[dict[str, Any]]:
        where, params = [], []
        if user_id is not None:
            where.append("user_id=?")
            params.append(user_id)
        if not include_revoked:
            where.append("revoked_at IS NULL AND refresh_expires_at > ?")
            params.append(int(time.time()))
        sql = ("SELECT id, user_id, device_id, device_name, platform, app_version, created_at, last_used_at, last_ip, "
               "access_expires_at, refresh_expires_at, revoked_at, revoke_reason FROM admin_sessions")
        if where:
            sql += " WHERE " + " AND ".join(where)
        return await self.db.fetchall(sql + " ORDER BY COALESCE(last_used_at, created_at) DESC LIMIT ?", params + [limit])

    async def login_events(self, user_id: int | None = None, limit: int = 100) -> list[dict[str, Any]]:
        if user_id is None:
            return await self.db.fetchall("SELECT * FROM login_events ORDER BY id DESC LIMIT ?", (limit,))
        return await self.db.fetchall("SELECT * FROM login_events WHERE user_id=? ORDER BY id DESC LIMIT ?", (user_id, limit))

    async def suspicious(self, hours: int = 24) -> dict[str, Any]:
        since = int(time.time()) - hours * 3600
        by_ip = await self.db.fetchall("SELECT ip, COUNT(*) AS failures FROM login_events WHERE success=0 AND created_at > ? "
                                       "GROUP BY ip HAVING failures >= 3 ORDER BY failures DESC LIMIT 50", (since,))
        return {"failed_by_ip": by_ip, "lockout_active": time.time() < self._lockout_until,
                "lockout_until": int(self._lockout_until) if time.time() < self._lockout_until else None}

    async def cleanup(self) -> int:
        now = int(time.time())
        n = await self.db.rowcount("DELETE FROM pairing_codes WHERE expires_at < ?", (now - 86400,))
        n += await self.db.rowcount("DELETE FROM login_events WHERE created_at < ?", (now - 90 * 86400,))
        return n
