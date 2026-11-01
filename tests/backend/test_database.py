"""Database layer: migrations, transactions, concurrent writes, backup/restore, settings validation, payments idempotency."""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from conftest import OWNER, USER2

from chat_helper.database.db import Database
from chat_helper.database.migrations import MIGRATIONS, apply_migrations, current_version
from chat_helper.services.settings import SettingsError



async def test_migrations_idempotent(tmp_path: Path):
    db = Database(tmp_path / "t.db")
    await db.connect()
    first = await apply_migrations(db)
    second = await apply_migrations(db)
    assert first == [v for v, _, _ in MIGRATIONS] and second == []
    assert await current_version(db) == MIGRATIONS[-1][0]
    mode = await db.fetchval("PRAGMA journal_mode")
    fk = await db.fetchval("PRAGMA foreign_keys")
    assert mode == "wal" and fk == 1
    await db.close()


async def test_transaction_rollback(env):
    db = env.app.db
    with pytest.raises(RuntimeError):
        async with db.transaction() as tx:
            await tx.execute("INSERT INTO users(id, created_at) VALUES (1, 1)")
            raise RuntimeError("boom")
    assert await db.fetchval("SELECT COUNT(*) FROM users WHERE id=1") == 0


async def test_concurrent_writes(env):
    db = env.app.db

    async def writer(i):
        await env.app.metrics.incr("concurrency_test", OWNER)
    await asyncio.gather(*(writer(i) for i in range(200)))
    assert await env.app.metrics.total("concurrency_test", OWNER) == 200
    assert await env.app.metrics.total("concurrency_test", 0) == 200
    assert (await db.integrity_check())["ok"]


async def test_backup_and_restore(env, tmp_path: Path):
    await env.app.users.ensure(OWNER)
    path = await env.app.backups.create("test")
    assert path.exists() and env.app.backups.list()
    target = tmp_path / "restored.db"
    target.write_bytes(b"")
    Database.restore_from(path, target)
    db2 = Database(target)
    await db2.connect()
    assert await db2.fetchval("SELECT COUNT(*) FROM users WHERE id=?", (OWNER,)) == 1
    await db2.close()
    bad = tmp_path / "bad.db"
    bad.write_bytes(b"garbage" * 100)
    with pytest.raises(Exception):
        Database.restore_from(bad, target)


async def test_settings_validation(env):
    s = env.app.settings
    await env.app.users.ensure(OWNER)
    with pytest.raises(SettingsError):
        await s.set(OWNER, "prefix", "a")
    with pytest.raises(SettingsError):
        await s.set(OWNER, "ai_disclosure", "  ")
    with pytest.raises(SettingsError):
        await s.set(OWNER, "nope", 1)
    with pytest.raises(SettingsError):
        await s.set(OWNER, "timezone", "Mars/Olympus")
    assert await s.set(OWNER, "work_start", "9:5".replace("9:5", "9:05")) == "09:05"


async def test_user_data_deletion(env):
    await env.app.users.ensure(USER2)
    await env.app.settings.set(USER2, "lang", "uz")
    await env.app.ai.memory.remember(USER2, "fact")
    await env.app.users.delete_user_data(USER2)
    assert await env.app.db.fetchval("SELECT COUNT(*) FROM user_settings WHERE user_id=?", (USER2,)) == 0
    assert await env.app.db.fetchval("SELECT COUNT(*) FROM ai_memory WHERE user_id=?", (USER2,)) == 0


async def test_payment_idempotency_and_validation(env):
    import datetime as dt

    from aiogram.types import Chat, Message, SuccessfulPayment, User
    env.app.config.payments_enabled = True
    await env.app.users.ensure(USER2)
    await env.app.payments.send_invoice(USER2, "plus")
    payload = (await env.app.db.fetchone("SELECT payload FROM payments"))["payload"]

    def paid(amount=150, charge="ch_1"):
        return Message(message_id=1, date=dt.datetime.now(dt.timezone.utc), chat=Chat(id=USER2, type="private"),
                       from_user=User(id=USER2, is_bot=False, first_name="B"),
                       successful_payment=SuccessfulPayment(currency="XTR", total_amount=amount, invoice_payload=payload,
                                                            telegram_payment_charge_id=charge, provider_payment_charge_id=""))
    sub = await env.app.payments.on_success(paid())
    assert sub and sub["plan_id"] == "plus"
    assert await env.app.payments.on_success(paid()) is None  # same charge id → no double grant
    assert await env.app.db.fetchval("SELECT COUNT(*) FROM subscriptions WHERE user_id=?", (USER2,)) == 1
    assert await env.app.payments.on_success(paid(amount=1, charge="ch_2")) is None  # amount mismatch → orphan, no grant


async def test_payments_disabled_by_default(env):
    with pytest.raises(ValueError):
        await env.app.payments.send_invoice(USER2, "plus")


async def test_scheduler_runs_and_recovers(env):
    sch = env.app.scheduler
    ran = []

    async def h(task):
        ran.append(task["payload"]["x"])
    sch.register("t", h)
    await sch.add(OWNER, "t", {"x": 1}, 0)
    tid = await sch.add(OWNER, "t", {"x": 2}, 0)
    await env.app.db.execute("UPDATE scheduled_tasks SET status='running' WHERE id=?", (tid,))
    assert await sch.recover() == 1
    await sch.run_due()
    assert sorted(ran) == [1, 2]
    await sch.run_due()
    assert sorted(ran) == [1, 2]  # never executed twice


async def test_cli_restore_keeps_safety_copy_and_refuses_while_running(tmp_path: Path):
    import os

    import main as entry
    from chat_helper.config import load_settings

    cfg = load_settings(None, data_dir=tmp_path / "data", bot_token="")
    db = Database(cfg.database_path)
    await db.connect()
    try:
        await apply_migrations(db)
        await db.execute("INSERT INTO users(id, created_at) VALUES (?,?)", (OWNER, 1))
        snap = await db.backup_to(cfg.backups_dir / "chat_helper_snap.db")
        await db.execute("INSERT INTO users(id, created_at) VALUES (?,?)", (USER2, 1))
    finally:
        await db.close()

    pid = cfg.data_dir / "chat_helper.pid"
    pid.write_text(str(os.getpid()))                      # "running" → must refuse
    assert entry.restore_backup(cfg, snap.name) == 2
    pid.unlink()
    assert entry.restore_backup(cfg, "does_not_exist.db") == 2
    assert entry.restore_backup(cfg, snap.name) == 0
    assert list(cfg.backups_dir.glob("*_pre_restore.db")), "safety copy of the replaced database"
    db = Database(cfg.database_path)
    await db.connect()
    try:
        assert [r["id"] for r in await db.fetchall("SELECT id FROM users ORDER BY id")] == [OWNER]
    finally:
        await db.close()
