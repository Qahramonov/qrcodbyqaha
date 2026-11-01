"""Chat helper — entry point.

    python main.py              # bot (long polling) + local API + workers
    python main.py --check      # configuration & environment self-check, no network writes
    python main.py --init-db    # create / migrate the database and exit
    python main.py --no-api     # run without the Android control API
    python main.py --api-only   # only the REST API (no Telegram polling)
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
    if want_bot:
        me = await app.bot.get_me()
        app.bot_info = me
        log.info("%s v%s started as @%s", APP_NAME, __version__, me.username)
        if not getattr(me, "can_connect_to_business", True):
            log.warning("Business Mode is OFF for this bot. Enable it in @BotFather → Bot Settings → Business Mode.")
        stats = await app.connections.restore(app.bot)
        log.info("business connections restored: %s", stats)

        async def polling() -> None:
            app.polling_active = True
            try:
                await dp.start_polling(app.bot, allowed_updates=dp.resolve_used_update_types(), handle_signals=False,
                                       polling_timeout=cfg.polling_timeout, close_bot_session=False)
            finally:
                app.polling_active = False
        tasks.append(asyncio.create_task(polling(), name="polling"))

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
        if t is not waiter and t.exception():
            log.error("component crashed: %s", t.exception())
    log.info("shutting down…")
    if want_bot:
        await dp.stop_polling() if dp._running_lock.locked() else None  # noqa: SLF001
    server = getattr(app, "api_server", None)
    if server is not None:
        server.should_exit = True
    for t in tasks:
        try:
            await asyncio.wait_for(t, timeout=10)
        except (asyncio.TimeoutError, Exception):
            t.cancel()
    await stop_background(app)
    if app.bot is not None:
        await app.bot.session.close()
    await app.db.close()
    pid_file.unlink(missing_ok=True)
    log.info("bye")
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
