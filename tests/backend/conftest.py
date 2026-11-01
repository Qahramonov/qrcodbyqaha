from __future__ import annotations

import sys
from pathlib import Path

import pytest
import pytest_asyncio

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fakes import make_bot  # noqa: E402

OWNER = 8053614984      # super admin from the specification
USER2 = 4200000001      # a second, regular Chat helper user
CONTACT = 5550000001    # a counterpart chatting with the owner


@pytest_asyncio.fixture
async def env(tmp_path: Path):
    from chat_helper.app import build_app
    from chat_helper.config import load_settings

    bot, session = make_bot()
    cfg = load_settings(None, data_dir=tmp_path / "data", bot_token="", openai_api_key="", gemini_api_key="", anthropic_api_key="",
                        compat_api_key="", compat_base_url="", payments_enabled=False)
    app, dp = await build_app(cfg, bot=bot)
    app.bot_info = await bot.get_me()
    app.sender.flood.per_chat_interval = 0.0
    app.sender.flood.global_interval = 0.0
    session.clear()

    class Env:
        pass
    e = Env()
    e.app, e.dp, e.bot, e.session, e.cfg = app, dp, bot, session, cfg

    async def feed(update):
        return await dp.feed_update(bot, update)
    e.feed = feed
    yield e
    for t in list(app.ai_auto._bg):
        t.cancel()
    await app.media.queue.stop()
    await app.db.close()


@pytest.fixture
def anyio_backend():
    return "asyncio"
