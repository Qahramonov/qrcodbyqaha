#!/usr/bin/env bash
# Runs the Android test-suite on the JVM (Robolectric, real Android 14 framework) against a REAL backend instance.
# Requirements: JDK 17+, Maven, Python deps of the backend. Not needed for normal usage on the phone.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"
PORT="${PORT:-18787}"
export DATA_DIR="$TMP/data" API_PORT="$PORT" API_HOST=127.0.0.1 BOT_TOKEN="" CHAT_HELPER_ENV="$TMP/none.env"

echo "▸ building resources/R.java"
"$ROOT/android/build_apk.sh" >/dev/null

if curl -fsS "http://127.0.0.1:$PORT/api/v1/health" >/dev/null 2>&1; then
  echo "port $PORT is already in use — stop the other backend first" >&2; exit 1
fi
echo "▸ starting backend (api-only) on :$PORT"
( cd "$ROOT/backend" && exec python3 main.py --api-only >"$TMP/backend.log" 2>&1 ) &
BACK=$!
trap 'kill $BACK 2>/dev/null || true; rm -rf "$TMP"' EXIT
for i in $(seq 1 60); do curl -fsS "http://127.0.0.1:$PORT/api/v1/health" >/dev/null 2>&1 && break; sleep 0.5; done
curl -fsS "http://127.0.0.1:$PORT/api/v1/health" >/dev/null || { cat "$TMP/backend.log"; exit 1; }

CODES=($(cd "$ROOT/backend" && python3 tools/issue_pair_code.py --count 2))
echo "▸ pairing codes issued: ${#CODES[@]}"

GEN="$ROOT/android/robolectric/target/generated-test-resources/com/android/tools"
mkdir -p "$GEN"
cat > "$GEN/test_config.properties" <<PROPS
android_merged_manifest=$ROOT/android/build_out/AndroidManifest.xml
android_resource_apk=$ROOT/android/build_out/base.apk
android_custom_package=com.chathelper.control
PROPS

cd "$ROOT/android/robolectric"
set +e
mvn -q -B test -Dch.server="http://127.0.0.1:$PORT" -Dch.code="${CODES[0]}" -Dch.code2="${CODES[1]:-}" 2>&1 | grep -v "^Picked up JAVA_TOOL_OPTIONS"
RC=${PIPESTATUS[0]}
set -e
echo "▸ results:"
grep -h "Tests run" target/surefire-reports/*.txt || true
[ "$RC" -eq 0 ] && echo "▸ Android tests PASSED" || { echo "▸ Android tests FAILED (rc=$RC)"; exit "$RC"; }
