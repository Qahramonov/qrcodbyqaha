"""Telegram Business engine: connections, rights, isolation, incoming/outgoing routing, loops, duplicates, 24h errors."""
from __future__ import annotations

from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import SendMessage
from conftest import CONTACT, OWNER, USER2
from fakes import biz_message, business_connection, update_business_message, update_connection



async def connect(env, conn_id="bc1", owner=OWNER, **rights):
    bc = business_connection(conn_id, owner, **rights)
    env.session.connections[conn_id] = bc
    await env.feed(update_connection(bc))
    return await env.app.connections.get(conn_id)


async def test_new_connection_registers_owner_and_rights(env):
    conn = await connect(env)
    assert conn.user_id == OWNER and conn.is_enabled and conn.status == "connected"
    assert conn.rights["can_reply"] and conn.rights["can_delete_all_messages"]
    texts = env.session.sent_texts()
    assert any("подключён" in t for t in texts)  # welcome + permission report sent to the owner
    user = await env.app.users.get(OWNER)
    assert user and user["username"] == f"owner{OWNER}"


async def test_disconnect_and_rights_change(env):
    await connect(env)
    env.session.clear()
    bc = business_connection("bc1", OWNER, can_delete_all_messages=False)
    await env.feed(update_connection(bc))
    conn = await env.app.connections.get("bc1")
    assert conn.rights["can_delete_all_messages"] is False
    assert any("Права" in t for t in env.session.sent_texts())
    await env.feed(update_connection(business_connection("bc1", OWNER, enabled=False)))
    conn = await env.app.connections.get("bc1")
    assert not conn.is_enabled and conn.status == "disabled"


async def test_missing_reply_right_status(env):
    conn = await connect(env, can_reply=False)
    assert conn.status == "missing_permission"


async def test_multiple_connections_isolated(env):
    await connect(env, "bcA", OWNER)
    await connect(env, "bcB", USER2)
    a = await env.app.connections.for_user(OWNER)
    b = await env.app.connections.for_user(USER2)
    assert [c.id for c in a] == ["bcA"] and [c.id for c in b] == ["bcB"]
    await env.app.settings.set(USER2, "mode", "silent")
    assert (await env.app.settings.all(OWNER))["mode"] == "manual"


async def test_restore_after_restart(env):
    await connect(env)
    stats = await env.app.connections.restore(env.bot)
    assert stats == {"checked": 1, "updated": 1, "failed": 0}
    env.session.connections.clear()
    stats = await env.app.connections.restore(env.bot)
    assert stats["failed"] == 1
    assert (await env.app.connections.get("bc1")).status == "reconnection_required"


async def test_owner_command_is_executed_and_edited_in_place(env):
    await connect(env)
    env.session.clear()
    msg = biz_message("bc1", CONTACT, OWNER, ".calc 2+2*2", first_name="Owner")
    await env.feed(update_business_message(msg))
    edits = env.session.calls("EditMessageText")
    assert edits and "6" in edits[0].text and edits[0].business_connection_id == "bc1"


async def test_contact_cannot_run_owner_commands(env):
    await connect(env)
    env.session.clear()
    await env.feed(update_business_message(biz_message("bc1", CONTACT, CONTACT, ".calc 1+1")))
    assert not env.session.calls("EditMessageText")


async def test_messages_sent_by_bot_are_ignored(env):
    await connect(env)
    await env.app.afk.enable(OWNER, "test")
    env.session.clear()
    res = await env.app.pipeline.on_message(await env.app.connections.get("bc1"),
                                            biz_message("bc1", CONTACT, OWNER, "💤 AFK", via_bot=True))
    assert res == "own_bot_echo"
    assert not env.session.calls("SendMessage")


async def test_afk_auto_reply_and_cooldown(env):
    await connect(env)
    await env.app.afk.enable(OWNER, "Занят делами")
    env.session.clear()
    await env.feed(update_business_message(biz_message("bc1", CONTACT, CONTACT, "привет")))
    sends = [r for r in env.session.calls("SendMessage") if r.chat_id == CONTACT]
    assert len(sends) == 1 and "Занят делами" in sends[0].text and sends[0].business_connection_id == "bc1"
    await env.feed(update_business_message(biz_message("bc1", CONTACT, CONTACT, "ты тут?")))
    sends = [r for r in env.session.calls("SendMessage") if r.chat_id == CONTACT]
    assert len(sends) == 1  # cooldown
    sess = await env.app.afk.active(OWNER)
    assert sess["messages_received"] == 2 and sess["replies_sent"] == 1


async def test_afk_auto_off_when_owner_writes(env):
    await connect(env)
    await env.app.afk.enable(OWNER, "away")
    await env.feed(update_business_message(biz_message("bc1", CONTACT, CONTACT, "hi")))
    env.session.clear()
    await env.feed(update_business_message(biz_message("bc1", CONTACT, OWNER, "я тут", first_name="Owner")))
    assert await env.app.afk.active(OWNER) is None
    assert any("AFK" in t for t in env.session.sent_texts())  # summary sent to owner


