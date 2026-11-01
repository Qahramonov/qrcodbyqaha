"""v3 access model: only the configured super admin is an administrator; features stay locked until the account is
connected through Telegram Business (Chat automation). Covers menu, commands, callbacks, FSM and the REST API."""
from __future__ import annotations

import httpx
from aiogram.exceptions import TelegramBadRequest
from conftest import OWNER, USER2
from fakes import business_connection, private_message, update_connection
from test_panel import cb

from chat_helper.api.server import create_api


async def connect(env, uid: int, conn_id: str):
    bc = business_connection(conn_id, uid)
    env.session.connections[conn_id] = bc
    await env.feed(update_connection(bc))


def buttons(req) -> list:
    mk = getattr(req, "reply_markup", None)
    return [b for row in (mk.inline_keyboard if mk else []) for b in row]


def last_text(env) -> str:
    reqs = env.session.calls("EditMessageText") + env.session.calls("SendMessage") + env.session.calls("SendPhoto")
    return (getattr(reqs[-1], "text", None) or getattr(reqs[-1], "caption", None) or "") if reqs else ""


# ---- before connection -----------------------------------------------------------------------------------------
async def test_start_shows_onboarding_and_connect_buttons(env):
    await env.feed(private_message(USER2, "/start", "Bob"))
    req = env.session.calls("SendMessage")[-1]
    assert "подключите свой Telegram-аккаунт" in req.text
    data = {b.callback_data for b in buttons(req)}
    assert {"m:connect", "m:features", "m:lang", "m:help"} <= data
    assert "m:admin" not in data


async def test_commands_and_text_are_locked_until_connection(env):
    for text in (".ai привет", ".calc 2+2", "просто текст"):
        env.session.clear()
        await env.feed(private_message(USER2, text, "Bob"))
        req = env.session.calls("SendMessage")[-1]
        assert "ещё не подключён" in req.text, text
        assert {b.callback_data for b in buttons(req)} == {"m:connect", "ob:guide", "ob:check"}
    # allowed before connection
    env.session.clear()
    await env.feed(private_message(USER2, ".help", "Bob"))
    assert not any("ещё не подключён" in t for t in env.session.sent_texts())


async def test_feature_callbacks_and_screens_are_locked(env):
    await env.feed(private_message(USER2, "/start", "Bob"))
    env.session.clear()
    await env.feed(cb(USER2, "tg:afk_ai"))
    assert await env.app.settings.get(USER2, "afk_ai") is False
    alert = env.session.calls("AnswerCallbackQuery")[-1]
    assert alert.show_alert and "подключите" in alert.text
    env.session.clear()
    await env.feed(cb(USER2, "m:afk"))
    assert "подключите свой Telegram-аккаунт" in last_text(env)


async def test_feature_fsm_state_is_cleared_when_locked(env):
    from aiogram.fsm.storage.base import StorageKey
    key = StorageKey(bot_id=env.bot.id, chat_id=USER2, user_id=USER2)
    await env.dp.storage.set_state(key, "PS:afk_reason")
    await env.feed(private_message(USER2, "Ушёл на обед", "Bob"))
    assert await env.dp.storage.get_state(key) is None
    assert not await env.app.afk.active(USER2)


async def test_connect_wizard_has_copy_settings_and_check_buttons(env):
    await env.feed(private_message(USER2, "/connect", "Bob"))
    req = env.session.calls("SendMessage")[-1]
    assert "Автоматизация чатов" in req.text and "@ChatHelperTestBot" in req.text
    btns = buttons(req)
    assert any(b.copy_text and b.copy_text.text == "@ChatHelperTestBot" for b in btns)
    assert any(b.url == "tg://settings/edit" for b in btns)
    assert any(b.callback_data == "ob:check" for b in btns)


async def test_wizard_falls_back_when_tg_link_is_rejected(env):
    exc = TelegramBadRequest(method=None, message="Bad Request: BUTTON_URL_INVALID")
    exc._once = True
    env.session.fail["SendMessage"] = exc
    await env.feed(private_message(USER2, "/connect", "Bob"))
    sent = env.session.calls("SendMessage")
    assert len(sent) == 2                       # first attempt rejected, then re-sent
    assert not any((b.url or "").startswith("tg://") for b in buttons(sent[-1]))
    assert "вручную" in sent[-1].text


async def test_infographic_is_sent_as_photo(env):
    await env.feed(private_message(USER2, "/start", "Bob"))
    env.session.clear()
    await env.feed(cb(USER2, "ob:guide"))
    photo = env.session.calls("SendPhoto")[-1]
    assert "6 шагов" in photo.caption


