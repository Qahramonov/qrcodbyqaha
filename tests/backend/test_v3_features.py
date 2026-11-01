"""v3 features: Animation Engine, .r RTL, .ball, .morse, .re, .mad, reminders, .info, .geo, QR decode, OCR, GIF, video watermark, AI Twin."""
from __future__ import annotations

import asyncio
import io
import os
import random
import shutil
import time

import pytest
from aiogram.exceptions import TelegramRetryAfter
from aiogram.types import PhotoSize
from conftest import CONTACT, OWNER
from fakes import biz_message, business_connection, private_message, update_business_message, update_connection
from test_v3_controls import card_buttons, deletes, press

from chat_helper.modules import animations as A
from chat_helper.utils.unicode import graphemes

needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


async def connect(env, uid=OWNER, conn_id="bc1", **rights):
    bc = business_connection(conn_id, uid, **rights)
    env.session.connections[conn_id] = bc
    await env.feed(update_connection(bc))


async def say(env, sender, text=None, chat=CONTACT, conn_id="bc1", **extra):
    m = biz_message(conn_id, chat, sender, text, **extra)
    await env.feed(update_business_message(m))
    return m


@pytest.fixture
def fast_anim(monkeypatch):
    monkeypatch.setattr(A, "SPEEDS", {k: (0.0, v[1]) for k, v in A.SPEEDS.items()})


# ---- animation engine ---------------------------------------------------------------------------------------------------
def test_all_animation_types_end_with_clean_text_and_respect_budget():
    from chat_helper.services.settings import ANIM_TYPES
    text = "Привет 👨‍👩‍👧 <мир>"
    for kind in ANIM_TYPES:
        frames = A.frames_for(kind, text, 12, rng=random.Random(1), custom=["1", "2", text])
        assert frames[-1] == "Привет 👨‍👩‍👧 &lt;мир&gt;", kind                     # final clean (HTML-escaped) text
        assert len(frames) <= 13, (kind, len(frames))
        assert all(a != b for a, b in zip(frames, frames[1:])), kind                    # no identical consecutive edits
        assert all("<мир>" not in f for f in frames), kind                              # user text is always escaped


def test_typewriter_never_splits_emoji_sequences():
    text = "Hi 👨‍👩‍👧🇺🇿!"
    allowed = {"".join(graphemes(text)[:i]) for i in range(len(graphemes(text)) + 1)}
    for f in A.frames_for("typewriter", text, 12)[:-1]:
        assert f.rstrip("▌") in allowed


def test_parse_animation_args():
    d = {"anim_type": "typewriter", "anim_speed": "fast"}
    assert A.parse_args("glitch turbo Ура", d)[:3] == ("glitch", "turbo", "Ура")
    assert A.parse_args("fast Привет", d)[:3] == ("fast", "fast", "Привет")      # «fast» = Fast Typewriter type
    kind, _, text, frames = A.parse_args("custom 🌑 | 🌓 | 🌕 Луна", d)
    assert kind == "custom" and frames == ["🌑", "🌓", "🌕 Луна"] and text == "🌕 Луна"


async def test_animation_edits_command_in_place_and_finishes(env, fast_anim):
    await connect(env)
    env.session.clear()
    cmd = await say(env, OWNER, ".a progress Загрузка")
    for _ in range(50):
        await asyncio.sleep(0.02)
        if not A._active:
            break
    edits = [r for r in env.session.calls("EditMessageText") if r.message_id == cmd.message_id]
    assert len(edits) >= 5 and edits[-1].text == "Загрузка" and edits[-1].business_connection_id == "bc1"
    assert "▰" in edits[-2].text
    job = await env.app.db.fetchone("SELECT * FROM animation_jobs WHERE owner_id=?", (OWNER,))
    assert job["status"] == "done" and job["kind"] == "progress"


