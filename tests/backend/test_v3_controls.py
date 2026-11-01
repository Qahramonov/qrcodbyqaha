"""v3 Chat Control Framework + Mute engine + Protect + filters + Chat Context Manager (real dispatcher, fake Bot API)."""
from __future__ import annotations

import datetime as dt
import itertools
import time

from aiogram.types import Animation, CallbackQuery, Chat, Message, Sticker, Update, User
from conftest import CONTACT, OWNER, USER2
from fakes import biz_message, business_connection, private_message, update_business_message, update_connection
from test_panel import cb

_ids = itertools.count(1)
CONTACT2 = 5550000002


async def connect(env, uid=OWNER, conn_id="bc1", **rights):
    bc = business_connection(conn_id, uid, **rights)
    env.session.connections[conn_id] = bc
    await env.feed(update_connection(bc))
    return bc


async def say(env, sender, text=None, chat=CONTACT, conn_id="bc1", **extra):
    m = biz_message(conn_id, chat, sender, text, **extra)
    await env.feed(update_business_message(m))
    return m


def press(user_id: int, data: str, chat_id: int = CONTACT, cb_id: str | None = None) -> Update:
    msg = Message(message_id=9000 + next(_ids), date=dt.datetime.now(dt.timezone.utc), chat=Chat(id=chat_id, type="private"),
                  from_user=User(id=777, is_bot=True, first_name="bot"), text="card")
    return Update(update_id=50_000 + next(_ids), callback_query=CallbackQuery(
        id=cb_id or f"cbq{next(_ids)}", from_user=User(id=user_id, is_bot=False, first_name="U"), chat_instance="ci", message=msg, data=data))


def card_buttons(req) -> dict[str, str]:
    mk = getattr(req, "reply_markup", None)
    return {b.text: b.callback_data for row in (mk.inline_keyboard if mk else []) for b in row if b.callback_data}


def deletes(env) -> list[int]:
    return [i for r in env.session.calls("DeleteBusinessMessages") for i in r.message_ids]


def find(buttons: dict[str, str], word: str) -> str:
    return next(v for k, v in buttons.items() if word in k)


async def enable_mute(env, chat=CONTACT, extra: str = ""):
    """Owner types .mute, confirms in the DM (first time)."""
    await say(env, OWNER, (".mute " + extra).strip(), chat=chat)
    confirm = [r for r in env.session.calls("SendMessage") if r.chat_id == OWNER and "Включить Mute" in (r.text or "")][-1]
    data = find(card_buttons(confirm), "Включить")
    env.session.clear()
    await env.feed(press(OWNER, data, chat_id=OWNER))
    return confirm


# ---- mute -----------------------------------------------------------------------------------------------------------
async def test_mute_requires_confirmation_then_deletes_only_new_incoming(env):
    await connect(env)
    old = await say(env, CONTACT, "старое сообщение")
    env.session.clear()
    await say(env, OWNER, ".mute")
    confirm = [r for r in env.session.calls("SendMessage") if r.chat_id == OWNER][-1]
    assert "Включить Mute" in confirm.text and "необратимо" in confirm.text
    assert not await env.app.controls.is_on(OWNER, CONTACT, "mute")       # nothing happens before confirmation
    data = find(card_buttons(confirm), "Включить")
    env.session.clear()
    await env.feed(press(OWNER, data, chat_id=OWNER))
    assert await env.app.controls.is_on(OWNER, CONTACT, "mute")
    chat_card = [r for r in env.session.calls("SendMessage") if r.chat_id == CONTACT][-1]
    assert "Режим Mute включён" in chat_card.text and chat_card.business_connection_id == "bc1"
    assert "Снять Mute" in " ".join(card_buttons(chat_card))
    env.session.clear()
    incoming = await say(env, CONTACT, "привет, ты тут?")
    assert deletes(env) == [incoming.message_id]
    assert old.message_id not in deletes(env)                              # history untouched
    assert not [r for r in env.session.calls("SendMessage") if r.chat_id == CONTACT]   # no auto replies to deleted messages
    row = await env.app.controls.get(OWNER, CONTACT, "mute")
    assert row["state"]["deleted"] == 1
    assert await env.app.db.fetchval("SELECT result FROM mute_events WHERE message_id=?", (incoming.message_id,)) == "deleted"
    # owner's own messages and other chats are never touched
    env.session.clear()
    await say(env, OWNER, "это пишу я")
    await say(env, CONTACT2, "другой чат", chat=CONTACT2)
    assert deletes(env) == []


