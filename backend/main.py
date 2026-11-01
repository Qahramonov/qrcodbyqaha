"""Chat helper — entry point.

    python main.py              # bot (long polling) + local API + workers
    python main.py --check      # configuration & environment self-check, no network writes
    python main.py --init-db    # create / migrate the database and exit
    python main.py --no-api     # run without the Android control API
    python main.py --api-only   # only the REST API (no Telegram polling)
    python main.py --restore FILE   # offline restore of a backup (bot must be stopped)
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import signal
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from chat_helper import APP_NAME, __version__  # noqa: E402
from chat_helper.config import load_settings, set_settings  # noqa: E402

log = logging.getLogger("chat_helper")


async def run(args: argparse.Namespace) -> int:
    from chat_helper.app import build_app, start_background, stop_background

    cfg = load_settings(args.env)
    set_settings(cfg)
    if args.init_db:
        app, _ = await build_app(cfg, with_bot=False)
        log.info("database ready at %s", cfg.database_path)
        await app.db.close()
        return 0
    if args.check:
        return await self_check(cfg)
    if args.restore:
        return restore_backup(cfg, args.restore)

    want_bot = not args.api_only
    app, dp = await build_app(cfg, with_bot=want_bot)
    pid_file = cfg.data_dir / "chat_helper.pid"
    pid_file.write_text(str(os.getpid()))
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:  # pragma: no cover
            pass

    tasks: list[asyncio.Task] = []
    await start_background(app)
    exit_code = 0
    if want_bot:
        from aiogram.exceptions import TelegramNetworkError, TelegramServerError, TelegramUnauthorizedError

        async def bot_main() -> None:
            nonlocal exit_code
            delay = 5
            while True:  # the phone may be offline right after boot (Termux:Boot) — wait instead of exiting
                try:
                    me = await app.bot.get_me()
                    break
                except TelegramUnauthorizedError:
                    log.error("Telegram rejected BOT_TOKEN (Unauthorized). Copy the token again from @BotFather into backend/.env")
                    exit_code = 3
                    return
                except (TelegramNetworkError, TelegramServerError, OSError) as e:
                    log.warning("Telegram is unreachable (%s) — retrying in %ss", type(e).__name__, delay)
                    await asyncio.sleep(delay)
                    delay = min(delay * 2, 60)
            # long polling and a webhook cannot coexist: drop a webhook left from another setup (pending updates are kept)
            if (await app.bot.get_webhook_info()).url:
                log.warning("a webhook was set for this bot — removing it to use long polling")
                await app.bot.delete_webhook(drop_pending_updates=False)
            app.bot_info = me
            log.info("%s v%s started as @%s", APP_NAME, __version__, me.username)
            if not getattr(me, "can_connect_to_business", True):
                log.warning("Business Mode is OFF for this bot. Enable it in @BotFather → Bot Settings → Business Mode.")
            stats = await app.connections.restore(app.bot)
            log.info("business connections restored: %s", stats)
            app.polling_active = True
            try:
                await dp.start_polling(app.bot, allowed_updates=dp.resolve_used_update_types(), handle_signals=False,
                                       polling_timeout=cfg.polling_timeout, close_bot_session=False)
            finally:
                app.polling_active = False
        tasks.append(asyncio.create_task(bot_main(), name="bot"))

    if cfg.api_enabled and not args.no_api:
        import uvicorn

        from chat_helper.api.server import create_api
        api = create_api(app)
        ucfg = uvicorn.Config(api, host=cfg.api_host, port=cfg.api_port, log_level="warning", access_log=False,
                              ssl_certfile=cfg.api_ssl_certfile or None, ssl_keyfile=cfg.api_ssl_keyfile or None, lifespan="off")
        server = uvicorn.Server(ucfg)
        server.install_signal_handlers = lambda: None  # type: ignore[method-assign]
        app.api_server = server  # type: ignore[attr-defined]
        tasks.append(asyncio.create_task(server.serve(), name="api"))
        log.info("control API on %s://%s:%s (docs: /api/docs)", "https" if cfg.api_ssl_certfile else "http", cfg.api_host, cfg.api_port)

    waiter = asyncio.create_task(stop.wait())
    done, _ = await asyncio.wait([waiter, *tasks], return_when=asyncio.FIRST_COMPLETED)
    for t in done:
        if t is not waiter and not t.cancelled() and t.exception():
            log.error("component crashed: %s", t.exception())
    log.info("shutting down…")
    if want_bot:
        if dp._running_lock.locked():  # noqa: SLF001
            await dp.stop_polling()
        elif not app.polling_active:
            tasks[0].cancel()  # still waiting for Telegram — nothing to drain
    server = getattr(app, "api_server", None)
    if server is not None:
        server.should_exit = True
    for t in tasks:
        try:
            await asyncio.wait_for(t, timeout=10)
        except (asyncio.TimeoutError, asyncio.CancelledError, Exception):
            t.cancel()
    await stop_background(app)
    if app.bot is not None:
        await app.bot.session.close()
    await app.db.close()
    pid_file.unlink(missing_ok=True)
    log.info("bye")
    return exit_code


def restore_backup(cfg, name: str) -> int:
    """Validate a backup, keep a safety copy of the current DB, then replace it (WAL/SHM files are removed)."""
    import sqlite3
    import time

    from chat_helper.database.db import Database

    pid_file = cfg.data_dir / "chat_helper.pid"
    if pid_file.exists():
        try:
            os.kill(int(pid_file.read_text().strip()), 0)
            print("ERROR: Chat helper is running — stop it first (./scripts/stop.sh)", file=sys.stderr)
            return 2
        except (ValueError, ProcessLookupError, PermissionError):
            pid_file.unlink(missing_ok=True)
    src = Path(name).expanduser()
    if not src.is_file():
        src = cfg.backups_dir / name
    if not src.is_file():
        print(f"ERROR: backup not found: {name}", file=sys.stderr)
        return 2
    db_path = Path(cfg.database_path)
    if db_path.exists():
        safety = cfg.backups_dir / time.strftime("chat_helper_%Y%m%d_%H%M%S_pre_restore.db")
        safety.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(str(db_path)) as cur, sqlite3.connect(str(safety)) as dst:
            cur.backup(dst)
        print(f"current database saved to {safety}")
    try:
        Database.restore_from(src, db_path)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    print(f"restored {src.name} → {db_path}. Start again: ./scripts/start.sh")
    return 0


async def self_check(cfg) -> int:
    import shutil

    from chat_helper.app import build_app
    ok = True
    print(f"{APP_NAME} v{__version__} self-check")
    print(f"  python           : {sys.version.split()[0]}")
    print(f"  data dir         : {cfg.data_dir}")
    print(f"  BOT_TOKEN        : {'set' if cfg.bot_token else 'MISSING'}")
    ok &= bool(cfg.bot_token)
    for b in (cfg.ffmpeg_bin, cfg.ffprobe_bin):
        found = shutil.which(b) is not None
        print(f"  {b:<17}: {'ok' if found else 'missing (pkg install ffmpeg)'}")
    app, _ = await build_app(cfg, with_bot=False)
    integ = await app.db.integrity_check()
    print(f"  database         : {'ok' if integ['ok'] else 'ERROR'} ({cfg.database_path})")
    ok &= integ["ok"]
    print(f"  commands         : {len(app.registry)} registered")
    provs = [p["name"] for p in app.ai.providers_status() if p["configured"]]
    print(f"  AI providers     : {', '.join(provs) or 'none (AI features disabled)'}")
    print(f"  API              : {cfg.api_host}:{cfg.api_port} remote={cfg.api_remote_enabled}")
    if cfg.api_remote_enabled and not (cfg.api_ssl_certfile and cfg.api_ssl_keyfile):
        print("  WARNING          : API_REMOTE_ENABLED needs API_SSL_CERTFILE + API_SSL_KEYFILE; listening on 127.0.0.1 only")
    print(f"  super admin      : {cfg.super_admin_id}")
    await app.db.close()
    print("RESULT:", "OK" if ok else "PROBLEMS FOUND")
    return 0 if ok else 1


def main() -> None:
    parser = argparse.ArgumentParser(description=f"{APP_NAME} backend")
    parser.add_argument("--env", default=None, help="path to .env file")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--init-db", action="store_true")
    parser.add_argument("--no-api", action="store_true")
    parser.add_argument("--api-only", action="store_true")
    parser.add_argument("--restore", metavar="FILE", default=None, help="restore a backup (name in data/backups or a path)")
    args = parser.parse_args()
    try:
        code = asyncio.run(run(args))
    except KeyboardInterrupt:
        code = 0
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        code = 2
    sys.exit(code)


if __name__ == "__main__":
    main()
