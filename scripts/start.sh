#!/usr/bin/env bash
# Start Chat helper (bot + local API) in a detached tmux session (or nohup without tmux).
set -euo pipefail
. "$(dirname "$0")/_common.sh"
if pid="$(running_pid)"; then c_ok "already running (pid $pid)"; exit 0; fi
[ -f "$BACKEND/.env" ] || { c_err "backend/.env missing — run scripts/install_termux.sh"; exit 1; }
grep -qE '^BOT_TOKEN=.+' "$BACKEND/.env" || { c_err "BOT_TOKEN is empty in backend/.env"; exit 1; }
mkdir -p "$DATA/logs"
command -v termux-wake-lock >/dev/null && termux-wake-lock || true
CMD="cd '$BACKEND' && exec '$PY' main.py $* >> '$LOGFILE' 2>&1"
if command -v tmux >/dev/null; then
  tmux has-session -t "$SESSION" 2>/dev/null && tmux kill-session -t "$SESSION"
  tmux new-session -d -s "$SESSION" "bash -c \"$CMD\""
  c_info "started in tmux session '$SESSION' (attach: tmux attach -t $SESSION, detach: Ctrl+B then D)"
else
  nohup bash -c "$CMD" >/dev/null 2>&1 &
  c_info "started with nohup"
fi
for _ in $(seq 1 40); do
  if running_pid >/dev/null; then c_ok "Chat helper is running (pid $(running_pid))"; exit 0; fi
  sleep 0.5
done
c_err "did not start — last log lines:"; tail -n 30 "$LOGFILE" || true; exit 1
