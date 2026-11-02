"""Record real responses of the Chat helper API for the Flutter app's tests (flutter_app/test/fixtures/api_samples.json).

Builds the real backend (fake Telegram transport, temporary database), creates a connected super admin and a connected
regular user with a little activity, then calls every read endpoint as each of them and stores the JSON bodies.
No tokens or secrets are written: the pairing/refresh responses are recorded with placeholder token values.

    python3 tests/backend/record_api_samples.py            # rewrites the fixture file
"""
from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import httpx  # noqa: E402
from fakes import biz_message, business_connection, make_bot, private_message, update_business_message, update_connection  # noqa: E402

OWNER, USER2, CONTACT = 8053614984, 4200000001, 5550000001
OUT = ROOT / "flutter_app" / "test" / "fixtures" / "api_samples.json"

USER_GETS = [
    "/health", "/auth/me", "/auth/sessions", "/onboarding", "/dashboard", "/settings", "/connections", "/permissions",
    "/chats", "/inbox", "/notifications", "/afk", "/afk/history", "/afk/preview", "/mute", "/protect", "/ai/providers",
    "/ai/usage", "/ai/profiles", "/ai/memory", "/ai/drafts", "/ai/twin", "/animations", "/media/settings", "/media/jobs",
    "/media/stats", "/games", "/games/history", "/games/leaderboard", "/games/sessions", "/commands", "/commands/custom",
    "/reminders", "/automation/schema", "/automation/rules", "/automation/templates", "/automation/executions",
    "/autoreply/rules", "/autoreply/templates", "/subscriptions/me", "/subscriptions/plans", "/analytics/overview",
    "/delegation", "/payments", "/changelog", "/flags", "/export",
]
ADMIN_GETS = [
    "/dashboard?scope=global", "/users", "/connections?all=true", "/admin/chat-controls", "/ai/usage?scope=global",
    "/media/stats?scope=global", "/media/jobs?scope=global", "/games/sessions?scope=global", "/payments?scope=global",
    "/analytics/overview?scope=global", "/broadcasts", "/security/audit", "/security/suspicious", "/security/logins",
    "/security/sessions", "/security/ratelimits", "/system/status", "/system/modules", "/system/backups", "/system/checks",
    "/system/db-integrity", "/system/logs", "/subscriptions/stats", "/subscriptions/promo",
]