async def test_animation_stops_on_flood_wait_and_keeps_final_text(env, fast_anim):
    await connect(env)
    await say(env, OWNER, ".r warmup")                        # plain edit to have the chat known
    exc = TelegramRetryAfter(method=None, message="Flood control exceeded", retry_after=12)
    exc._once = True
    env.session.clear()
    env.session.fail["EditMessageText"] = exc
    cmd = await say(env, OWNER, ".a typewriter Длинный текст для проверки лимитов")
    for _ in range(50):
        await asyncio.sleep(0.02)
        if not A._active:
            break
    edits = [r for r in env.session.calls("EditMessageText") if r.message_id == cmd.message_id]
    assert edits[-1].text == "Длинный текст для проверки лимитов" and len(edits) == 2   # failed frame + final, no retry storm
    job = await env.app.db.fetchone("SELECT status FROM animation_jobs WHERE owner_id=? ORDER BY id DESC", (OWNER,))
    assert job["status"] == "rate_limited"


async def test_animation_cancel(env, monkeypatch):
    monkeypatch.setattr(A, "SPEEDS", {k: (0.2, v[1]) for k, v in A.SPEEDS.items()})
    await connect(env)
    cmd = await say(env, OWNER, ".a glitch Секретное сообщение")
    await asyncio.sleep(0.05)
    await say(env, OWNER, ".a stop")
    await asyncio.sleep(0.1)
    edits = [r for r in env.session.calls("EditMessageText") if r.message_id == cmd.message_id]
    assert edits[-1].text == "Секретное сообщение"
    job = await env.app.db.fetchone("SELECT status FROM animation_jobs WHERE owner_id=? ORDER BY id DESC", (OWNER,))
    assert job["status"] == "cancelled"


# ---- text effects ------------------------------------------------------------------------------------------------------------
async def test_rtl_ball_morse(env):
    await connect(env)
    env.session.clear()
    await say(env, OWNER, ".r Привет 👋🏽")
    assert env.session.sent_texts()[-1] == "👋🏽 тевирП"
    await say(env, OWNER, ".ball Получится?")
    assert "🎱" in env.session.sent_texts()[-1]
    await say(env, OWNER, ".morse SOS")
    assert "... --- ..." in env.session.sent_texts()[-1]
    await say(env, OWNER, ".morse ... --- ...")
    assert env.session.sent_texts()[-1].endswith("SOS")
    await say(env, OWNER, ".morse ru .--. .-. .. .-- . -")
    assert env.session.sent_texts()[-1].endswith("ПРИВЕТ")


# ---- .re / .mad -----------------------------------------------------------------------------------------------------------------
async def test_repeat_sends_deletes_and_stops_by_owner_button(env, monkeypatch):
    from chat_helper.modules import repeat as R
    monkeypatch.setattr(R, "INTERVAL", 0.05)
    monkeypatch.setattr(R, "MAX_DURATION", 3)
    await connect(env)
    env.session.clear()
    await say(env, OWNER, ".re Ты где? 👀")
    await asyncio.sleep(0.25)
    sends = [r for r in env.session.calls("SendMessage") if r.chat_id == CONTACT and r.text == "Ты где? 👀"]
    assert len(sends) >= 3 and all(r.business_connection_id == "bc1" for r in sends)
    assert len(deletes(env)) >= 2                                     # previous copy removed before each resend
    card = (await env.app.controls.cards(OWNER, CONTACT, "re"))[0]
    stop = card_buttons(sends[-1])["⏹ Остановить"]
    await env.feed(press(CONTACT, stop))                               # the counterpart cannot stop it
    assert "только владелец" in env.session.calls("AnswerCallbackQuery")[-1].text
    await env.feed(press(OWNER, stop))
    await asyncio.sleep(0.1)
    job = await env.app.db.fetchone("SELECT * FROM repetition_jobs WHERE owner_id=?", (OWNER,))
    assert job["status"] == "cancelled" and job["sends"] >= 3
    assert (await env.app.controls.card(card["token"]))["status"] == "closed"


