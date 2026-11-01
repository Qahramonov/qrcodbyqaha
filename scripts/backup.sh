#!/usr/bin/env bash
# Consistent online backup of the SQLite database (safe while the bot is running).
# Optional: copy to phone storage after `termux-setup-storage`:  ./scripts/backup.sh --shared
set -euo pipefail
. "$(dirname "$0")/_common.sh"
cd "$BACKEND"
OUT="$("$PY" - <<'PYEOF'
import asyncio, sys, time
from pathlib import Path
sys.path.insert(0, ".")
from chat_helper.config import load_settings
from chat_helper.database.db import Database
async def main():
    cfg = load_settings()
    db = Database(cfg.database_path)
    await db.connect()
    p = await db.backup_to(cfg.backups_dir / time.strftime("chat_helper_%Y%m%d_%H%M%S_cli.db"))
    await db.close()
    files = sorted(cfg.backups_dir.glob("chat_helper_*.db"), key=lambda f: f.stat().st_mtime, reverse=True)
    for f in files[cfg.backup_keep:]:
        f.unlink()
    print(p)
asyncio.run(main())
PYEOF
)"
c_ok "backup: $OUT"
if [ "${1:-}" = "--shared" ] && [ -d "$HOME/storage/shared" ]; then
  mkdir -p "$HOME/storage/shared/ChatHelper/backups"
  cp "$OUT" "$HOME/storage/shared/ChatHelper/backups/"
  c_ok "copied to shared storage: ChatHelper/backups/"
fi
