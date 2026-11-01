"""Security controls promised in docs/SECURITY.md: log redaction, headers, pairing lockout, session cap,
fixed super-admin role, new-device alerts, dangerous business rights, retention, per-session API limit, flood control."""
from __future__ import annotations

import logging
import time

import httpx
import pytest
from conftest import OWNER, USER2

from chat_helper.api.server import create_api
from chat_helper.auth.service import AuthError


FAKE_BOT_TOKEN = "1234567890:" + "A" * 35          # shape of a token, not a real one
FAKE_OPENAI = "sk-" + "x" * 40
FAKE_GEMINI = "AIza" + "y" * 35


@pytest.fixture
async def api(env):
    transport = httpx.ASGITransport(app=create_api(env.app))
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
        yield client


async def test_redactor_masks_tokens_and_keys():
    from chat_helper.core.logging import RedactingFilter, Redactor

    r = Redactor()
    r.set_values(["my-configured-secret-value"])
    text = (f"token {FAKE_BOT_TOKEN} key={FAKE_OPENAI} g {FAKE_GEMINI} Authorization: Bearer cha_abcdefghijklmnopqrstuvwxyz "
            f"url https://x/?key=ABCDEFGHIJKLMNOPQRSTUV and my-configured-secret-value")
    out = r(text)
    for secret in (FAKE_BOT_TOKEN, FAKE_OPENAI, FAKE_GEMINI, "cha_abcdefghijklmnopqrstuvwxyz", "ABCDEFGHIJKLMNOPQRSTUV",
                   "my-configured-secret-value"):
        assert secret not in out, secret
    # the logging filter rewrites records, including %-args
    rec = logging.LogRecord("t", logging.INFO, __file__, 1, "call failed for %s", (f"https://api.telegram.org/bot{FAKE_BOT_TOKEN}/getMe",), None)
    RedactingFilter().filter(rec)
    assert FAKE_BOT_TOKEN not in rec.getMessage()
    assert r("refresh chr_" + "z" * 40).count("z") == 0
    assert r("12:30 meeting, order 123456") == "12:30 meeting, order 123456"   # ordinary text is untouched


async def test_security_headers_and_minimal_errors(api):
    r = await api.get("/api/v1/health")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["cache-control"] == "no-store"
    r = await api.get("/api/v1/users")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "unauthorized" and "Traceback" not in r.text


async def test_global_pairing_lockout_and_admin_alert(env):
    auth = env.app.auth
    for i in range(50):
        await auth._fail(f"10.0.{i // 250}.{i % 250}", "invalid_or_expired")
    await env.app.users.ensure(OWNER)
    code, _ = await auth.create_pairing_code(OWNER)
    with pytest.raises(AuthError) as e:
        await auth.pair(code, device_id="dev-lock", device_name="X", platform="android", app_version="1", ip="10.9.9.9")
    assert e.value.code == "locked" and e.value.status == 429
    notes = await env.app.notifications.list(OWNER)
    assert any(n["title"] == "Pairing lockout" for n in notes)


async def test_session_cap_revokes_oldest(env):
    auth = env.app.auth
    await env.app.users.ensure(USER2)
    first = None
    for i in range(12):
        t = await auth._create_session(USER2, f"dev-{i:02d}", "Phone", "android", "1.0.0", "127.0.0.1")
        first = first or t
    active = await env.app.db.fetchval("SELECT COUNT(*) FROM admin_sessions WHERE user_id=? AND revoked_at IS NULL", (USER2,))
    assert active == 10
    with pytest.raises(AuthError):
        await auth.authenticate(first["access_token"])


async def test_super_admin_role_is_fixed_and_new_device_alert(env, api):
    users = env.app.users
    await users.ensure(OWNER)
    with pytest.raises(ValueError):
        await users.set_role(OWNER, "user", granted_by=OWNER)
    assert await users.role(OWNER) == "super_admin"
    await users.ensure(USER2)
    await users.set_role(USER2, "moderator", granted_by=OWNER)
    assert await users.role(USER2) == "moderator"
    # a username can never grant the role: only the configured ID is super admin
    await users.upsert(USER2, "libPM", "Fake", None, "ru", touch=True)
    assert await users.role(USER2) == "moderator"

    code, _ = await env.app.auth.create_pairing_code(OWNER)
    r = await api.post("/api/v1/auth/pair", json={"code": code, "device_id": "dev-new", "device_name": "Pixel 8"})
    assert r.status_code == 200
    notes = await env.app.notifications.list(OWNER)
    assert any("Pixel 8" in (n["body"] or "") and n["kind"] == "security" for n in notes)


async def test_dangerous_business_rights_are_flagged():
    from chat_helper.business.rights import inspect

    safe = inspect({"can_reply": True, "can_read_messages": True}, True, "ru")
    assert not any("Stars" in a for a in safe["advice"])
    risky = inspect({"can_reply": True, "can_read_messages": True, "can_transfer_stars": True,
                     "can_transfer_and_upgrade_gifts": True}, True, "ru")
    assert any("Stars" in a for a in risky["advice"])


async def test_history_retention_deletes_old_ai_history(env):
    db, now = env.app.db, int(time.time())
    await env.app.users.ensure(OWNER)
    await env.app.settings.set(OWNER, "history_retention_days", 1)
    await db.execute("INSERT INTO ai_history(user_id, chat_id, role, content, created_at) VALUES (?,?,?,?,?)",
                     (OWNER, 1, "user", "old", now - 3 * 86400))
    await db.execute("INSERT INTO ai_history(user_id, chat_id, role, content, created_at) VALUES (?,?,?,?,?)",
                     (OWNER, 1, "user", "fresh", now))
    removed = await env.app.ai.memory.apply_retention(env.app.settings)
    assert removed >= 1
    rows = [r["content"] for r in await db.fetchall("SELECT content FROM ai_history WHERE user_id=?", (OWNER,))]
    assert rows == ["fresh"]


async def test_per_session_api_rate_limit(env, api):
    await env.app.users.ensure(USER2)
    code, _ = await env.app.auth.create_pairing_code(USER2)
    tok = (await api.post("/api/v1/auth/pair", json={"code": code, "device_id": "dev-rl", "device_name": "P"})).json()
    h = {"Authorization": f"Bearer {tok['access_token']}"}
    codes = [(await api.get("/api/v1/auth/me", headers=h)).status_code for _ in range(245)]
    assert codes[0] == 200 and 429 in codes
    assert codes.index(429) == 240


async def test_flood_control_spaces_messages_per_chat():
    from chat_helper.business.sender import FloodControl

    fc = FloodControl(per_chat_interval=0.15, global_rate=1000)
    t0 = time.monotonic()
    for _ in range(3):
        await fc.wait(42)
    assert time.monotonic() - t0 >= 0.29
    t1 = time.monotonic()
    await fc.wait(43)          # another chat is not delayed by chat 42
    assert time.monotonic() - t1 < 0.1