async def test_repeat_free_plan_limit(env, monkeypatch):
    from chat_helper.modules import repeat as R
    from conftest import USER2
    monkeypatch.setattr(R, "MAX_DURATION", 0)
    await connect(env, USER2, "bc2")
    for i in range(3):
        await env.app.db.execute("INSERT INTO repetition_jobs(owner_id, connection_id, chat_id, text, interval_sec, ends_at, status, created_at) "
                                 "VALUES (?,?,?,?,?,?,?,?)", (USER2, "bc2", CONTACT, "x", 5, 0, "done", int(time.time())))
    env.session.clear()
    await say(env, USER2, ".re ещё раз", conn_id="bc2")
    assert any("Free" in t for t in env.session.sent_texts())


async def test_mad_sends_chat_actions_and_stops(env, monkeypatch):
    await connect(env)
    env.session.clear()
    await say(env, OWNER, ".mad 5 voice photo")
    await asyncio.sleep(0.05)
    acts = env.session.calls("SendChatAction")
    assert acts and acts[0].action == "record_voice" and acts[0].business_connection_id == "bc1"
    await say(env, OWNER, ".mad stop")
    from chat_helper.modules.system_cmds import _ACTIVE_MAD
    await asyncio.sleep(0.05)
    assert (OWNER, CONTACT) not in _ACTIVE_MAD


# ---- reminders -------------------------------------------------------------------------------------------------------------------
async def test_dm_and_chat_reminders(env):
    await connect(env)
    await say(env, OWNER, ".remind 10m позвонить маме")
    await say(env, OWNER, ".remindf 1h Не забудь документы!")
    rows = await env.app.reminders.list(OWNER)
    assert {r["kind"] for r in rows} == {"dm", "chat"}
    await env.app.db.execute("UPDATE scheduled_tasks SET run_at=? WHERE user_id=?", (int(time.time()) - 1, OWNER))
    env.session.clear()
    await env.app.scheduler.run_due()
    texts = [(r.chat_id, r.text, r.business_connection_id) for r in env.session.calls("SendMessage")]
    assert (OWNER, "⏰ позвонить маме", None) in texts
    assert (CONTACT, "⏰ Не забудь документы!", "bc1") in texts
    assert {r["status"] for r in await env.app.reminders.list(OWNER, None)} == {"done"}


async def test_chat_reminder_falls_back_to_dm(env):
    from aiogram.exceptions import TelegramBadRequest
    await connect(env)
    await say(env, OWNER, ".remindf 1h Встреча в 18:00")
    await env.app.db.execute("UPDATE scheduled_tasks SET run_at=? WHERE user_id=?", (int(time.time()) - 1, OWNER))
    exc = TelegramBadRequest(method=None, message="Bad Request: BUSINESS_PEER_USAGE_MISSING")
    exc._once = True
    env.session.fail["SendMessage"] = exc
    env.session.clear()
    await env.app.scheduler.run_due()
    dm = [r for r in env.session.calls("SendMessage") if r.chat_id == OWNER][-1]
    assert "не отправлено" in dm.text and "Встреча в 18:00" in dm.text
    assert (await env.app.reminders.list(OWNER, None))[0]["status"] == "failed"


# ---- info / geo / qr / ocr ---------------------------------------------------------------------------------------------------------
async def test_info_and_geo(env):
    await connect(env)
    env.session.clear()
    await say(env, OWNER, ".info")
    info = [r for r in env.session.calls("SendMessage") if r.chat_id == OWNER] + env.session.calls("SendPhoto")
    body = (getattr(info[-1], "text", None) or info[-1].caption)
    assert str(CONTACT) in body and "Дата регистрации" in body
    env.session.clear()
    await say(env, OWNER, ".geo 41.3111, 69.2797")
    loc = env.session.calls("SendLocation")[-1]
    assert (loc.latitude, loc.longitude, loc.business_connection_id) == (41.3111, 69.2797, "bc1")
    await say(env, OWNER, ".geo 41.311, 69.279; 39.654, 66.975")
    assert "km" in env.session.sent_texts()[-1] and "openstreetmap" in env.session.sent_texts()[-1]
    from chat_helper.modules.extra_cmds import haversine_km
    assert 260 < haversine_km((41.311, 69.279), (39.654, 66.975)) < 270