async def test_check_connection_before_and_after(env):
    await env.feed(private_message(USER2, "/start", "Bob"))
    env.session.clear()
    await env.feed(cb(USER2, "ob:check"))
    assert "не найдено" in last_text(env)
    await connect(env, USER2, "bc2")
    env.session.clear()
    await env.feed(cb(USER2, "ob:check"))
    assert "Подключение активно" in last_text(env)
    env.session.clear()
    await env.feed(private_message(USER2, ".calc 2+2", "Bob"))
    assert any("4" in t for t in env.session.sent_texts())


async def test_language_switch_is_public(env):
    await env.feed(private_message(USER2, "/start", "Bob"))
    await env.feed(cb(USER2, "ob:lang:uz"))
    assert await env.app.settings.get(USER2, "lang") == "uz"
    env.session.clear()
    await env.feed(private_message(USER2, ".ai salom", "Bob"))
    assert "hali ulanmagan" in env.session.sent_texts()[-1]


async def test_disconnect_locks_features_again(env):
    await connect(env, USER2, "bc2")
    bc = business_connection("bc2", USER2, enabled=False)
    env.session.connections["bc2"] = bc
    await env.feed(update_connection(bc))
    env.session.clear()
    await env.feed(private_message(USER2, ".calc 1+1", "Bob"))
    assert "ещё не подключён" in env.session.sent_texts()[-1]


# ---- super admin only ----------------------------------------------------------------------------------------------
async def test_admin_callbacks_denied_for_connected_regular_user(env):
    await connect(env, USER2, "bc2")
    for data in ("adm:es", "adm:mt", "adm:bc", "bc:send:1"):
        env.session.clear()
        await env.feed(cb(USER2, data))
        alert = env.session.calls("AnswerCallbackQuery")[-1]
        assert alert.show_alert and "Недостаточно прав" in alert.text, data
    assert not env.app.runtime.emergency_stop and not env.app.runtime.maintenance
    assert await env.app.db.fetchval("SELECT COUNT(*) FROM audit_logs WHERE action='security.admin_callback_denied'") >= 4


async def test_admin_fsm_state_denied(env):
    from aiogram.fsm.storage.base import StorageKey
    await connect(env, USER2, "bc2")
    key = StorageKey(bot_id=env.bot.id, chat_id=USER2, user_id=USER2)
    await env.dp.storage.set_state(key, "PS:broadcast_text")
    await env.feed(private_message(USER2, "Купите у меня!", "Bob"))
    assert await env.app.db.fetchval("SELECT COUNT(*) FROM broadcasts") == 0
    assert await env.dp.storage.get_state(key) is None


async def test_admin_menu_hidden_and_redirected(env):
    await connect(env, USER2, "bc2")
    await env.feed(private_message(USER2, "/start", "Bob"))
    req = env.session.calls("SendMessage")[-1]
    assert "m:admin" not in {b.callback_data for b in buttons(req)}
    env.session.clear()
    await env.feed(cb(USER2, "m:admin"))
    assert "Super Admin" not in last_text(env) and "Dashboard" not in last_text(env)


async def test_legacy_moderator_and_username_grant_nothing(env):
    await connect(env, USER2, "bc2")
    await env.app.db.execute("INSERT INTO admin_roles(user_id, role, granted_by, granted_at) VALUES (?,?,?,?)", (USER2, "moderator", OWNER, 1))
    await env.app.users.upsert(USER2, "libPM", "Fake", None, "ru")
    assert await env.app.users.role(USER2) == "user"
    env.session.clear()
    await env.feed(private_message(USER2, ".logs", "Bob"))
    assert any("Недостаточно прав" in t for t in env.session.sent_texts())
    # REST API: a moderator row or a forged user id gives no admin access
    api_app = create_api(env.app)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=api_app), base_url="http://127.0.0.1") as api:
        code, _ = await env.app.auth.create_pairing_code(USER2)
        tok = (await api.post("/api/v1/auth/pair", json={"code": code, "device_id": "dev-mod", "device_name": "P"})).json()
        h = {"Authorization": f"Bearer {tok['access_token']}"}
        me = (await api.get("/api/v1/auth/me", headers=h)).json()
        assert me["role"] == "user" and "users" not in me["capabilities"]
        for path in ("/api/v1/users", f"/api/v1/users/{OWNER}", "/api/v1/system/backups"):
            r = await api.get(path, headers=h)
            assert r.status_code == 403, (path, r.status_code)
        r = await api.get("/api/v1/users", headers={**h, "X-User-Id": str(OWNER)}, params={"user_id": OWNER})
        assert r.status_code == 403