async def main() -> None:
    from chat_helper.api.server import create_api
    from chat_helper.app import build_app
    from chat_helper.config import load_settings

    with tempfile.TemporaryDirectory() as tmp:
        bot, session = make_bot()
        cfg = load_settings(None, data_dir=Path(tmp) / "data", bot_token="", openai_api_key="", gemini_api_key="",
                            anthropic_api_key="", compat_api_key="", compat_base_url="", payments_enabled=False)
        app, dp = await build_app(cfg, bot=bot)
        app.bot_info = await bot.get_me()
        app.sender.flood.per_chat_interval = app.sender.flood.global_interval = 0.0
        try:
            for uid, conn_id in ((OWNER, "bc_owner"), (USER2, "bc_user")):
                await dp.feed_update(bot, private_message(uid, "/start"))
                bc = business_connection(conn_id, uid)
                session.connections[conn_id] = bc
                await dp.feed_update(bot, update_connection(bc))
                for text in ("Привет! Сколько стоит?", "Ты где?"):
                    await dp.feed_update(bot, update_business_message(biz_message(conn_id, CONTACT, CONTACT, text, first_name="Ali")))
                await dp.feed_update(bot, update_business_message(biz_message(conn_id, CONTACT, uid, ".calc 2+2", first_name="Owner")))
            await app.reminders.create(USER2, "Позвонить маме", int(__import__("time").time()) + 3600, kind="dm")
            samples: dict[str, dict] = {"user": {}, "admin": {}, "meta": {"owner_id": OWNER, "user_id": USER2, "contact_id": CONTACT}}
            api = create_api(app)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=api), base_url="http://127.0.0.1") as c:
                tokens = {}
                for who, uid in (("user", USER2), ("admin", OWNER)):
                    code, _ = await app.auth.create_pairing_code(uid)
                    r = await c.post("/api/v1/auth/pair", json={"code": code, "device_id": f"rec-{who}", "device_name": "Recorder"})
                    tokens[who] = r.json()["access_token"]
                    pair = r.json()
                    samples[who]["POST /auth/pair"] = {**pair, "access_token": "ACCESS", "refresh_token": "REFRESH"}
                for who, paths in (("user", USER_GETS), ("admin", USER_GETS + ADMIN_GETS)):
                    h = {"Authorization": f"Bearer {tokens[who]}"}
                    for path in paths:
                        r = await c.get("/api/v1" + path, headers=h)
                        if r.headers.get("content-type", "").startswith("application/json"):
                            samples[who][f"GET {path}"] = {"status": r.status_code, "body": r.json()}
                    chats = samples[who]["GET /chats"]["body"].get("items") or []
                    if chats:
                        cid = chats[0]["chat_id"]
                        for path in (f"/chats/{cid}", f"/chats/{cid}/controls"):
                            r = await c.get("/api/v1" + path, headers=h)
                            samples[who][f"GET {path.replace(str(cid), '{chat_id}')}"] = {"status": r.status_code, "body": r.json()}
                    conns = samples[who]["GET /connections"]["body"].get("items") or []
                    if conns:
                        r = await c.get(f"/api/v1/connections/{conns[0]['id']}/inspector", headers=h)
                        samples[who]["GET /connections/{conn_id}/inspector"] = {"status": r.status_code, "body": r.json()}
                h = {"Authorization": f"Bearer {tokens['admin']}"}
                r = await c.get(f"/api/v1/users/{USER2}", headers=h)
                samples["admin"]["GET /users/{uid}"] = {"status": r.status_code, "body": r.json()}
                # the same reads with the account language set to Uzbek (server-localized texts), without the big /commands list
                for who, uid in (("user", USER2), ("admin", OWNER)):
                    await app.settings.set(uid, "lang", "uz")
                    samples[f"{who}_uz"] = {}
                    h = {"Authorization": f"Bearer {tokens[who]}"}
                    for path in (USER_GETS if who == "user" else USER_GETS + ADMIN_GETS):
                        if path == "/commands":
                            continue
                        r = await c.get("/api/v1" + path, headers=h)
                        if r.headers.get("content-type", "").startswith("application/json"):
                            samples[f"{who}_uz"][f"GET {path}"] = {"status": r.status_code, "body": r.json()}
                    await app.settings.set(uid, "lang", "ru")
                hu = {"Authorization": f"Bearer {tokens['user']}"}
                r = await c.get("/api/v1/users", headers=hu)
                samples["user"]["GET /users"] = {"status": r.status_code, "body": r.json()}
                r = await c.post("/api/v1/animations/preview", headers=hu, json={"kind": "typewriter", "text": "Salom"})
                samples["user"]["POST /animations/preview"] = {"status": r.status_code, "body": r.json()}
                r = await c.post("/api/v1/commands/test", headers=hu, json={"text": ".calc 2+2*2"})
                samples["user"]["POST /commands/test"] = {"status": r.status_code, "body": r.json()}
            OUT.parent.mkdir(parents=True, exist_ok=True)
            text = json.dumps(samples, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
            assert "ACCESS" in text and tokens["user"] not in text and tokens["admin"] not in text
            OUT.write_text(text + "\n", encoding="utf-8")
            print(f"recorded {sum(len(v) for k, v in samples.items() if k != 'meta')} responses → {OUT.relative_to(ROOT)}")
        finally:
            await app.db.close()


if __name__ == "__main__":
    asyncio.run(main())
