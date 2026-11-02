"""Command engine: parsing, aliases, prefixes, owner checks, permissions, unknown commands, arguments, sandbox, text tools."""
from __future__ import annotations

import pytest
from conftest import CONTACT, OWNER, USER2
from fakes import biz_message, business_connection, private_message, update_business_message, update_connection

from chat_helper.commands.parser import parse
from chat_helper.utils.calc import CalcError, evaluate
from chat_helper.utils.textfix import fix_text



def test_parser_variants():
    assert parse(".afk busy").name == "afk"
    assert parse(".AFK Busy").name == "afk" and parse(".AFK Busy").raw_args == "Busy"
    assert parse(". mute 2h").name == "mute"
    assert parse(".  mute") is None
    assert parse("...") is None and parse(".5") is None and parse("hello .afk") is None
    assert parse(".com/path") is None
    assert parse('.meme "top text" bottom').args == ["top text", "bottom"]
    assert parse("!afk", "!").name == "afk"
    assert parse("/help@ChatHelperBot topic").name == "help"
    assert parse(".дуэль").name == "дуэль"


def test_registry_aliases(env=None):
    from chat_helper.commands.registry import registry
    from chat_helper.app import load_modules
    load_modules()
    assert registry.resolve("дуэль").id == "duel"
    assert registry.resolve("рулетка").id == "revo"
    assert registry.resolve("реверс").id == "reverse"
    assert registry.resolve("GPT").id == "ai" and registry.resolve("ai").id == "ai"   # v3: .ai is the main command, .gpt an alias
    assert registry.resolve("r").id == "r" and registry.resolve("mad").id == "mad" and registry.resolve("re").id == "re"
    assert len(registry) >= 130
    for spec in registry.commands.values():
        assert spec.handler is not None and spec.ru and spec.uz and spec.syntax_for("ru") and spec.examples_for("uz"), spec.id


async def connect(env, conn_id="bc1", owner=OWNER, **rights):
    bc = business_connection(conn_id, owner, **rights)
    env.session.connections[conn_id] = bc
    await env.feed(update_connection(bc))


async def test_unknown_command_silent_in_chat_but_helpful_in_dm(env):
    await connect(env)
    env.session.clear()
    await env.feed(update_business_message(biz_message("bc1", CONTACT, OWNER, ".net is great", first_name="Owner")))
    assert not env.session.calls("EditMessageText") and not env.session.calls("SendMessage")
    await env.feed(private_message(OWNER, ".afkk"))
    texts = env.session.sent_texts()
    assert any("Неизвестная команда" in t and "afk" in t for t in texts)


async def test_custom_prefix(env):
    await connect(env)
    await env.app.settings.set(OWNER, "prefix", "!")
    env.session.clear()
    await env.feed(update_business_message(biz_message("bc1", CONTACT, OWNER, "!calc 3*3", first_name="Owner")))
    assert "9" in env.session.calls("EditMessageText")[0].text
    env.session.clear()
    await env.feed(update_business_message(biz_message("bc1", CONTACT, OWNER, ".calc 3*3", first_name="Owner")))
    assert not env.session.calls("EditMessageText")


async def test_wrong_arguments_show_usage_privately(env):
    await connect(env)
    env.session.clear()
    await env.feed(update_business_message(biz_message("bc1", CONTACT, OWNER, ".repeat lots", first_name="Owner")))
    dm = [r for r in env.session.calls("SendMessage") if r.chat_id == OWNER]
    assert dm and "Использование" in dm[0].text


async def test_rate_limit(env):
    await connect(env)
    res = []
    for _ in range(35):
        ok, _r = env.app.limiter.check(f"cmd:{OWNER}:uuid", 30, 60)
        res.append(ok)
    assert res.count(True) == 30


async def test_admin_only_command_denied_for_regular_user(env):
    await connect(env, "bc2", USER2)
    env.session.clear()
    await env.feed(private_message(USER2, ".logs", "Bob"))
    texts = env.session.sent_texts()
    # admin-only commands do not exist for others: the reply is the regular "unknown command" one
    assert any("Неизвестная команда" in t for t in texts) and not any("Недостаточно прав" in t for t in texts)


async def test_disabled_command(env):
    await env.app.users.ensure(OWNER)
    await env.app.settings.set(OWNER, "disabled_commands", ["uuid"])
    await env.feed(private_message(OWNER, ".uuid"))
    assert any("отключили" in t for t in env.session.sent_texts())


async def test_plan_gating(env):
    await connect(env, "bc2", USER2)
    env.session.clear()
    await env.app.executor.set_global("uuid", min_plan="pro")
    await env.feed(private_message(USER2, ".uuid", "Bob"))
    assert any("тарифе PRO" in t for t in env.session.sent_texts())
    env.session.clear()
    await env.feed(private_message(OWNER, ".uuid"))  # super admin bypasses plan gates
    assert any("<code>" in t for t in env.session.sent_texts())


async def test_restricted_user(env):
    await connect(env, "bc2", USER2)
    await env.app.users.restrict(USER2, "spam")
    await env.feed(private_message(USER2, ".calc 1+1", "Bob"))
    assert any("ограничен" in t for t in env.session.sent_texts())


async def test_sandbox_runs_safe_commands_without_sending(env):
    s = await env.app.settings.all(OWNER)
    out = await env.app.executor.sandbox(OWNER, ".calc 2^8", s)
    assert out["ok"] and "256" in out["outputs"][0]["text"]
    assert not env.session.calls("SendMessage") and not env.session.calls("EditMessageText")
    out = await env.app.executor.sandbox(OWNER, ".reverse", s)
    assert out["error"] == "not_sandbox_safe"
    out = await env.app.executor.sandbox(OWNER, ".nope", s)
    assert out["error"] == "unknown_command"


