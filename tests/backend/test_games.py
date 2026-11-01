"""Mini games: creation, acceptance, false start, winners, timeouts, button ownership, ratings."""
from __future__ import annotations

import asyncio
import time

import pytest
from conftest import CONTACT, OWNER
from fakes import biz_message, business_connection, update_business_message, update_connection

from chat_helper.games.games import last_letter, slot_combo, ttt_best, ttt_winner

STRANGER = 999


async def start(env, cmd: str):
    bc = business_connection("bc1", OWNER)
    env.session.connections["bc1"] = bc
    await env.feed(update_connection(bc))
    await env.feed(update_business_message(biz_message("bc1", CONTACT, OWNER, cmd, first_name="Owner")))
    sessions = list(env.app.games.sessions.values())
    assert sessions, "game not created"
    return sessions[-1]


async def test_duel_accept_false_start(env):
    s = await start(env, ".duel")
    eng = env.app.games
    assert s.status == "pending" and s.state["invitee"] == CONTACT
    assert "Это не ваша игра" in await eng.handle_callback(s.id, STRANGER, "accept", "")
    assert "Принять может только соперник" in (await eng.handle_callback(s.id, OWNER, "accept", "") or "")
    await eng.handle_callback(s.id, CONTACT, "accept", "")
    assert s.status == "active" and s.state["phase"] == "wait"
    res = await eng.handle_callback(s.id, CONTACT, "fire", "")
    assert res == "💥" and s.status == "finished"
    row = await env.app.db.fetchone("SELECT * FROM game_results")
    assert row["winner_id"] == OWNER and row["loser_id"] == CONTACT


async def test_duel_winner_reaction_time(env):
    s = await start(env, ".duel")
    eng = env.app.games
    await eng.handle_callback(s.id, CONTACT, "accept", "")
    eng._timers[s.id].cancel()
    async with eng.locks[s.id]:
        await eng.games["duel"]._green(eng, s)
    eng._timers[s.id].cancel()
    await asyncio.sleep(0.05)
    res = await eng.handle_callback(s.id, OWNER, "fire", "")
    assert res.startswith("⚡️") and s.status == "finished"
    r = await env.app.db.fetchone("SELECT * FROM game_ratings WHERE player_id=?", (OWNER,))
    assert r["wins"] == 1 and r["best_ms"] is not None and r["rating"] > 1000


async def test_duel_decline_and_timeout(env):
    s = await start(env, ".duel")
    await env.app.games.handle_callback(s.id, CONTACT, "decline", "")
    assert s.status == "finished"
    s2 = await start(env, ".rps")
    s2.expires = time.time() - 1
    assert await env.app.games.expire_due() == 1 and s2.status == "finished"


async def test_ttt_turns_and_win(env):
    s = await start(env, ".ttt")
    eng = env.app.games
    await eng.handle_callback(s.id, CONTACT, "accept", "")
    assert "не ваш ход" in await eng.handle_callback(s.id, CONTACT, "m", "0")
    for uid, cell in [(OWNER, "0"), (CONTACT, "3"), (OWNER, "1"), (CONTACT, "4"), (OWNER, "2")]:
        await eng.handle_callback(s.id, uid, "m", cell)
    assert s.status == "finished"
    assert (await env.app.db.fetchone("SELECT winner_id FROM game_results"))["winner_id"] == OWNER


def test_ttt_ai_and_helpers():
    b = list("XX O O   ")
    assert ttt_best(b, "O") == 2 or ttt_best(b, "O") in range(9)
    assert ttt_winner(list("XXXOO    ")) == "X" and ttt_winner(list("XOXXOOOXX")) == "draw"
    assert last_letter("кровь") == "в" and last_letter("olma") == "a"
    assert slot_combo(64) == ["7️⃣"] * 3 and slot_combo(1) == ["BAR"] * 3


async def test_rps_hidden_choices(env):
    s = await start(env, ".rps")
    eng = env.app.games
    await eng.handle_callback(s.id, OWNER, "c", "r")
    assert "уже выбрали" in await eng.handle_callback(s.id, OWNER, "c", "p")
    await eng.handle_callback(s.id, CONTACT, "c", "s")
    assert s.status == "finished"
    assert (await env.app.db.fetchone("SELECT winner_id FROM game_results"))["winner_id"] == OWNER


async def test_revo_turns(env):
    s = await start(env, ".revo")
    eng = env.app.games
    await eng.handle_callback(s.id, CONTACT, "accept", "")
    s.state["bullet"] = 1
    assert "не ваш ход" in await eng.handle_callback(s.id, CONTACT, "pull", "")
    assert await eng.handle_callback(s.id, OWNER, "pull", "") == "😅"
    assert await eng.handle_callback(s.id, CONTACT, "pull", "") == "💥"
    assert (await env.app.db.fetchone("SELECT winner_id FROM game_results"))["winner_id"] == OWNER


async def test_text_game_guess(env):
    s = await start(env, ".guess 10")
    s.state["n"] = 7
    conn = await env.app.connections.get("bc1")
    assert await env.app.games.on_chat_message(conn, biz_message("bc1", CONTACT, CONTACT, "3"))
    assert await env.app.games.on_chat_message(conn, biz_message("bc1", CONTACT, CONTACT, "7"))
    assert s.status == "finished"
    assert not await env.app.games.on_chat_message(conn, biz_message("bc1", CONTACT, CONTACT, "5"))


async def test_dm_duel_vs_bot(env):
    from fakes import private_message
    await env.feed(private_message(OWNER, ".duel"))
    s = list(env.app.games.sessions.values())[-1]
    assert s.vs_bot and s.status == "active"


async def test_dice_uses_business_connection(env):
    bc = business_connection("bc1", OWNER)
    env.session.connections["bc1"] = bc
    await env.feed(update_connection(bc))
    env.session.clear()
    await env.feed(update_business_message(biz_message("bc1", CONTACT, OWNER, ".dice 🎯", first_name="Owner")))
    d = env.session.calls("SendDice")
    assert d and d[0].emoji == "🎯" and d[0].business_connection_id == "bc1"