async def test_duplicate_update_is_not_deleted_twice(env):
    await connect(env)
    await enable_mute(env)
    m = biz_message("bc1", CONTACT, CONTACT, "раз")
    env.session.clear()
    await env.feed(update_business_message(m))
    await env.app.filters.handle_incoming(await env.app.connections.get("bc1"), m)   # redelivery
    assert deletes(env) == [m.message_id]


async def test_counterpart_cannot_press_owner_buttons(env):
    await connect(env)
    await enable_mute(env)
    card = [c for c in await env.app.controls.cards(OWNER, CONTACT, "mute") if c["location"] == "chat"][0]
    data = f"cc:{card['token']}:off:{card['version']}"
    env.session.clear()
    await env.feed(press(CONTACT, data))
    ans = env.session.calls("AnswerCallbackQuery")[-1]
    assert ans.show_alert and "только владелец" in ans.text
    assert await env.app.controls.is_on(OWNER, CONTACT, "mute")
    assert await env.app.db.fetchval("SELECT COUNT(*) FROM audit_logs WHERE action='controls.foreign_press'") == 1


async def test_owner_unmutes_with_button_and_stale_or_duplicate_presses_do_nothing(env):
    await connect(env)
    await enable_mute(env)
    card = [c for c in await env.app.controls.cards(OWNER, CONTACT, "mute") if c["location"] == "chat"][0]
    off = f"cc:{card['token']}:off:{card['version']}"
    env.session.clear()
    await env.feed(press(OWNER, off, cb_id="same-id"))
    assert not await env.app.controls.is_on(OWNER, CONTACT, "mute")
    edited = [r for r in env.session.calls("EditMessageText") if r.chat_id == CONTACT][-1]
    assert "Mute отключён" in edited.text and edited.business_connection_id == "bc1"
    assert "Включить снова" in " ".join(card_buttons(edited))
    # an old button with the previous version cannot flip the state again
    await env.feed(press(OWNER, f"cc:{card['token']}:on:{card['version']}"))
    assert not await env.app.controls.is_on(OWNER, CONTACT, "mute")
    assert "уже изменилось" in env.session.calls("AnswerCallbackQuery")[-1].text
    # a redelivered callback id is ignored
    fresh = await env.app.controls.card(card["token"])
    await env.app.controls.record_action("dup-1", card["token"], OWNER, "on", "accepted")
    await env.feed(press(OWNER, f"cc:{card['token']}:on:{fresh['version']}", cb_id="dup-1"))
    assert not await env.app.controls.is_on(OWNER, CONTACT, "mute")
    env.session.clear()
    m = await say(env, CONTACT, "теперь можно")
    assert m.message_id not in deletes(env)


async def test_buttons_stop_working_after_connection_is_revoked(env):
    await connect(env)
    await enable_mute(env)
    card = [c for c in await env.app.controls.cards(OWNER, CONTACT, "mute") if c["location"] == "chat"][0]
    bc = business_connection("bc1", OWNER, enabled=False)
    env.session.connections["bc1"] = bc
    await env.feed(update_connection(bc))
    env.session.clear()
    await env.feed(press(OWNER, f"cc:{card['token']}:off:{card['version']}"))
    ans = env.session.calls("AnswerCallbackQuery")[-1]
    assert ans.show_alert and ("отключён" in ans.text or "не активно" in ans.text)
    assert (await env.app.controls.card(card["token"]))["status"] == "revoked"


