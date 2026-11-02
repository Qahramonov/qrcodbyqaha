"""Telegram user panel (private chat): /start, every menu screen, toggles, FSM flows, pairing code, profile, broadcast, privacy."""
from __future__ import annotations

import datetime as dt
import itertools

from aiogram.types import CallbackQuery, Chat, Message, Update, User
from conftest import OWNER, USER2
from fakes import business_connection, private_message, update_connection

_ids = itertools.count(1)


def cb(user_id: int, data: str, message_id: int = 10) -> Update:
    msg = Message(message_id=message_id, date=dt.datetime.now(dt.timezone.utc), chat=Chat(id=user_id, type="private"),
                  from_user=User(id=777, is_bot=True, first_name="bot"), text="menu")
    return Update(update_id=10_000 + next(_ids), callback_query=CallbackQuery(
        id=str(next(_ids)), from_user=User(id=user_id, is_bot=False, first_name="Owner", language_code="ru"), chat_instance="ci",
        message=msg, data=data))


async def test_start_and_all_screens(env):
    await env.feed(private_message(OWNER, "/start"))
    assert any("Chat helper" in t for t in env.session.sent_texts())
    for screen in ("home", "connect", "ai", "autoreply", "afk", "media", "games", "commands", "profile", "stats", "privacy", "sub",
                   "settings", "app", "help", "admin"):
        env.session.clear()
        await env.feed(cb(OWNER, f"m:{screen}"))
        edits = env.session.calls("EditMessageText") + env.session.calls("SendMessage")
        assert edits, f"screen {screen} rendered nothing"
        assert env.session.calls("AnswerCallbackQuery"), screen


async def test_admin_screen_hidden_for_regular_user(env):
    await env.feed(private_message(USER2, "/start", "Bob"))
    env.session.clear()
    await env.feed(cb(USER2, "m:admin"))
    text = (env.session.calls("EditMessageText") or env.session.calls("SendMessage"))[0].text
    assert "Администрирование" not in text


async def test_toggles_and_settings(env):
    await env.feed(private_message(OWNER, "/start"))
    await env.feed(cb(OWNER, "tg:ai_confirm"))
    assert (await env.app.settings.all(OWNER))["ai_confirm"] is True
    await env.feed(cb(OWNER, "st:lang:uz"))
    assert (await env.app.settings.all(OWNER))["lang"] == "uz"
    await env.feed(cb(OWNER, "st:prefix:!"))
    assert (await env.app.settings.all(OWNER))["prefix"] == "!"
    await env.feed(cb(OWNER, "tg:not_a_setting"))  # forged callback is ignored
    await env.feed(cb(OWNER, "mode:business"))
    assert (await env.app.settings.all(OWNER))["mode"] == "business"


async def test_afk_panel_flow(env):
    await env.feed(private_message(OWNER, "/start"))
    await env.feed(cb(OWNER, "afk:on:3600"))
    sess = await env.app.afk.active(OWNER)
    assert sess and sess["ends_at"]
    await env.feed(cb(OWNER, "afk:reason"))
    await env.feed(private_message(OWNER, "На встрече"))
    assert (await env.app.afk.active(OWNER))["reason"] == "На встрече"
    env.session.clear()
    await env.feed(cb(OWNER, "afk:preview"))
    assert any("На встрече" in t for t in env.session.sent_texts())
    await env.feed(cb(OWNER, "afk:off"))
    assert await env.app.afk.active(OWNER) is None


async def test_rule_creation_fsm(env):
    await env.feed(private_message(OWNER, "/start"))
    await env.feed(cb(OWNER, "ar:add"))
    await env.feed(private_message(OWNER, "доставка, delivery"))
    await env.feed(private_message(OWNER, "Доставка 1-2 дня"))
    rules = await env.app.autoreply.rules(OWNER)
    assert rules and rules[0]["response"] == "Доставка 1-2 дня"
    rid = rules[0]["id"]
    await env.feed(cb(USER2, f"ar:del:{rid}"))  # another user cannot delete it
    assert await env.app.autoreply.rules(OWNER)
    await env.feed(cb(OWNER, f"ar:del:{rid}"))
    assert not await env.app.autoreply.rules(OWNER)


