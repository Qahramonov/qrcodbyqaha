"""The admin section exists only for the super admin (numeric SUPER_ADMIN_ID). For everyone else it is invisible:
no buttons, no commands in help/lists/suggestions, no "access denied" texts, and the admin API answers exactly like a
route that does not exist. Every attempt is written to the audit log."""
from __future__ import annotations

import re

import httpx
import pytest_asyncio
from conftest import CONTACT, OWNER, USER2
from fakes import biz_message, business_connection, private_message, update_business_message, update_connection
from fastapi.routing import APIRoute
from test_panel import cb

from chat_helper.api import deps
from chat_helper.api.server import create_api

ADMIN_WORDS = re.compile(r"Super Admin|Админ-панел|Admin panel|Dashboard|Рассылк|Broadcast|\.logs\b|👑")


async def connect(env, uid: int, conn_id: str):
    bc = business_connection(conn_id, uid)
    env.session.connections[conn_id] = bc
    await env.feed(update_connection(bc))


def all_buttons(env) -> list:
    out = []
    for r in env.session.requests:
        mk = getattr(r, "reply_markup", None)
        if hasattr(mk, "inline_keyboard"):
            out += [b for row in mk.inline_keyboard for b in row]
    return out


def everything_shown(env) -> str:
    texts = env.session.sent_texts() + [getattr(r, "caption", None) or "" for r in env.session.requests]
    texts += [getattr(r, "text", None) or "" for r in env.session.calls("AnswerCallbackQuery")]
    texts += [f"{b.text} {b.callback_data or ''}" for b in all_buttons(env)]
    return "\n".join(texts)


# ---- Telegram bot ---------------------------------------------------------------------------------------------------
async def test_regular_user_never_sees_admin_entry_points(env):
    await connect(env, USER2, "bc2")
    for text in ("/start", "/menu", "/help", ".help", ".commands", "/connect"):
        env.session.clear()
        await env.feed(private_message(USER2, text, "Bob"))
        shown = everything_shown(env)
        assert not ADMIN_WORDS.search(shown), (text, ADMIN_WORDS.search(shown))
        assert "m:admin" not in shown and "ax:" not in shown and "adm:" not in shown
    # the panel's command catalogue: no admin-only command anywhere
    for data in ("m:commands", "cmd:cat:system:0", "cmd:cat:system:1", "m:home", "m:help", "m:settings"):
        env.session.clear()
        await env.feed(cb(USER2, data))
        assert not ADMIN_WORDS.search(everything_shown(env)), data


async def test_not_connected_user_sees_no_admin_either(env):
    for text in ("/start", "/help", "/connect"):
        env.session.clear()
        await env.feed(private_message(USER2, text, "Bob"))
        assert not ADMIN_WORDS.search(everything_shown(env)), text


async def test_admin_command_behaves_like_unknown_command(env):
    await connect(env, USER2, "bc2")
    env.session.clear()
    await env.feed(private_message(USER2, ".nosuchcmd", "Bob"))
    unknown = env.session.sent_texts()[-1].replace(".nosuchcmd", "<CMD>").split("\n")[:2]
    env.session.clear()
    await env.feed(private_message(USER2, ".logs", "Bob"))
    reply = env.session.sent_texts()[-1]
    # same "unknown command" reply; "did you mean" hints only come from commands this user can see
    assert reply.replace(".logs", "<CMD>").split("\n")[:2] == unknown
    assert ".logs" not in reply.split("\n", 2)[-1]
    # aliases and typos do not lead to it either
    for text in (".логи", ".log", ".lgos"):
        env.session.clear()
        await env.feed(private_message(USER2, text, "Bob"))
        assert "logs" not in " ".join(env.session.sent_texts()), text
    # .help for it: "not found", exactly like for a command that does not exist
    env.session.clear()
    await env.feed(private_message(USER2, ".help nosuchcmd", "Bob"))
    missing = env.session.sent_texts()[-1]
    env.session.clear()
    await env.feed(private_message(USER2, ".help logs", "Bob"))
    assert env.session.sent_texts()[-1] == missing
    # in a business chat an unknown ".word" is ordinary text: no reply at all
    env.session.clear()
    await env.feed(update_business_message(biz_message("bc2", CONTACT, USER2, ".logs", first_name="Bob")))
    assert not env.session.sent_texts()
    # the attempt itself is not even recorded as a command (it is not one for this user)
    assert await env.app.db.fetchval("SELECT COUNT(*) FROM command_history WHERE user_id=? AND command_id='logs'", (USER2,), 0) == 0


async def test_super_admin_still_has_everything(env):
    await connect(env, OWNER, "bc_owner")
    env.session.clear()
    await env.feed(private_message(OWNER, "/start"))
    assert "m:admin" in {b.callback_data for b in all_buttons(env)}
    env.session.clear()
    await env.feed(private_message(OWNER, ".help"))
    assert ".logs" in env.session.sent_texts()[-1]
    env.session.clear()
    await env.feed(private_message(OWNER, ".logs"))
    assert not any("Неизвестная команда" in t for t in env.session.sent_texts())
    env.session.clear()
    await env.feed(cb(OWNER, "m:admin"))
    assert "Super Admin" in everything_shown(env)