async def test_super_admin_panel_without_connection(env):
    await env.feed(private_message(OWNER, "/start"))
    req = env.session.calls("SendMessage")[-1]
    assert "m:admin" in {b.callback_data for b in buttons(req)}
    env.session.clear()
    await env.feed(cb(OWNER, "m:admin"))
    assert "Super Admin" in last_text(env)
    env.session.clear()
    await env.feed(private_message(OWNER, ".calc 6*7"))
    assert any("42" in t for t in env.session.sent_texts())


async def test_every_admin_section_renders_for_super_admin_only(env):
    from chat_helper.handlers.admin import SECTIONS
    await connect(env, USER2, "bc2")
    await env.feed(private_message(OWNER, "/start"))
    for key, _ in SECTIONS:
        env.session.clear()
        await env.feed(cb(OWNER, f"ax:{key}"))
        assert env.session.calls("EditMessageText") or env.session.calls("SendMessage"), key
        assert "⚠️ Внутренняя" not in last_text(env), key
    # actions: block/unblock and plan grant from the user card
    await env.feed(cb(OWNER, f"ax:uact:{USER2}:block"))
    assert await env.app.users.is_restricted(USER2)
    await env.feed(cb(OWNER, f"ax:uact:{USER2}:unblock"))
    await env.feed(cb(OWNER, f"ax:uact:{USER2}:grant_pro"))
    assert await env.app.subs.plan_of(USER2) == "pro"
    await env.feed(cb(OWNER, f"ax:uact:{OWNER}:block"))                  # the super admin cannot be blocked
    assert not await env.app.users.is_restricted(OWNER)
    # a regular user gets nothing from any ax: callback
    for key, _ in SECTIONS[:5]:
        env.session.clear()
        await env.feed(cb(USER2, f"ax:{key}"))
        ans = env.session.calls("AnswerCallbackQuery")[-1]
        assert ans.show_alert and "Недостаточно прав" in ans.text
    env.session.clear()
    await env.feed(cb(USER2, f"ax:uact:{USER2}:grant_vip"))
    assert await env.app.subs.plan_of(USER2) == "pro"


async def test_new_user_sections_render_after_connection(env):
    await connect(env, USER2, "bc2")
    await env.feed(private_message(USER2, "/start", "Bob"))
    req = env.session.calls("SendMessage")[-1]
    data = {b.callback_data for b in buttons(req)}
    for screen in ("account", "chats", "quick", "ai", "twin", "autoreply", "afk", "mutes", "protects", "media", "games", "texttools",
                   "reminders", "stats", "sub", "settings", "help", "delegation"):
        if screen != "delegation":
            assert f"m:{screen}" in data, screen
        env.session.clear()
        await env.feed(cb(USER2, f"m:{screen}"))
        assert env.session.calls("EditMessageText") or env.session.calls("SendMessage"), screen
    await env.feed(cb(USER2, "dg:ai"))
    assert await env.app.delegation.is_granted(USER2, "ai")
    await env.feed(cb(USER2, "dg:ai"))
    assert not await env.app.delegation.is_granted(USER2, "ai")


async def test_delegation_limits_admin_changes(env):
    await connect(env, USER2, "bc2")
    import pytest
    with pytest.raises(PermissionError):
        await env.app.delegation.admin_update_settings(OWNER, USER2, {"ai_style": "funny"})      # not granted yet
    await env.app.delegation.grant(USER2, "ai")
    s = await env.app.delegation.admin_update_settings(OWNER, USER2, {"ai_style": "funny"})
    assert s["ai_style"] == "funny"
    with pytest.raises(PermissionError):
        await env.app.delegation.admin_update_settings(OWNER, USER2, {"prefix": "!"})           # «commands» not granted
    with pytest.raises(PermissionError):
        await env.app.delegation.admin_update_settings(USER2, USER2, {"ai_style": "short"})     # only the super admin
    # profile: each change needs the user's confirmation
    with pytest.raises(PermissionError):
        await env.app.delegation.request_profile_change(OWNER, USER2, "bio", "Новое био")
    await env.app.delegation.grant(USER2, "profile")
    rid = await env.app.delegation.request_profile_change(OWNER, USER2, "bio", "Новое био")
    assert any("Применить?" in t for t in env.session.sent_texts())
    env.session.clear()
    await env.feed(cb(USER2, f"dlg:ok:{rid}"))
    assert env.session.calls("SetBusinessAccountBio")[-1].bio == "Новое био"
    assert await env.app.delegation.decide_profile_change(USER2, rid, True) == "already_decided"
    hist = await env.app.delegation.history(USER2)
    assert {h["action"] for h in hist} >= {"grant", "use", "request"}
