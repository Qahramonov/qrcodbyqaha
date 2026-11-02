"""Localization Manager (v3): catalogs are complete and consistent, every key used by the code exists, and the bot
really speaks Uzbek — every panel screen, Super Admin section and the main commands render without Russian text."""
from __future__ import annotations

import ast
import re
import string
from pathlib import Path

import pytest
from conftest import CONTACT, OWNER, USER2
from fakes import biz_message, business_connection, private_message, update_business_message, update_connection

import chat_helper
from chat_helper.localization import DEFAULT_LANG, LANGS, catalog, has, load, placeholders, tr

PKG = Path(chat_helper.__file__).resolve().parent
CYR = re.compile(r"[А-Яа-яЁё]")
KEY_RE = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z0-9_]+)+$")
# Uzbek texts that legitimately contain Cyrillic: the keyboard-layout fixer shows its Russian example (ghbdtn → привет).
UZ_CYRILLIC_ALLOWED = {"cmd.fix.desc"}
# Language names are shown in their own language on the language picker; the keyboard-layout fixer's example
# converts a Latin-typed word into Russian.
OWN_NAME_ALLOWED = ("🇷🇺 Русский", "ghbdtn → привет")


def ns_set() -> set[str]:
    return {k.split(".")[0] for k in catalog(DEFAULT_LANG)}


# ---- catalogs ---------------------------------------------------------------------------------------------------
def test_shipped_languages_have_catalogs():
    cats = load(force=True)
    assert set(LANGS) <= set(cats), "ru.json and uz.json must exist"
    assert len(catalog("ru")) > 1000


@pytest.mark.parametrize("lang", [x for x in LANGS if x != DEFAULT_LANG])
def test_catalog_has_exactly_the_reference_keys(lang):
    ref, cat = set(catalog(DEFAULT_LANG)), set(catalog(lang))
    assert not sorted(ref - cat), f"missing in {lang}.json"
    assert not sorted(cat - ref), f"keys only in {lang}.json"


@pytest.mark.parametrize("lang", LANGS)
def test_values_are_valid_format_strings_and_not_empty(lang):
    for key, text in catalog(lang).items():
        assert isinstance(text, str) and text.strip(), (lang, key)
        list(string.Formatter().parse(text))     # raises on unbalanced braces


@pytest.mark.parametrize("lang", [x for x in LANGS if x != DEFAULT_LANG])
def test_placeholders_match_reference(lang):
    ref = catalog(DEFAULT_LANG)
    bad = {k: (placeholders(ref[k]), placeholders(v)) for k, v in catalog(lang).items() if placeholders(ref[k]) != placeholders(v)}
    assert not bad


def test_uzbek_catalog_contains_no_cyrillic():
    bad = {k: v for k, v in catalog("uz").items() if CYR.search(v) and k not in UZ_CYRILLIC_ALLOWED}
    assert not bad


def test_tr_fallbacks_and_formatting():
    assert tr("uz", "common.on") != tr("ru", "common.on")
    assert tr("xx", "common.on") == tr("ru", "common.on")            # unknown language → reference catalog
    assert tr("uz", "no.such.key") == "no.such.key"                   # unknown key → the key itself (visible in tests)
    assert tr("ru", "time.day.one", n=1) == "1 день"
    assert tr("ru", "time.day.one", wrong=1) == tr("ru", "time.day.one")   # bad kwargs never raise
    assert tr(None, "common.on") == tr("ru", "common.on")


# ---- keys used by the code ------------------------------------------------------------------------------------
def _call_name(node: ast.Call) -> str:
    f = node.func
    return f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else ""


def _keys_in_code() -> dict[str, list[str]]:
    """String constants that are translation keys: arguments of tr()/t()/p()/notify_t() and key-shaped constants
    of a catalog namespace (excluding audit action names and f-string fragments)."""
    namespaces = ns_set()
    found: dict[str, list[str]] = {}
    for path in sorted(PKG.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        skip: set[int] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.JoinedStr):
                skip.update(id(v) for v in node.values)
            if isinstance(node, ast.Call) and _call_name(node) in ("log", "incr", "emit") and node.args:
                skip.add(id(node.args[0]))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name, args = _call_name(node), node.args
                picked: list[tuple[ast.AST, str]] = []
                if name == "tr" and len(args) >= 2:
                    picked.append((args[1], ""))
                elif name in ("t", "_t") and args:
                    picked.append((args[0], ""))
                elif name in ("p", "phrase") and len(args) >= 2:
                    picked.append((args[1], "common."))
                elif name == "notify_t":
                    picked += [(a, "") for a in args[2:4]]
                for arg, prefix in picked:
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                        found.setdefault(prefix + arg.value, []).append(f"{path.name}:{arg.lineno}")
            elif (isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in skip
                  and KEY_RE.match(node.value) and node.value.split(".")[0] in namespaces):
                found.setdefault(node.value, []).append(f"{path.name}:{node.lineno}")
    return found