async def test_forged_admin_callbacks_get_a_dead_button_reaction(env):
    await connect(env, USER2, "bc2")
    for data in ("m:admin", "ax:dash", "ax:users", "ax:sys", "ax:db", "ax:uact:4200000001:grant_vip", "adm:es", "adm:mt",
                 "adm:bc", "adm:health", "bc:start:1", "bc:cancel:1"):
        env.session.clear()
        await env.feed(cb(USER2, data))
        answers = env.session.calls("AnswerCallbackQuery")
        assert answers and all(not a.text and not a.show_alert for a in answers), data
        assert not ADMIN_WORDS.search(everything_shown(env)), data
    assert not env.app.runtime.emergency_stop and not env.app.runtime.maintenance
    assert await env.app.subs.plan_of(USER2) == "free"
    denied = await env.app.db.fetchval("SELECT COUNT(*) FROM audit_logs WHERE action='security.admin_callback_denied'", (), 0)
    assert denied >= 11


async def test_forged_admin_fsm_state_is_dropped_silently(env):
    from aiogram.fsm.storage.base import StorageKey
    await connect(env, USER2, "bc2")
    for state in ("PS:broadcast_text", "AX:user_search"):
        key = StorageKey(bot_id=env.bot.id, chat_id=USER2, user_id=USER2)
        await env.dp.storage.set_state(key, state)
        env.session.clear()
        await env.feed(private_message(USER2, "Купите у меня!", "Bob"))
        assert await env.dp.storage.get_state(key) is None
        assert not ADMIN_WORDS.search(everything_shown(env)) and "Недостаточно прав" not in everything_shown(env)
    assert await env.app.db.fetchval("SELECT COUNT(*) FROM broadcasts", (), 0) == 0


# ---- REST API -------------------------------------------------------------------------------------------------------
@pytest_asyncio.fixture
async def api(env):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_api(env.app)), base_url="http://127.0.0.1") as client:
        yield client


async def token(env, api, uid: int) -> dict:
    await env.app.users.ensure(uid)
    code, _ = await env.app.auth.create_pairing_code(uid)
    r = await api.post("/api/v1/auth/pair", json={"code": code, "device_id": f"dev-{uid}", "device_name": "Pixel"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _uses(dependant, targets) -> bool:
    return any(d.call in targets or _uses(d, targets) for d in dependant.dependencies)


def admin_routes() -> list[tuple[str, APIRoute]]:
    """Every API route guarded by the admin / super_admin dependency (read from the routers themselves)."""
    from chat_helper.api.routers import admin_routes as adm, ai_routes, auth_routes, ops_routes, user_routes, v3_routes
    out = []
    for router in (auth_routes.router, user_routes.router, ai_routes.router, ops_routes.router, adm.router, v3_routes.router):
        out += [("/api/v1" + r.path, r) for r in router.routes
                if isinstance(r, APIRoute) and _uses(r.dependant, (deps.admin, deps.super_admin))]
    return out


def concrete(path: str) -> str:
    return re.sub(r"\{[^}]+\}", "1", path)


async def test_every_admin_route_is_a_404_for_regular_users(env, api):
    h = await token(env, api, USER2)
    routes = admin_routes()
    assert len(routes) >= 40
    unknown = await api.get("/api/v1/definitely/not/a/route", headers=h)
    assert unknown.status_code == 404
    for path, route in routes:
        for method in sorted(route.methods - {"HEAD"}):
            r = await api.request(method, concrete(path), headers=h, json={})
            assert r.status_code == 404, (method, path, r.status_code)
            assert r.json() == unknown.json(), (method, path)       # exactly the "no such route" answer
    denied = await env.app.db.fetchval("SELECT COUNT(*) FROM audit_logs WHERE action='security.admin_api_denied'", (), 0)
    assert denied >= len(routes)


async def test_super_admin_reaches_admin_routes(env, api):
    h = await token(env, api, OWNER)
    for path in ("/api/v1/users", "/api/v1/system/status", "/api/v1/security/suspicious", "/api/v1/broadcasts",
                 f"/api/v1/users/{USER2}"):
        r = await api.get(path, headers=h)
        assert r.status_code in (200, 404 if path.endswith(str(USER2)) else 200), (path, r.status_code)
        assert r.status_code == 200 or "not found" in r.text.lower()


async def test_without_token_admin_and_unknown_routes_look_the_same(api):
    a = await api.get("/api/v1/users")
    b = await api.get("/api/v1/definitely/not/a/route")
    assert a.status_code == b.status_code == 401 and a.json() == b.json()


async def test_user_scoped_params_do_not_reveal_admin_data(env, api):
    h = await token(env, api, USER2)
    me = (await api.get("/api/v1/auth/me", headers=h)).json()
    assert me["role"] == "user" and not {"users", "system", "broadcast", "security"} & set(me["capabilities"])
    assert (await api.get(f"/api/v1/users/{OWNER}", headers=h)).status_code == 404
    usage = (await api.get("/api/v1/ai/usage", params={"scope": "global"}, headers=h))
    assert usage.status_code == 200
    dash = (await api.get("/api/v1/dashboard", params={"scope": "global"}, headers=h)).json()
    assert dash["scope"] == "self"
    cmds = (await api.get("/api/v1/commands", headers=h)).json()["items"]
    assert "logs" not in {c["id"] for c in cmds}
    assert (await api.patch("/api/v1/commands/logs", json={"enabled": False}, headers=h)).status_code == 404
    test = (await api.post("/api/v1/commands/test", json={"text": ".logs"}, headers=h)).json()
    assert test["error"] == "unknown_command" and "logs" not in str(test.get("suggestions"))


async def test_api_docs_are_off_by_default(env, api):
    for path in ("/api/docs", "/api/openapi.json"):
        assert (await api.get(path)).status_code in (401, 404), path
    env.app.config.api_docs_enabled = True
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_api(env.app)), base_url="http://127.0.0.1") as c:
            assert (await c.get("/api/openapi.json")).status_code == 200
    finally:
        env.app.config.api_docs_enabled = False