async def test_qr_decode_from_photo(env):
    pytest.importorskip("zxingcpp")
    import segno
    await connect(env)
    buf = io.BytesIO()
    segno.make("https://t.me/ChatHelperTestBot", error="m").save(buf, kind="png", scale=8, border=4)
    env.session.files["qr1"] = buf.getvalue()
    photo = await say(env, CONTACT, None, photo=[PhotoSize(file_id="qr1", file_unique_id="qr1u", width=300, height=300, file_size=len(buf.getvalue()))])
    env.session.clear()
    await say(env, OWNER, ".qr", reply_to=photo)
    assert any("https://t.me/ChatHelperTestBot" in t and "zxing-cpp" in t for t in env.session.sent_texts())


async def test_ocr_uses_tesseract_engine(env, tmp_path, monkeypatch):
    # a stand-in for the tesseract CLI (the real engine is installed on the phone: pkg install tesseract)
    stub = tmp_path / "tesseract"
    stub.write_text('#!/bin/sh\nif [ "$1" = "--list-langs" ]; then printf "List of available languages:\\neng\\nrus\\n"; '
                    'else printf "Привет из OCR\\nHello"; fi\n')
    stub.chmod(0o755)
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ['PATH']}")
    from PIL import Image
    b = io.BytesIO()
    Image.new("RGB", (40, 20), "white").save(b, "JPEG")
    env.session.files["ph1"] = b.getvalue()
    await connect(env)
    photo = await say(env, CONTACT, None, photo=[PhotoSize(file_id="ph1", file_unique_id="ph1u", width=40, height=20, file_size=len(b.getvalue()))])
    env.session.clear()
    await say(env, OWNER, ".ptext", reply_to=photo)
    out = env.session.sent_texts()[-1]
    assert "Привет из OCR" in out and "tesseract (rus+eng)" in out


async def test_ocr_without_engine_explains(env, monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda name: None)
    from PIL import Image
    b = io.BytesIO()
    Image.new("RGB", (40, 20), "white").save(b, "JPEG")
    env.session.files["ph2"] = b.getvalue()
    await connect(env)
    photo = await say(env, CONTACT, None, photo=[PhotoSize(file_id="ph2", file_unique_id="ph2u", width=40, height=20, file_size=len(b.getvalue()))])
    env.session.clear()
    await say(env, OWNER, ".ptext", reply_to=photo)
    assert any("pkg install tesseract" in t for t in env.session.sent_texts())


# ---- media ---------------------------------------------------------------------------------------------------------------------------
async def test_gif_from_photo_is_animated(tmp_path):
    from PIL import Image

    from chat_helper.media import image as I
    out = I.zoom_gif(I.demo_image((320, 240)), tmp_path / "a.gif")
    im = Image.open(out)
    assert im.format == "GIF" and im.n_frames >= 20 and im.size[0] <= 480


@needs_ffmpeg
async def test_video_watermark_keeps_circle(tmp_path):
    from chat_helper.media import image as I
    from chat_helper.media.av import AV
    from chat_helper.media.ffmpeg import FFmpeg
    av = AV(FFmpeg(timeout=60))
    src = await av.make_test_media(tmp_path, "video")
    info = await av.ff.probe(src)
    layer = tmp_path / "wm.png"
    I.watermark_layer((info["width"], info["height"]), "© Chat helper", "br").save(layer)
    out, kind, extra = await av.watermark(src, "video", tmp_path, layer)
    assert kind == "video" and out.exists()
    out2, kind2, extra2 = await av.watermark(src, "video_note", tmp_path, layer)
    p2 = await av.ff.probe(out2)
    assert kind2 == "video_note" and p2["width"] == p2["height"] == 384