@pytest.mark.parametrize("text,needle", [
    (".base64 hello", "aGVsbG8="), (".unbase64 aGVsbG8=", "hello"), (".hex hi", "6869"), (".binary hi", "01101000"),
    (".upper abc", "ABC"), (".lower ABC", "abc"), (".title hello world", "Hello World"), (".reverse_text abc", "cba"),
    (".leet hacker", "h4ck3r"), (".hash md5 hello", "5d41402abc4b2a76b9719d911017c592"), (".urlencode a b", "a%20b"),
    (".urldecode a%20b", "a b"), (".json {\"a\":1}", "&quot;a&quot;" if False else "\"a\": 1"), (".count раз два три", "3"),
    (".calc 1000 - 15%", "850"), (".repeat 2 ok", "ok ok"), (".bubble ab", "ⓐⓑ"), (".format b hi", "<b>hi</b>"),
    (".rd 5 5", "5"), (".timestamp 1700000000", "2023"), (".fix ghbdtn", "привет"), (".random color", "#"),
])
async def test_text_tools_sandbox(env, text, needle):
    s = await env.app.settings.all(OWNER)
    out = await env.app.executor.sandbox(OWNER, text, s)
    assert out["ok"], out
    assert needle in out["outputs"][-1]["text"], out


def test_calculator_security():
    assert evaluate("2+2*2") == 6
    assert evaluate("(2+3)!") == 120
    for bad in ["__import__('os')", "9^9^9", "1/0", "a" * 400, "((((((((((((((((((((((((((((((((((((((((((((((((((((((((((((((1"]:
        with pytest.raises(CalcError):
            evaluate(bad)


def test_fix_engine():
    assert fix_text("ghbdtn rfr ltkf").text == "привет как дела"
    assert fix_text("пРИВЕТ").text == "Привет"
    r = fix_text("helo")
    assert r.text == "helo" and r.ambiguous  # ambiguous → unchanged without confirmation


async def test_help_and_status_in_dm(env):
    await env.feed(private_message(OWNER, ".help"))
    assert any("команды" in t.lower() for t in env.session.sent_texts())
    env.session.clear()
    await env.feed(private_message(OWNER, ".help speed"))
    assert any(".speed" in t for t in env.session.sent_texts())


async def test_autoreply_rules_and_modes(env):
    await connect(env)
    await env.feed(update_business_message(biz_message("bc1", CONTACT, OWNER, ".reply add цена | Прайс: 100$", first_name="Owner")))
    rules = await env.app.autoreply.rules(OWNER)
    assert rules and rules[0]["pattern"] == "цена"
    await env.app.autoreply.set_mode(OWNER, "auto")
    env.app.loop_guard.reset(OWNER, CONTACT)
    await env.app.chats.set_owner_pause(OWNER, CONTACT, 0)
    env.session.clear()
    conn = await env.app.connections.get("bc1")
    out = await env.app.pipeline.on_message(conn, biz_message("bc1", CONTACT, CONTACT, "Какая цена?"))
    assert out == "rule_reply"
    assert any("Прайс" in r.text for r in env.session.calls("SendMessage"))


async def test_silent_and_manual_modes(env):
    await connect(env)
    conn = await env.app.connections.get("bc1")
    out = await env.app.pipeline.on_message(conn, biz_message("bc1", CONTACT, CONTACT, "hi"))
    assert out == "manual_mode"
    await env.app.autoreply.set_mode(OWNER, "silent")
    await env.app.afk.enable(OWNER, "x")  # AFK switches mode to afk
    await env.app.autoreply.set_mode(OWNER, "silent")
    assert await env.app.afk.active(OWNER) is None
    out = await env.app.pipeline.on_message(conn, biz_message("bc1", CONTACT, CONTACT, "hi again"))
    assert out == "manual_mode" or out.startswith("blocked:")


async def test_ignore_list(env):
    await connect(env)
    await env.app.afk.enable(OWNER, "x")
    await env.feed(update_business_message(biz_message("bc1", CONTACT, OWNER, ".ignore", first_name="Owner")))
    await env.app.afk.enable(OWNER, "x")
    conn = await env.app.connections.get("bc1")
    out = await env.app.pipeline.on_message(conn, biz_message("bc1", CONTACT, CONTACT, "hi"))
    assert out == "blocked:ignored"


async def test_afk_commands(env):
    await connect(env)
    await env.feed(update_business_message(biz_message("bc1", CONTACT, OWNER, ".afk 2h Встреча", first_name="Owner")))
    sess = await env.app.afk.active(OWNER)
    assert sess and sess["reason"] == "Встреча" and sess["ends_at"]
    assert (await env.app.settings.all(OWNER))["mode"] == "afk"
    env.session.clear()
    await env.feed(update_business_message(biz_message("bc1", CONTACT, OWNER, ".afk status", first_name="Owner")))
    assert any("AFK включён" in t for t in env.session.sent_texts())
    await env.feed(update_business_message(biz_message("bc1", CONTACT, OWNER, ".unafk", first_name="Owner")))
    assert await env.app.afk.active(OWNER) is None
    assert (await env.app.settings.all(OWNER))["mode"] == "manual"


async def test_afk_timer_expiry(env):
    await env.app.users.ensure(OWNER)
    await env.app.afk.enable(OWNER, "x", duration=60)
    await env.app.db.execute("UPDATE afk_sessions SET ends_at=1")
    env.app.afk._active_cache.clear()
    assert await env.app.afk.expire_due() == 1
    assert await env.app.afk.active(OWNER) is None