async def test_duplicate_updates_ignored(env):
    await connect(env)
    await env.app.afk.enable(OWNER, "x")
    env.session.clear()
    msg = biz_message("bc1", CONTACT, CONTACT, "hello", message_id=999)
    conn = await env.app.connections.get("bc1")
    assert await env.app.pipeline.on_message(conn, msg) == "afk_reply"
    assert await env.app.pipeline.on_message(conn, msg) == "duplicate"


async def test_no_reply_to_other_bots(env):
    await connect(env)
    await env.app.afk.enable(OWNER, "x")
    env.session.clear()
    conn = await env.app.connections.get("bc1")
    out = await env.app.pipeline.on_message(conn, biz_message("bc1", CONTACT, CONTACT, "I am a bot", sender_is_bot=True))
    assert out == "blocked:counterpart_is_bot"
    assert not env.session.calls("SendMessage")


async def test_loop_guard_limits_auto_replies(env):
    await connect(env)
    await env.app.autoreply.set_mode(OWNER, "auto")
    await env.app.autoreply.add_rule(OWNER, {"trigger_type": "keyword", "pattern": "ping", "response": "pong", "cooldown_sec": 0})
    conn = await env.app.connections.get("bc1")
    results = []
    for i in range(10):
        results.append(await env.app.pipeline.on_message(conn, biz_message("bc1", CONTACT, CONTACT, f"ping {i}")))
    assert results.count("rule_reply") == env.app.loop_guard.max_replies
    assert any(r.startswith("blocked:") for r in results)


async def test_owner_reply_pauses_automation(env):
    await connect(env)
    await env.app.autoreply.set_mode(OWNER, "auto")
    await env.app.autoreply.add_rule(OWNER, {"trigger_type": "keyword", "pattern": "цена", "response": "100$", "cooldown_sec": 0})
    conn = await env.app.connections.get("bc1")
    await env.app.pipeline.on_message(conn, biz_message("bc1", CONTACT, OWNER, "сейчас отвечу", first_name="Owner"))
    out = await env.app.pipeline.on_message(conn, biz_message("bc1", CONTACT, CONTACT, "цена?"))
    assert out == "blocked:owner_active"


async def test_24h_window_error_falls_back_to_owner_dm(env):
    await connect(env)
    env.session.clear()
    err = TelegramBadRequest(method=SendMessage(chat_id=CONTACT, text="x"), message="Bad Request: BUSINESS_PEER_USAGE_MISSING")
    env.session.fail["EditMessageText"] = TelegramBadRequest(method=SendMessage(chat_id=CONTACT, text="x"), message="Bad Request: message can't be edited")
    env.session.fail["SendMessage"] = err
    err._once = True  # only the first send (into the business chat) fails
    await env.feed(update_business_message(biz_message("bc1", CONTACT, OWNER, ".uuid", first_name="Owner")))
    sends = env.session.calls("SendMessage")
    assert sends[0].chat_id == CONTACT and sends[-1].chat_id == OWNER
    assert "24" in sends[-1].text


async def test_paused_connection_does_not_auto_reply(env):
    conn = await connect(env)
    await env.app.afk.enable(OWNER, "x")
    await env.app.connections.set_paused(conn.id, OWNER, True)
    env.session.clear()
    out = await env.app.pipeline.on_message(await env.app.connections.get("bc1"), biz_message("bc1", CONTACT, CONTACT, "hello"))
    assert out == "blocked:connection_inactive"


async def test_emergency_stop_blocks_automation(env):
    await connect(env)
    await env.app.afk.enable(OWNER, "x")
    env.app.runtime.emergency_stop = True
    out = await env.app.pipeline.on_message(await env.app.connections.get("bc1"), biz_message("bc1", CONTACT, CONTACT, "hello"))
    assert out == "blocked:emergency_stop"


async def test_deleted_and_edited_updates(env):
    from aiogram.types import BusinessMessagesDeleted, Chat, Update
    await connect(env)
    await env.feed(Update(update_id=99999, deleted_business_messages=BusinessMessagesDeleted(
        business_connection_id="bc1", chat=Chat(id=CONTACT, type="private"), message_ids=[1, 2])))
    from chat_helper.core.timeutil import today
    v = await env.app.db.fetchval("SELECT value FROM daily_metrics WHERE metric='messages_deleted' AND user_id=? AND day=?", (OWNER, today()))
    assert v == 2


async def test_permission_inspector_blocks_command_without_right(env):
    await connect(env, can_edit_bio=False)
    env.session.clear()
    await env.feed(update_business_message(biz_message("bc1", CONTACT, OWNER, ".bio new", first_name="Owner")))
    dm = [r for r in env.session.calls("SendMessage") if r.chat_id == OWNER]
    assert dm and "Не хватает прав" in dm[0].text