# ---- AI twin -------------------------------------------------------------------------------------------------------------------------
async def test_twin_profile_and_prompt():
    from chat_helper.ai.twin import DEFAULTS, twin_system
    p = dict(DEFAULTS, mode="auto", name="Kamron AI", formality=90, humor=0, emoji=0, persona="male",
             examples=["Ок, гляну вечером", "Скинь в личку"], custom_prompt="Не обещай встречи")
    sys = twin_system(p, "Kamron", "ru")
    assert "AI twin of Kamron" in sys and "Kamron AI" in sys and "formal" in sys and "Ок, гляну вечером" in sys
    assert "Never use profanity" in sys and "AI assistant" in sys and "Не обещай встречи" in sys


async def test_twin_modes_drive_auto_reply(env):
    env.app.ai.enable_test_provider()
    await connect(env)
    await env.app.autoreply.set_mode(OWNER, "ai")
    await env.app.settings.set(OWNER, "ai_debounce_sec", 0)
    captured = {}
    real = env.app.ai.complete

    async def spy(uid, msgs, **kw):
        captured["system"] = kw.get("system", "")
        return await real(uid, msgs, **kw)
    env.app.ai.complete = spy
    await env.app.twin.update(OWNER, mode="draft", name="Двойник")
    with pytest.raises(ValueError):
        await env.app.twin.update(OWNER, mode="evil")
    conn = await env.app.connections.get("bc1")
    env.session.clear()
    await env.app.pipeline.on_message(conn, biz_message("bc1", CONTACT, CONTACT, "Привет, ты где?"))
    await asyncio.sleep(0.3)
    assert "AI twin" in captured["system"] and "Двойник" in captured["system"]
    assert not [r for r in env.session.calls("SendMessage") if r.chat_id == CONTACT]   # draft only → nothing sent
    draft = await env.app.db.fetchone("SELECT * FROM ai_drafts WHERE user_id=? ORDER BY id DESC", (OWNER,))
    assert draft["status"] == "suggested"
    dm = [r for r in env.session.calls("SendMessage") if r.chat_id == OWNER][-1]
    assert dm.reply_markup is None                                                    # no «Send» button in Draft mode
    await env.app.twin.update(OWNER, mode="auto")
    env.session.clear()
    await env.app.pipeline.on_message(conn, biz_message("bc1", CONTACT, CONTACT, "Ответь мне"))
    await asyncio.sleep(0.3)
    sent = [r for r in env.session.calls("SendMessage") if r.chat_id == CONTACT]
    assert sent and "AI" in sent[-1].text                                             # auto replies are always labelled
    await env.app.twin.update(OWNER, active_from="00:00", active_to="00:01")
    assert not env.app.twin.is_active_now(await env.app.twin.get(OWNER), "UTC") or time.gmtime().tm_hour == 0


async def test_twin_learn_only_own_messages(env):
    await connect(env)
    theirs = await say(env, CONTACT, "чужое сообщение")
    mine = await say(env, OWNER, "Моё сообщение, коротко и по делу")
    env.session.clear()
    await say(env, OWNER, ".twin learn", reply_to=theirs)
    assert any("только ВАШИ" in t for t in env.session.sent_texts())
    await say(env, OWNER, ".twin learn", reply_to=mine)
    p = await env.app.twin.get(OWNER)
    assert p["examples"] == ["Моё сообщение, коротко и по делу"] and p["consent_at"]
    await env.feed(private_message(OWNER, "/start"))
    from test_panel import cb
    env.session.clear()
    await env.feed(cb(OWNER, "m:twin"))
    assert any("AI-двойник" in t for t in env.session.sent_texts())
    await env.feed(cb(OWNER, "tw:mode:manual"))
    assert (await env.app.twin.get(OWNER))["mode"] == "manual"
    await env.feed(cb(OWNER, "tw:clear"))
    assert (await env.app.twin.get(OWNER))["examples"] == []

