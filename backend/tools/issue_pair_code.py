"""Issue a one-time Chat helper Control pairing code from the local shell (Termux).

Normally codes are issued in Telegram (/app). This tool exists for setup/testing on the device itself:
anyone who can run it already has full access to the backend files, so it does not weaken security.

    python tools/issue_pair_code.py              # code for SUPER_ADMIN_ID
    python tools/issue_pair_code.py --user 123   # code for another existing user
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from chat_helper.auth.service import AuthService  # noqa: E402
from chat_helper.config import load_settings  # noqa: E402
from chat_helper.database.db import Database  # noqa: E402
from chat_helper.database.migrations import apply_migrations  # noqa: E402
from chat_helper.security.ratelimit import SlidingWindowLimiter  # noqa: E402
from chat_helper.services.audit import AuditService  # noqa: E402
from chat_helper.services.users import UserService  # noqa: E402


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--user", type=int, default=None)
    ap.add_argument("--count", type=int, default=1)
    args = ap.parse_args()
    cfg = load_settings()
    cfg.ensure_dirs()
    db = Database(cfg.database_path)
    await db.connect()
    await apply_migrations(db)
    users = UserService(db, cfg.super_admin_id)
    uid = args.user or cfg.super_admin_id
    await users.ensure(uid)
    auth = AuthService(db, cfg.load_or_create_secret(), users, SlidingWindowLimiter(), AuditService(db), None,
                       cfg.access_token_ttl, cfg.refresh_token_ttl, cfg.pairing_code_ttl)
    codes = []
    for _ in range(max(1, args.count)):
        code, _exp = await auth.create_pairing_code(uid)
        codes.append(code)
    # create_pairing_code invalidates previous unused codes of the same user; keep only the newest if count > 1
    if args.count > 1:
        await db.execute("UPDATE pairing_codes SET used_at=NULL WHERE user_id=? AND expires_at > strftime('%s','now')", (uid,))
    await db.close()
    print("\n".join(codes))


if __name__ == "__main__":
    asyncio.run(main())
