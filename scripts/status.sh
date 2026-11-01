#!/usr/bin/env bash
# Process, API health, resources and recent log lines.
. "$(dirname "$0")/_common.sh"
if pid="$(running_pid)"; then c_ok "process: running (pid $pid)"; else c_err "process: not running"; fi
PORT="$(api_port)"; PORT="${PORT:-8787}"
if out="$(curl -fsS "http://127.0.0.1:$PORT/api/v1/health" 2>/dev/null)"; then c_ok "API: $out"; else c_warn "API: no answer on 127.0.0.1:$PORT"; fi
command -v tmux >/dev/null && tmux has-session -t "$SESSION" 2>/dev/null && c_ok "tmux session: $SESSION"
df -h "$DATA" 2>/dev/null | tail -1 | awk '{print "disk: " $4 " free of " $2}'
[ -f "$PIDFILE" ] && [ -r "/proc/$(cat "$PIDFILE")/status" ] && grep VmRSS "/proc/$(cat "$PIDFILE")/status" | awk '{print "memory: " $2/1024 " MB"}'
echo "── last log lines ──"
tail -n 15 "$DATA/logs/chat_helper.log" 2>/dev/null || tail -n 15 "$LOGFILE" 2>/dev/null || echo "(no logs yet)"
