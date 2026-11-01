#!/usr/bin/env bash
# Shared helpers for Chat helper scripts (Termux / Linux).
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="$ROOT/backend"
DATA="${DATA_DIR:-$BACKEND/data}"
PIDFILE="$DATA/chat_helper.pid"
LOGFILE="$DATA/logs/console.log"
SESSION="chat_helper"
PY="$(command -v python3 || command -v python)"
c_ok() { printf '\033[1;32m✓\033[0m %s\n' "$*"; }
c_info() { printf '\033[1;35m▸\033[0m %s\n' "$*"; }
c_warn() { printf '\033[1;33m!\033[0m %s\n' "$*"; }
c_err() { printf '\033[1;31m✗\033[0m %s\n' "$*" >&2; }
is_termux() { [ -n "${PREFIX:-}" ] && [ -d "/data/data/com.termux" ]; }
running_pid() {
  if [ -f "$PIDFILE" ]; then
    local pid; pid="$(cat "$PIDFILE" 2>/dev/null)"
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then echo "$pid"; return 0; fi
  fi
  return 1
}
api_port() { grep -E '^API_PORT=' "$BACKEND/.env" 2>/dev/null | tail -1 | cut -d= -f2 | tr -d ' "' || true; }