async def test_mute_timer_expires_and_survives_restart(env):
    await connect(env)
    await env.app.settings.set(OWNER, "mute_confirmed", True)
    await say(env, OWNER, ".mute 10m")
    row = await env.app.controls.get(OWNER, CONTACT, "mute")
    assert row["enabled"] and 590 <= row["until_at"] - time.time() <= 600
    env.app.controls.invalidate()                      # "restart": state is read back from SQLite
    assert await env.app.controls.is_on(OWNER, CONTACT, "mute")
    await env.app.db.execute("UPDATE chat_control_states SET until_at=? WHERE owner_id=? AND module='mute'", (int(time.time()) - 1, OWNER))
    env.app.controls.invalidate()
    env.session.clear()
    job = next(j for j in env.app.scheduler.periodic if j["name"] == "controls_expiry")
    await job["fn"]()
    assert not await env.app.controls.is_on(OWNER, CONTACT, "mute")
    notice = [r for r in env.session.calls("SendMessage") if r.chat_id == OWNER][-1]
    assert "истекло" in notice.text and "Удалено сообщений" in notice.text
    card_edit = [r for r in env.session.calls("EditMessageText") if r.chat_id == CONTACT][-1]
    assert "Mute отключён" in card_edit.text


async def test_mute_time_picker_and_types(env):
    await connect(env)
    await env.app.settings.set(OWNER, "mute_confirmed", True)
    await say(env, OWNER, ".mute gif")
    card = [c for c in await env.app.controls.cards(OWNER, CONTACT, "mute") if c["location"] == "chat"][0]
    env.session.clear()
    await env.feed(press(OWNER, f"cc:{card['token']}:time:{card['version']}"))
    picker = env.session.calls("EditMessageText")[-1]
    assert "Выберите длительность" in picker.text
    one_hour = find(card_buttons(picker), "1 ч")
    await env.feed(press(OWNER, one_hour))
    row = await env.app.controls.get(OWNER, CONTACT, "mute")
    assert 3500 < row["until_at"] - time.time() <= 3600
    env.session.clear()
    text_msg = await say(env, CONTACT, "текст остаётся")
    gif = await say(env, CONTACT, None, animation=Animation(file_id="a1", file_unique_id="a1u", width=1, height=1, duration=1))
    assert deletes(env) == [gif.message_id] and text_msg.message_id not in deletes(env)


async def test_mute_needs_delete_right(env):
    await connect(env, can_delete_all_messages=False)
    env.session.clear()
    await say(env, OWNER, ".mute")
    assert not await env.app.controls.is_on(OWNER, CONTACT, "mute")
    assert any("Удал" in t or "удал" in t for t in env.session.sent_texts())


async def test_first_edit_turns_command_into_card_or_falls_back(env):
    await connect(env)
    await env.app.settings.set(OWNER, "mute_confirmed", True)
    cmd = await say(env, OWNER, ".mute")
    card = [c for c in await env.app.controls.cards(OWNER, CONTACT, "mute") if c["location"] == "chat"][0]
    assert card["message_id"] == cmd.message_id          # the command message became the card
    await say(env, OWNER, ".unmute")
    env.session.drop_markup = True                     # a server that drops keyboards on edits → new message instead
    env.session.clear()
    cmd2 = await say(env, OWNER, ".mute")
    cards = [c for c in await env.app.controls.cards(OWNER, CONTACT, "mute") if c["location"] == "chat"]
    assert cards[0]["message_id"] != cmd2.message_id
    assert cmd2.message_id in deletes(env)


async def test_dm_place_setting(env):
    await connect(env)
    await env.app.settings.set(OWNER, "mute_confirmed", True)
    await env.app.settings.set(OWNER, "controls_place", "dm")
    env.session.clear()
    await say(env, OWNER, ".mute")
    cards = await env.app.controls.cards(OWNER, CONTACT, "mute")
    assert cards[0]["location"] == "dm" and cards[0]["host_chat_id"] == OWNER
    assert not [r for r in env.session.calls("SendMessage") if r.chat_id == CONTACT]