async def test_pairing_code_via_app_button(env):
    await env.feed(private_message(OWNER, "/start"))
    env.session.clear()
    await env.feed(cb(OWNER, "app:pair"))
    assert any("Код для Chat helper Control" in t for t in env.session.sent_texts())
    assert await env.app.db.fetchval("SELECT COUNT(*) FROM pairing_codes WHERE user_id=?", (OWNER,)) == 1


async def test_profile_change_with_confirmation(env):
    bc = business_connection("bc1", OWNER)
    env.session.connections["bc1"] = bc
    await env.feed(update_connection(bc))
    await env.feed(private_message(OWNER, "/start"))
    await env.feed(cb(OWNER, "pr:bio"))
    await env.feed(private_message(OWNER, "Новый статус"))
    assert not env.session.calls("SetBusinessAccountBio")  # nothing applied before confirmation
    await env.feed(cb(OWNER, "pr:ok"))
    calls = env.session.calls("SetBusinessAccountBio")
    assert calls and calls[0].bio == "Новый статус" and calls[0].business_connection_id == "bc1"
    hist = await env.app.profile.history(OWNER)
    assert hist and hist[0]["field"] == "bio"


async def test_privacy_export_and_delete(env):
    await env.feed(private_message(OWNER, "/start"))
    await env.app.settings.set(OWNER, "lang", "ru")
    await env.feed(cb(OWNER, "pv:export"))
    assert env.session.calls("SendDocument")
    await env.feed(cb(USER2, "pv:del2"))  # deletes only the caller's own data
    await env.feed(cb(OWNER, "pv:del2"))
    assert await env.app.db.fetchval("SELECT COUNT(*) FROM user_settings WHERE user_id=?", (OWNER,)) == 0


async def test_promo_trial_and_dm_commands(env):
    bc = business_connection("bc2", USER2)
    env.session.connections["bc2"] = bc
    await env.feed(update_connection(bc))
    await env.feed(private_message(USER2, "/start", "Bob"))
    await env.feed(cb(USER2, "sub:trial"))
    assert await env.app.subs.plan_of(USER2) == "plus"
    await env.feed(cb(USER2, "sub:trial"))
    assert await env.app.db.fetchval("SELECT COUNT(*) FROM subscriptions WHERE user_id=?", (USER2,)) == 1
    env.session.clear()
    await env.feed(private_message(USER2, ".calc 7*6", "Bob"))
    assert any("42" in t for t in env.session.sent_texts())
    env.session.clear()
    await env.feed(private_message(USER2, "просто текст", "Bob"))
    assert any("/menu" in t for t in env.session.sent_texts())  # no AI configured → helpful hint


async def test_broadcast_admin_only(env):
    await env.feed(private_message(OWNER, "/start"))
    await env.feed(private_message(USER2, "/start", "Bob"))
    await env.feed(cb(USER2, "adm:bc"))
    await env.feed(private_message(USER2, "spam everyone", "Bob"))
    assert await env.app.db.fetchval("SELECT COUNT(*) FROM broadcasts") == 0
    bid = await env.app.broadcast.create(OWNER, text="Hello users!")
    res = await env.app.broadcast.start(bid, OWNER)
    assert res["total"] == 2
    import asyncio
    for _ in range(50):
        if (await env.app.broadcast.get(bid))["status"] == "done":
            break
        await asyncio.sleep(0.1)
    b = await env.app.broadcast.get(bid)
    assert b["status"] == "done" and b["sent"] == 2
    assert not any(getattr(r, "business_connection_id", None) for r in env.session.calls("SendMessage") if r.text == "Hello users!")


async def test_emergency_toggle_super_only(env):
    await env.feed(private_message(USER2, "/start", "Bob"))
    await env.feed(cb(USER2, "adm:es"))
    assert env.app.runtime.emergency_stop is False
    await env.feed(private_message(OWNER, "/start"))
    await env.feed(cb(OWNER, "adm:es"))
    assert env.app.runtime.emergency_stop is True


async def test_maintenance_mode_blocks_regular_users(env):
    env.app.runtime.maintenance = True
    env.session.clear()
    await env.feed(private_message(USER2, "/start", "Bob"))
    assert any("обслуживании" in t for t in env.session.sent_texts())
