"""v3 gaps closed by dedicated tests: pre-migration backup, .finfo, .wtm on a photo, .quiet, localized admin notifications."""
from __future__ import annotations

import asyncio
import io
from pathlib import Path

from aiogram.types import PhotoSize
from conftest import CONTACT, OWNER
from fakes import biz_message, business_connection, update_business_message, update_connection

from chat_helper.database import migrations as M
from chat_helper.database.db import Database


async def connect(env, uid=OWNER, conn_id="bc1"):
    bc = business_connection(conn_id, uid)
    env.session.connections[conn_id] = bc
    await env.feed(update_connection(bc))


async def photo_message(env, file_id: str, size=(64, 32)):
    from PIL import Image
    b = io.BytesIO()
    Image.new("RGB", size, "red").save(b, "PNG")
    env.session.files[file_id] = b.getvalue()
    m = biz_message("bc1", CONTACT, CONTACT, None,
                    photo=[PhotoSize(file_id=file_id, file_unique_id=file_id + "u", width=size[0], height=size[1], file_size=len(b.getvalue()))])
    await env.feed(update_business_message(m))
    return m


# ---- migration ----------------------------------------------------------------------------------------------------
async def test_existing_v1_database_is_backed_up_before_m003(tmp_path: Path, monkeypatch):
    db = Database(tmp_path / "chat_helper.db")
    await db.connect()
    try:
        monkeypatch.setattr(M, "MIGRATIONS", M.MIGRATIONS[:2])          # a v1 install: schema v2
        assert await M.apply_migrations(db) == [1, 2]
        await db.execute("INSERT INTO users(id, first_name, created_at, last_seen_at) VALUES (?,?,?,?)", (OWNER, "Owner", 1, 1))
        monkeypatch.undo()
        backups = tmp_path / "backups"
        assert await M.apply_migrations(db, backups) == [3]
        files = list(backups.glob("chat_helper_*_pre_migration_v3.db"))
        assert len(files) == 1
        old = Database(files[0])
        await old.connect()
        try:
            assert await old.fetchval("SELECT COUNT(*) FROM sqlite_master WHERE name='mute_rules'") == 0
            assert await old.fetchval("SELECT COUNT(*) FROM users") == 1          # the data is in the backup
        finally:
            await old.close()
        assert await db.fetchval("SELECT COUNT(*) FROM sqlite_master WHERE name='mute_rules'") == 1
        assert await db.fetchval("SELECT first_name FROM users WHERE id=?", (OWNER,)) == "Owner"   # data kept
    finally:
        await db.close()


async def test_fresh_install_needs_no_backup(tmp_path: Path):
    db = Database(tmp_path / "new.db")
    await db.connect()
    try:
        assert await M.apply_migrations(db, tmp_path / "backups") == [v for v, _, _ in M.MIGRATIONS]
        assert not (tmp_path / "backups").exists() or not list((tmp_path / "backups").iterdir())
    finally:
        await db.close()


# ---- media commands ---------------------------------------------------------------------------------------------
async def test_finfo_reports_photo_details(env):
    await connect(env)
    photo = await photo_message(env, "fi1", (64, 32))
    env.session.clear()
    await env.feed(update_business_message(biz_message("bc1", CONTACT, OWNER, ".finfo", reply_to=photo, first_name="Owner")))
    out = "\n".join(env.session.sent_texts())
    assert "64×32" in out and "photo" in out


async def test_wtm_watermarks_a_photo(env):
    await connect(env)
    photo = await photo_message(env, "wm1", (320, 240))
    env.session.clear()
    await env.feed(update_business_message(biz_message("bc1", CONTACT, OWNER, ".wtm © Brand", reply_to=photo, first_name="Owner")))
    for _ in range(100):
        if env.session.calls("SendPhoto") or env.session.calls("SendDocument"):
            break
        await asyncio.sleep(0.05)
    sent = env.session.calls("SendPhoto") or env.session.calls("SendDocument")
    assert sent and sent[0].business_connection_id == "bc1"
    job = await env.app.db.fetchone("SELECT kind, status FROM media_jobs ORDER BY id DESC LIMIT 1")
    assert job["kind"] == "watermark" and job["status"] == "done"


# ---- .quiet ---------------------------------------------------------------------------------------------------------
async def test_quiet_pauses_auto_replies_without_deleting_messages(env):
    await connect(env)
    await env.app.afk.enable(OWNER, "Занят")
    await env.feed(update_business_message(biz_message("bc1", CONTACT, OWNER, ".quiet 1h", first_name="Owner")))
    row = await env.app.chats.get(OWNER, CONTACT)
    assert row["muted_until"] and row["muted_until"] > 0
    env.session.clear()
    await env.feed(update_business_message(biz_message("bc1", CONTACT, CONTACT, "привет")))
    assert not [r for r in env.session.calls("SendMessage") if r.chat_id == CONTACT]      # no AFK reply
    assert not env.session.calls("DeleteBusinessMessages")                                 # nothing deleted
    await env.feed(update_business_message(biz_message("bc1", CONTACT, OWNER, ".quiet off", first_name="Owner")))
    assert (await env.app.chats.get(OWNER, CONTACT))["muted_until"] is None
    env.session.clear()
    await env.feed(update_business_message(biz_message("bc1", CONTACT, CONTACT, "ты тут?")))
    assert [r for r in env.session.calls("SendMessage") if r.chat_id == CONTACT]           # AFK replies again


# ---- admin notifications are localized ------------------------------------------------------------------------------
async def test_admin_notifications_use_the_admin_language(env):
    await env.app.users.ensure(OWNER)
    await env.app.settings.set(OWNER, "lang", "uz")
    await env.app.support_message(4200000001, "Yordam kerak")
    n = (await env.app.notifications.list(OWNER))[0]
    assert n["title"] == "Qo'llab-quvvatlash: 4200000001" and n["body"] == "Yordam kerak"
    await env.app.settings.set(OWNER, "lang", "ru")
    await env.app.notifications.notify_t(OWNER, "disk", "notify.disk_title", "notify.disk_body", mb=42)
    n = (await env.app.notifications.list(OWNER))[0]
    assert n["title"] == "Мало места на диске" and n["body"] == "Свободно 42 МБ"
