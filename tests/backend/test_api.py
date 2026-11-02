"""REST API for the Android app: pairing auth, token expiry/refresh/revoke, RBAC, data isolation, validation, errors."""
from __future__ import annotations


import httpx
import pytest
from conftest import OWNER, USER2
from fakes import business_connection, update_connection

from chat_helper.api.server import create_api



@pytest.fixture
async def api(env):
    app = create_api(env.app)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
        yield client


async def pair(env, api, uid=OWNER, device="dev-1"):
    await env.app.users.ensure(uid)
    code, _ = await env.app.auth.create_pairing_code(uid)
    r = await api.post("/api/v1/auth/pair", json={"code": code, "device_id": device, "device_name": "Pixel"})
    assert r.status_code == 200, r.text
    return r.json()


def h(tok):
    return {"Authorization": f"Bearer {tok['access_token']}"}


async def test_health_is_public_and_minimal(api):
    r = await api.get("/api/v1/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"
    assert "token" not in r.text.lower()


async def test_requires_auth(api):
    r = await api.get("/api/v1/dashboard")
    assert r.status_code == 401 and r.json()["error"]["code"] == "unauthorized"
    r = await api.get("/api/v1/dashboard", headers={"Authorization": "Bearer cha_forged"})
    assert r.status_code == 401


async def test_pairing_flow_and_one_time_code(env, api):
    await env.app.users.ensure(OWNER)
    code, _ = await env.app.auth.create_pairing_code(OWNER)
    r = await api.post("/api/v1/auth/pair", json={"code": code.lower().replace("-", " "), "device_id": "dev-1"})
    assert r.status_code == 200
    data = r.json()
    assert data["role"] == "super_admin" and data["me"]["user"]["id"] == OWNER and "emergency_stop" in data["me"]["capabilities"]
    r2 = await api.post("/api/v1/auth/pair", json={"code": code, "device_id": "dev-2"})
    assert r2.status_code == 401  # single use


async def test_cannot_claim_identity_by_passing_user_id(env, api):
    await env.app.users.ensure(USER2)
    code, _ = await env.app.auth.create_pairing_code(USER2)
    r = await api.post("/api/v1/auth/pair", json={"code": code, "device_id": "dev-1", "user_id": OWNER})
    assert r.json()["role"] == "user" and r.json()["user_id"] == USER2


async def test_expired_code(env, api):
    await env.app.users.ensure(OWNER)
    code, _ = await env.app.auth.create_pairing_code(OWNER)
    await env.app.db.execute("UPDATE pairing_codes SET expires_at=1")
    r = await api.post("/api/v1/auth/pair", json={"code": code, "device_id": "dev-1"})
    assert r.status_code == 401


async def test_bruteforce_rate_limit(api):
    codes = []
    for _ in range(7):
        r = await api.post("/api/v1/auth/pair", json={"code": "ABCD-EFGH", "device_id": "dev-x"})
        codes.append(r.status_code)
    assert codes[:5] == [401] * 5 and 429 in codes


async def test_access_expiry_and_refresh_rotation(env, api):
    tok = await pair(env, api)
    await env.app.db.execute("UPDATE admin_sessions SET access_expires_at=1")
    r = await api.get("/api/v1/auth/me", headers=h(tok))
    assert r.status_code == 401 and r.json()["error"]["code"] == "token_expired"
    r = await api.post("/api/v1/auth/refresh", json={"refresh_token": tok["refresh_token"]})
    assert r.status_code == 200
    new = r.json()
    assert (await api.get("/api/v1/auth/me", headers=h(new))).status_code == 200
    r = await api.post("/api/v1/auth/refresh", json={"refresh_token": tok["refresh_token"]})
    assert r.status_code == 401  # old refresh token is invalid after rotation


async def test_logout_and_remote_revoke(env, api):
    a = await pair(env, api, device="phone-a")
    b = await pair(env, api, device="phone-b")
    sessions = (await api.get("/api/v1/auth/sessions", headers=h(a))).json()["items"]
    assert len(sessions) == 2 and sum(1 for s in sessions if s["current"]) == 1
    other = next(s["id"] for s in sessions if not s["current"])
    assert (await api.delete(f"/api/v1/auth/sessions/{other}", headers=h(a))).status_code == 200
    assert (await api.get("/api/v1/auth/me", headers=h(b))).status_code == 401
    assert (await api.post("/api/v1/auth/logout", headers=h(a))).status_code == 200
    assert (await api.get("/api/v1/auth/me", headers=h(a))).status_code == 401


async def test_regular_user_cannot_access_admin(env, api):
    tok = await pair(env, api, USER2)
    for path in ("/api/v1/users", "/api/v1/system/status", "/api/v1/security/suspicious", "/api/v1/broadcasts"):
        r = await api.get(path, headers=h(tok))
        assert r.status_code == 403, path
    r = await api.post("/api/v1/security/emergency-stop", json={"enabled": True, "confirm": "STOP"}, headers=h(tok))
    assert r.status_code == 403
    r = await api.get(f"/api/v1/users/{OWNER}", headers=h(tok))
    assert r.status_code == 403


async def test_super_admin_access_and_confirmations(env, api):
    tok = await pair(env, api)
    assert (await api.get("/api/v1/users", headers=h(tok))).status_code == 200
    r = await api.post("/api/v1/security/emergency-stop", json={"enabled": True, "confirm": "yes"}, headers=h(tok))
    assert r.status_code == 400 and r.json()["error"]["code"] == "confirmation_required"
    r = await api.post("/api/v1/security/emergency-stop", json={"enabled": True, "confirm": "STOP"}, headers=h(tok))
    assert r.status_code == 200 and env.app.runtime.emergency_stop
    r = await api.post("/api/v1/security/emergency-stop", json={"enabled": False, "confirm": "RESUME"}, headers=h(tok))
    assert not env.app.runtime.emergency_stop


async def test_data_isolation_between_users(env, api):
    bc = business_connection("bcA", OWNER)
    env.session.connections["bcA"] = bc
    await env.feed(update_connection(bc))
    await env.app.chats.touch(OWNER, 111, title="Owner's friend", incoming=True, preview="secret")
    rule = await env.app.autoreply.add_rule(OWNER, {"trigger_type": "keyword", "pattern": "x", "response": "y"})
    tok2 = await pair(env, api, USER2)
    assert (await api.get("/api/v1/chats", headers=h(tok2))).json()["total"] == 0
    assert (await api.get("/api/v1/chats/111", headers=h(tok2))).status_code == 404
    assert (await api.patch("/api/v1/chats/111", json={"ignored": True}, headers=h(tok2))).status_code == 404
    assert (await api.delete(f"/api/v1/autoreply/rules/{rule['id']}", headers=h(tok2))).status_code == 404
    assert (await api.get("/api/v1/connections/bcA/inspector", headers=h(tok2))).status_code == 404
    assert (await api.get("/api/v1/connections", headers=h(tok2))).json()["items"] == []
    tok1 = await pair(env, api, OWNER)
    assert (await api.get("/api/v1/chats/111", headers=h(tok1))).status_code == 200


async def test_validation_errors_structured(env, api):
    tok = await pair(env, api)
    r = await api.patch("/api/v1/settings", json={"values": {"afk_cooldown_min": 99999}}, headers=h(tok))
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_setting"
    r = await api.post("/api/v1/automation/rules", json={"name": "x", "trigger": {"type": "nope"}, "actions": []}, headers=h(tok))
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_rule"
    r = await api.post("/api/v1/afk/enable", json={"minutes": -5}, headers=h(tok))
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"


async def test_dashboard_settings_afk_commands(env, api):
    tok = await pair(env, api)
    d = (await api.get("/api/v1/dashboard", headers=h(tok))).json()
    assert d["scope"] == "global" and "charts" in d and d["users"]["total"] >= 1
    r = await api.patch("/api/v1/settings", json={"values": {"lang": "uz", "mode": "business"}}, headers=h(tok))
    assert r.json()["values"]["lang"] == "uz" and r.json()["values"]["mode"] == "business"
    assert (await api.post("/api/v1/afk/enable", json={"reason": "busy", "minutes": 30}, headers=h(tok))).json()["active"]["reason"] == "busy"
    assert (await api.post("/api/v1/afk/disable", headers=h(tok))).json()["summary"]
    cmds = (await api.get("/api/v1/commands", headers=h(tok))).json()
    assert cmds["count"] >= 130
    t = (await api.post("/api/v1/commands/test", json={"text": ".calc 6*7"}, headers=h(tok))).json()
    assert t["ok"] and "42" in t["outputs"][0]["text"]
    assert (await api.patch("/api/v1/commands/uuid", json={"enabled": False}, headers=h(tok))).json()["enabled"] is False


async def test_automation_api_and_dry_run(env, api):
    tok = await pair(env, api)
    rule = {"name": "price", "trigger": {"type": "keyword", "keywords": ["цена"]}, "actions": [{"type": "reply", "text": "100$"}]}
    r = await api.post("/api/v1/automation/test", json={"rule": rule, "sample_text": "какая цена?"}, headers=h(tok))
    assert r.json()["would_fire"] is True and r.json()["actions"] == ["reply:would_run"]
    created = (await api.post("/api/v1/automation/rules", json=rule, headers=h(tok))).json()
    assert created["id"]
    tpls = (await api.get("/api/v1/automation/templates", headers=h(tok))).json()["items"]
    r = await api.post(f"/api/v1/automation/templates/{tpls[0]['id']}/install", headers=h(tok))
    assert r.status_code == 200 and len(r.json()["items"]) >= 1


async def test_media_demo_and_games(env, api):
    tok = await pair(env, api)
    r = await api.get("/api/v1/media/demo/ramka:neon", headers=h(tok))
    assert r.status_code == 200 and r.headers["content-type"].startswith("image/")
    g = (await api.get("/api/v1/games", headers=h(tok))).json()
    assert len(g["items"]) == 14


async def test_analytics_export(env, api):
    tok = await pair(env, api)
    await env.app.metrics.incr("messages_in", OWNER, 5)
    r = await api.get("/api/v1/analytics/overview", headers=h(tok))
    assert r.json()["totals"]["messages_in"] == 5
    for fmt, ctype in (("csv", "text/csv"), ("json", "application/json"), ("pdf", "application/pdf")):
        r = await api.get(f"/api/v1/analytics/export?format={fmt}", headers=h(tok))
        assert r.status_code == 200 and r.headers["content-type"].startswith(ctype), fmt


async def test_subscription_grant_promo_and_restrict(env, api):
    admin = await pair(env, api)
    await env.app.users.ensure(USER2)
    r = await api.post(f"/api/v1/users/{USER2}/subscription", json={"plan_id": "pro", "days": 30}, headers=h(admin))
    assert r.status_code == 200 and await env.app.subs.plan_of(USER2) == "pro"
    promo = (await api.post("/api/v1/subscriptions/promo", json={"plan_id": "plus", "days": 7, "max_uses": 1}, headers=h(admin))).json()
    user = await pair(env, api, USER2, "dev-u2")
    assert (await api.post("/api/v1/subscriptions/redeem", json={"code": promo["code"]}, headers=h(user))).status_code == 200
    assert (await api.post("/api/v1/subscriptions/redeem", json={"code": promo["code"]}, headers=h(user))).status_code == 400
    r = await api.post(f"/api/v1/users/{USER2}/restrict", json={"reason": "abuse"}, headers=h(admin))
    assert r.status_code == 200
    assert (await api.get("/api/v1/auth/me", headers=h(user))).status_code in (401, 403)


async def test_security_endpoints(env, api):
    tok = await pair(env, api)
    assert (await api.get("/api/v1/security/logins", headers=h(tok))).json()["items"][0]["success"] == 1
    assert "failed_by_ip" in (await api.get("/api/v1/security/suspicious", headers=h(tok))).json()
    assert (await api.get("/api/v1/system/db-integrity", headers=h(tok))).json()["ok"] is True
    r = await api.post("/api/v1/system/restart/python", headers=h(tok))
    assert r.status_code == 400 and "supervisor" in r.json()["error"]["message"]
    r = await api.post("/api/v1/system/backup", json={"confirm": True}, headers=h(tok))
    assert r.status_code == 200 and r.json()["size"] > 0


async def test_api_binds_publicly_only_with_remote_mode_and_tls(tmp_path, monkeypatch):
    from chat_helper.config import load_settings

    for k in ("API_HOST", "API_REMOTE_ENABLED", "API_SSL_CERTFILE", "API_SSL_KEYFILE"):
        monkeypatch.delenv(k, raising=False)
    base = dict(data_dir=tmp_path, bot_token="")
    assert load_settings(None, api_host="0.0.0.0", **base).api_host == "127.0.0.1"
    # remote flag alone is not enough: plain HTTP must never leave loopback
    assert load_settings(None, api_host="0.0.0.0", api_remote_enabled=True, **base).api_host == "127.0.0.1"
    tls = load_settings(None, api_host="0.0.0.0", api_remote_enabled=True, api_ssl_certfile="c.pem", api_ssl_keyfile="k.pem", **base)
    assert tls.api_host == "0.0.0.0"