# ---- protect, .g, filters ------------------------------------------------------------------------------------------
async def test_protect_marks_chat_helper_messages(env):
    await connect(env)
    await say(env, OWNER, ".protect")
    assert await env.app.controls.is_on(OWNER, CONTACT, "protect")
    await say(env, OWNER, ".afk Встреча")
    env.session.clear()
    await say(env, CONTACT, "привет")
    replies = [r for r in env.session.calls("SendMessage") if r.chat_id == CONTACT]
    assert replies and all(r.protect_content for r in replies)
    await say(env, OWNER, ".unprotect")
    await say(env, OWNER, ".unafk")
    assert not await env.app.controls.is_on(OWNER, CONTACT, "protect")


async def test_g_sends_protected_message_and_removes_command(env):
    await connect(env)
    env.session.clear()
    cmd = await say(env, OWNER, ".g Код 4521")
    sent = [r for r in env.session.calls("SendMessage") if r.chat_id == CONTACT][-1]
    assert sent.protect_content and sent.text == "Код 4521"
    assert cmd.message_id in deletes(env)


async def test_nogif_and_word_filter(env):
    await connect(env)
    await say(env, OWNER, ".nogif")
    await say(env, OWNER, ".nomute add казино")
    env.session.clear()
    st = await say(env, CONTACT, None, sticker=Sticker(file_id="s1", file_unique_id="s1u", type="regular", width=1, height=1,
                                                       is_animated=False, is_video=False))
    spam = await say(env, CONTACT, "Лучшее КАЗИНО тут")
    ok = await say(env, CONTACT, "казинозавр — это не слово из списка")
    assert set(deletes(env)) == {st.message_id, spam.message_id}
    assert ok.message_id not in deletes(env)
    await say(env, OWNER, ".nogif off")
    await say(env, OWNER, ".nomute off")
    env.session.clear()
    st2 = await say(env, CONTACT, None, sticker=Sticker(file_id="s2", file_unique_id="s2u", type="regular", width=1, height=1,
                                                        is_animated=False, is_video=False))
    assert st2.message_id not in deletes(env)


# ---- chat context manager --------------------------------------------------------------------------------------------
async def test_bizchat_deeplink_opens_only_verified_chats(env):
    await connect(env)
    await say(env, CONTACT, "привет")                    # chat becomes known for OWNER
    await connect(env, USER2, "bc2")
    await say(env, CONTACT2, "чужой чат", chat=CONTACT2, conn_id="bc2")
    env.session.clear()
    await env.feed(private_message(OWNER, f"/start bizChat{CONTACT}"))
    panel = env.session.calls("SendMessage")[-1]
    assert "Управление чатом" in panel.text and "Alice" in panel.text
    env.session.clear()
    await env.feed(private_message(OWNER, f"/start bizChat{CONTACT2}"))   # exists only for USER2
    assert "Не удалось подтвердить" in env.session.calls("SendMessage")[-1].text
    env.session.clear()
    await env.feed(private_message(OWNER, "/start bizChatabc"))
    assert "Не удалось подтвердить" in env.session.calls("SendMessage")[-1].text
    assert await env.app.db.fetchval("SELECT COUNT(*) FROM audit_logs WHERE action='chat_context.deeplink'") == 3


async def test_chat_panel_toggles_are_scoped_to_owner(env):
    await connect(env)
    await say(env, CONTACT, "привет")
    await env.feed(private_message(OWNER, "/start"))
    env.session.clear()
    await env.feed(cb(OWNER, f"ch:{CONTACT}:protect"))
    assert await env.app.controls.is_on(OWNER, CONTACT, "protect")
    await connect(env, USER2, "bc2")
    env.session.clear()
    await env.feed(cb(USER2, f"ch:{CONTACT}:protect"))                   # not USER2's chat
    assert env.session.calls("AnswerCallbackQuery")[-1].show_alert
    assert not await env.app.controls.is_on(USER2, CONTACT, "protect")
    env.session.clear()
    await env.feed(cb(OWNER, f"ch:{CONTACT}:mute"))                      # first time → warning, nothing enabled yet
    assert "Включить Mute" in env.session.sent_texts()[-1]
    assert not await env.app.controls.is_on(OWNER, CONTACT, "mute")
    await env.feed(cb(OWNER, f"ch:{CONTACT}:mute:ok"))
    assert await env.app.controls.is_on(OWNER, CONTACT, "mute")