AUDIT_LIKE = re.compile(r"^(delegation\.(grant|revoke|use)|media\.(cleanup|settings)|plan\.upsert)$")


def test_every_key_used_in_code_exists_in_every_language():
    used = _keys_in_code()
    assert len(used) > 800
    for lang in LANGS:
        missing = {k: v[:3] for k, v in used.items() if k not in catalog(lang) and not AUDIT_LIKE.match(k)}
        assert not missing, lang


def test_dynamic_keys_exist():
    from chat_helper.app import load_modules
    from chat_helper.automation.engine import TEMPLATES, TRIGGERS, localize
    from chat_helper.business.rights import CAPABILITIES, RIGHT_TITLES
    from chat_helper.commands.registry import CATEGORIES, registry
    from chat_helper.handlers.panel import screen_stats  # noqa: F401  (imports the panel module)
    from chat_helper.media.infographic import STEP_COUNT
    from chat_helper.modules.text_tools import BALL_ANSWERS
    from chat_helper.subscriptions.service import DEFAULT_PLANS, LIMIT_KEYS
    load_modules()
    keys = [f"cmd.{cid}.desc" for cid in registry.commands]
    keys += [k for _, k in CATEGORIES.values()] + list(RIGHT_TITLES.values()) + [c["title"] for c in CAPABILITIES.values()]
    keys += list(TRIGGERS.values()) + [p["description"] for p in DEFAULT_PLANS]
    keys += [f"text_tools.ball.{i}" for i in range(BALL_ANSWERS)]
    keys += [f"infographic.step{i}.{part}" for i in range(1, STEP_COUNT + 1) for part in ("title", "hint")]
    keys += [f"time.{u}.{f}" for u in ("day", "hour", "minute", "second") for f in ("one", "few", "many")]
    keys += [f"panel.limit.{k}" for k in ("ai_requests_day", "media_jobs_day", "autoreply_rules", "automation_rules")]
    keys += [f"panel.stat.{k}" for k in ("messages_in", "messages_out", "auto_replies", "ai_requests", "media_jobs", "commands", "games_played")]
    assert set(LIMIT_KEYS) >= {"ai_requests_day", "media_jobs_day"}
    for lang in LANGS:
        assert not [k for k in keys if k not in catalog(lang)], lang
    # automation templates: every text field is rendered (no raw keys reach the user)
    for lang in LANGS:
        rendered = repr(localize(TEMPLATES, lang))
        assert "automation.tpl." not in rendered, lang


def test_commands_have_localized_descriptions_syntax_and_examples():
    from chat_helper.app import load_modules
    from chat_helper.commands.registry import registry
    load_modules()
    for spec in registry.commands.values():
        for lang in LANGS:
            assert has(f"cmd.{spec.id}.desc", lang), spec.id
            assert spec.syntax_for(lang).startswith(".") or spec.syntax_for(lang).startswith("/"), spec.id
            assert spec.examples_for(lang), spec.id
        assert spec.describe("uz") != spec.describe("ru") or not CYR.search(spec.describe("ru")), spec.id
        assert not CYR.search(spec.syntax_for("uz") + " ".join(spec.examples_for("uz"))), spec.id


