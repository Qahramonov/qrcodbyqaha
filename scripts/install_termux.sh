#!/usr/bin/env bash
# =====================================================================
#  Chat helper — one-shot installer for Android (Termux). No root, no PC.
#    cd ~/Chat_helper && bash scripts/install_termux.sh
# =====================================================================
set -euo pipefail
. "$(dirname "$0")/_common.sh"

c_info "1/10 Packages"
if is_termux; then
  pkg update -y
  # rust + binutils: build pydantic-core; clang/make/libjpeg/freetype: Pillow; ffmpeg: Media Studio
  pkg install -y python python-pip git tmux ffmpeg rust binutils clang make pkg-config libjpeg-turbo libpng freetype zlib openssl curl sqlite
  pkg install -y termux-api >/dev/null 2>&1 || c_warn "termux-api not installed (optional: notifications/wake features)"
  # optional, for building the APK on the phone (see docs/INSTALL_ANDROID.md)
  # pkg install -y aapt aapt2 apksigner d8 openjdk-17
else
  c_warn "Not Termux — make sure python3 (3.11+), pip and ffmpeg are installed."
fi

c_info "2/10 Python"
"$PY" - <<'PYEOF'
import sys
assert sys.version_info >= (3, 11), f"Python 3.11+ required, found {sys.version}"
print("python", sys.version.split()[0], "OK")
PYEOF

c_info "3/10 FFmpeg"
if command -v ffmpeg >/dev/null && command -v ffprobe >/dev/null; then c_ok "$(ffmpeg -version | head -1)"; else c_warn "ffmpeg missing: media commands will be disabled"; fi

c_info "4/10 Python libraries (first run can take 10–20 min: pydantic-core is compiled with Rust)"
export ANDROID_API_LEVEL="${ANDROID_API_LEVEL:-$(getprop ro.build.version.sdk 2>/dev/null || echo 24)}"
export CARGO_BUILD_JOBS="${CARGO_BUILD_JOBS:-2}"
"$PY" -m pip install --upgrade wheel setuptools >/dev/null
"$PY" -m pip install -r "$BACKEND/requirements.txt"

c_info "5/10 Environment"
mkdir -p "$DATA/logs" "$DATA/backups" "$DATA/tmp"
chmod 700 "$DATA" || true

c_info "6/10 .env"
if [ ! -f "$BACKEND/.env" ]; then
  cp "$BACKEND/.env.example" "$BACKEND/.env"
  chmod 600 "$BACKEND/.env" || true
  c_warn "Created backend/.env — put your BOT_TOKEN there:  nano $BACKEND/.env"
else
  c_ok ".env exists"
fi

c_info "7/10 Database"
( cd "$BACKEND" && "$PY" main.py --init-db )

c_info "8/10 Tests (quick)"
( cd "$ROOT" && "$PY" -m pytest -q -x tests/backend 2>&1 | tail -3 ) || c_warn "some tests failed — see output above"

c_info "9/10 Self-check"
( cd "$BACKEND" && "$PY" main.py --check ) || true

c_info "10/10 Done"
cat <<TXT

Next steps:
  1) nano backend/.env              → BOT_TOKEN=...  (from @BotFather, Business Mode ON)
  2) ./scripts/start.sh             → starts bot + API in tmux (survives closing the app)
  3) Telegram → @YourBot → /start   → menu, then /app to get a code for Chat helper Control
  4) Termux: termux-wake-lock       → keep Android from sleeping the process
TXT
