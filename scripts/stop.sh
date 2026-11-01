#!/usr/bin/env bash
# Graceful stop (SIGTERM → wait → SIGKILL as a last resort).
set -euo pipefail
. "$(dirname "$0")/_common.sh"
if pid="$(running_pid)"; then
  kill -TERM "$pid"
  for _ in $(seq 1 30); do kill -0 "$pid" 2>/dev/null || break; sleep 0.5; done
  if kill -0 "$pid" 2>/dev/null; then c_warn "forcing stop"; kill -KILL "$pid" || true; fi
  rm -f "$PIDFILE"
  c_ok "stopped"
else
  rm -f "$PIDFILE"   # stale PID file from a crash
  c_info "not running"
fi
command -v tmux >/dev/null && tmux kill-session -t "$SESSION" 2>/dev/null || true
command -v termux-wake-unlock >/dev/null && termux-wake-unlock || true