def test_handlers_contain_no_hardcoded_russian():
    """Panel/handler code holds only keys; the only Cyrillic literal allowed is the language's own name."""
    bad = []
    for path in sorted((PKG / "handlers").glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        docstrings = {id(n.body[0].value) for n in ast.walk(tree)
                      if isinstance(n, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and n.body
                      and isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, ast.Constant)}
        for node in ast.walk(tree):
            if (isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings
                    and CYR.search(node.value) and node.value not in OWN_NAME_ALLOWED):
                bad.append(f"{path.name}:{node.lineno}: {node.value[:40]}")
    assert not bad


# ---- the bot really speaks Uzbek ------------------------------------------------------------------------------
def _cyr(texts: list[str]) -> list[str]:
    out = []
    for t in texts:
        clean = t
        for allowed in OWN_NAME_ALLOWED:
            clean = clean.replace(allowed, "")
        if CYR.search(clean):
            out.append(clean[:300])
    return out


def _markup_texts(markup) -> list[str]:
    if markup is None:
        return []
    return [b.text for row in markup.inline_keyboard for b in row]


async def _connect(env, uid: int, conn_id: str):
    bc = business_connection(conn_id, uid)
    env.session.connections[conn_id] = bc
    await env.feed(update_connection(bc))


# screens that need arguments, with the arguments to render them
SCREEN_ARGS = {"chat": lambda: (CONTACT,), "help_cmd": lambda: ("afk",), "cmd": lambda: ("afk",)}


async def test_every_panel_screen_renders_in_uzbek(env):
    from chat_helper.handlers.ui import SCREENS
    await env.app.users.upsert(USER2, "bob", "Bob", None, "uz")
    await env.app.users.upsert(OWNER, "libPM", "Owner", None, "uz")
    await _connect(env, USER2, "bc_uz")
    await env.app.settings.set(USER2, "lang", "uz")
    await env.app.settings.set(OWNER, "lang", "uz")
    await env.feed(update_business_message(biz_message("bc_uz", CONTACT, CONTACT, "Salom!", first_name="Ali")))
    s = await env.app.settings.all(USER2)
    rendered, problems = 0, {}
    for name, sd in sorted(SCREENS.items()):
        uid = OWNER if sd.admin else USER2
        st = await env.app.settings.all(uid)
        args = SCREEN_ARGS.get(name, lambda: ())()
        try:
            text, markup = await sd.fn(env.app, uid, st, *args)
        except TypeError:
            continue                       # screens that need context-specific arguments are covered below
        rendered += 1
        bad = _cyr([text] + _markup_texts(markup))
        if bad:
            problems[name] = bad
    assert rendered >= 20
    assert s["lang"] == "uz"
    assert not problems


async def test_every_super_admin_section_renders_in_uzbek(env):
    from chat_helper.handlers.admin import HANDLERS, admin_menu
    await env.app.users.upsert(OWNER, "libPM", "Owner", None, "uz")
    await env.app.settings.set(OWNER, "lang", "uz")
    text, markup = await admin_menu(env.app, OWNER, await env.app.settings.all(OWNER))
    problems = {"menu": _cyr([text] + _markup_texts(markup))} if _cyr([text] + _markup_texts(markup)) else {}
    for name, fn in HANDLERS.items():
        text, rows = await fn(env.app, "uz", [])
        labels = [b[0] for row in rows for b in row if isinstance(b, tuple)]
        bad = _cyr([text] + labels)
        if bad:
            problems[name] = bad
    assert len(HANDLERS) >= 23
    assert not problems


UZ_COMMANDS = [".help", ".calc 2+2*2", ".afk Tushlik", ".unafk", ".ball Bugun kinoga borsammi?", ".morse SOS", ".r Salom",
               ".upper salom", ".online", ".status", ".ping", ".settings", ".mute", ".protect", ".unprotect", ".nogif",
               ".re test", ".a Salom", ".sum 10", ".remind 30m test", ".qr https://example.com", ".geo 41.3111, 69.2797",
               ".info", ".time Asia/Tashkent", ".coin", ".dice", ".password 12", ".unknowncmd"]


async def test_main_commands_answer_in_uzbek(env):
    await env.app.users.upsert(OWNER, "libPM", "Owner", None, "uz")
    await _connect(env, OWNER, "bc_o")
    await env.app.settings.set(OWNER, "lang", "uz")
    problems = {}
    for cmd in UZ_COMMANDS:
        env.session.clear()
        await env.feed(update_business_message(biz_message("bc_o", CONTACT, OWNER, cmd, first_name="Owner")))
        texts = env.session.sent_texts()
        texts += [getattr(r, "caption", None) or "" for r in env.session.requests if getattr(r, "caption", None)]
        for r in env.session.requests:
            texts += _markup_texts(getattr(r, "reply_markup", None) if hasattr(getattr(r, "reply_markup", None), "inline_keyboard") else None)
        bad = _cyr(texts)
        if bad:
            problems[cmd] = bad
    # the panel (/start) and DM commands in Uzbek as well
    for text in ("/start", "/help", ".help afk", ".afkk"):
        env.session.clear()
        await env.feed(private_message(OWNER, text))
        bad = _cyr(env.session.sent_texts())
        if bad:
            problems[text] = bad
    assert not problems


async def test_locked_user_sees_uzbek_onboarding(env):
    await env.app.users.upsert(USER2, "bob", "Bob", None, "uz")
    await env.app.settings.set(USER2, "lang", "uz")
    for text in ("/start", ".ai salom", "/connect", "/help"):
        env.session.clear()
        await env.feed(private_message(USER2, text, "Bob"))
        reqs = env.session.requests
        texts = env.session.sent_texts() + [getattr(r, "caption", "") or "" for r in reqs]
        for r in reqs:
            mk = getattr(r, "reply_markup", None)
            if hasattr(mk, "inline_keyboard"):
                texts += _markup_texts(mk)
        assert texts, text
        assert not _cyr(texts), (text, _cyr(texts))
