#!/usr/bin/env bash
# Restore a database backup:  ./scripts/restore.sh                      → list backups
#                             ./scripts/restore.sh chat_helper_XXXX.db  → stop, restore (safety copy kept), start
set -euo pipefail
. "$(dirname "$0")/_common.sh"
if [ -z "${1:-}" ]; then
  c_info "backups in $DATA/backups (newest first):"
  ls -1t "$DATA/backups" 2>/dev/null | grep '\.db$' || echo "  (none)"
  echo "usage: ./scripts/restore.sh <file>"
  exit 0
fi
WAS_RUNNING=0
if running_pid >/dev/null; then WAS_RUNNING=1; "$(dirname "$0")/stop.sh"; fi
( cd "$BACKEND" && "$PY" main.py --restore "$1" )
[ "$WAS_RUNNING" = 1 ] && "$(dirname "$0")/start.sh" || true