async def test_my_chats_list_and_history_storage(env):
    await connect(env)
    await say(env, CONTACT, "первое")
    await say(env, OWNER, "ответ")
    rows = await env.app.db.fetchall("SELECT outgoing, text FROM chat_messages WHERE owner_id=? AND chat_id=? ORDER BY id", (OWNER, CONTACT))
    assert [(r["outgoing"], r["text"]) for r in rows] == [(0, "первое"), (1, "ответ")]
    from chat_helper.modules.ai_cmds import chat_history_text
    assert await chat_history_text(env.app, OWNER, CONTACT, 10) == "Them: первое\nMe: ответ"
    await env.feed(private_message(OWNER, "/start"))
    env.session.clear()
    await env.feed(cb(OWNER, "m:chats"))
    req = (env.session.calls("EditMessageText") or env.session.calls("SendMessage"))[-1]
    assert "Мои чаты" in req.text and f"ch:{CONTACT}:open" in card_buttons(req).values()


# ---- AFK / auto / online cards ---------------------------------------------------------------------------------------
async def test_afk_card_buttons(env):
    await connect(env)
    env.session.clear()
    cmd = await say(env, OWNER, ".afk Обед")
    card = [c for c in await env.app.controls.cards(OWNER, CONTACT, "afk") if c["location"] == "chat"][0]
    assert card["message_id"] == cmd.message_id
    edit = [r for r in env.session.calls("EditMessageText") if r.chat_id == CONTACT][-1]
    assert "AFK включён" in edit.text and "Обед" in edit.text
    btns = card_buttons(edit)
    assert {"⏹ Выключить AFK", "📝 Изменить текст", "⏰ Таймер"} <= set(btns)
    # timer: 1 hour
    await env.feed(press(OWNER, btns["⏰ Таймер"]))
    picker = env.session.calls("EditMessageText")[-1]
    await env.feed(press(OWNER, find(card_buttons(picker), "1 ч")))
    sess = await env.app.afk.active(OWNER)
    assert sess and sess["reason"] == "Обед" and 3500 < sess["ends_at"] - time.time() <= 3600
    # change text via DM FSM
    card = await env.app.controls.card(card["token"])
    await env.feed(press(OWNER, f"cc:{card['token']}:text:{card['version']}"))
    assert "Пришлите новый текст" in env.session.sent_texts()[-1]
    await env.feed(private_message(OWNER, "На встрече до 15:00"))
    sess = await env.app.afk.active(OWNER)
    assert sess["reason"] == "На встрече до 15:00" and sess["ends_at"]
    # off — every AFK card follows the state
    card = await env.app.controls.card(card["token"])
    env.session.clear()
    await env.feed(press(OWNER, f"cc:{card['token']}:off:{card['version']}"))
    assert not await env.app.afk.active(OWNER)
    assert "AFK выключен" in [r for r in env.session.calls("EditMessageText") if r.chat_id == CONTACT][-1].text


async def test_auto_card_and_online_is_honest(env):
    await connect(env)
    env.session.clear()
    await say(env, OWNER, ".auto hybrid")
    card = [c for c in await env.app.controls.cards(OWNER, CONTACT, "auto")][0]
    await env.feed(press(OWNER, f"cc:{card['token']}:off:{card['version']}"))
    assert await env.app.settings.get(OWNER, "mode") == "manual"
    card = await env.app.controls.card(card["token"])
    await env.feed(press(OWNER, f"cc:{card['token']}:on:{card['version']}"))
    assert await env.app.settings.get(OWNER, "mode") == "hybrid"
    env.session.clear()
    await say(env, OWNER, ".online")
    dm = [r for r in env.session.calls("SendMessage") if r.chat_id == OWNER][-1]
    assert "NOT_SUPPORTED_BY_OFFICIAL_API" in dm.text
    assert not env.session.calls("SendChatAction")                  # no fake "online" via typing
    btn = find(card_buttons(dm), "Chat Activity")
    await env.feed(press(OWNER, btn, chat_id=OWNER))
    assert await env.app.settings.get(OWNER, "chat_activity") is True
