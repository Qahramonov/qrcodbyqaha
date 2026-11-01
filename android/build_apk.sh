#!/usr/bin/env bash
# =====================================================================================
#  Chat helper Control — APK build WITHOUT Android Studio / Gradle.
#  Works on Android in Termux and on Linux. Produces dist/Chat_helper_Control.apk
#
#  Termux packages:  pkg install -y aapt aapt2 apksigner d8 openjdk-17 python zip
#  (the script falls back to ecj / dalvik-dx / python zipalign when something is missing)
# =====================================================================================
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
APP="$HERE/app/src/main"
OUT="$HERE/build_out"
TOOLS="$HERE/.tools"
DIST="$ROOT/dist"
PKG="com.chathelper.control"
VERSION_NAME="${VERSION_NAME:-1.0.0}"
VERSION_CODE="${VERSION_CODE:-1}"
MIN_SDK=24
TARGET_SDK=34
KEYSTORE="${KEYSTORE:-$HERE/chat_helper_control.keystore}"
KS_PASS="${KS_PASS:-chathelper}"
KEY_ALIAS="${KEY_ALIAS:-chathelper}"

say() { printf '\033[1;35m▸\033[0m %s\n' "$*"; }
die() { printf '\033[1;31m✗ %s\033[0m\n' "$*" >&2; exit 1; }
mkdir -p "$TOOLS" "$DIST"

# ---------- locate tools -----------------------------------------------------------
AAPT2="${AAPT2:-$(command -v aapt2 || true)}"
[ -z "$AAPT2" ] && [ -x "$TOOLS/aapt2" ] && AAPT2="$TOOLS/aapt2"
[ -n "$AAPT2" ] || die "aapt2 not found. Termux: pkg install aapt2   (Linux: put aapt2 into android/.tools/)"

ANDROID_JAR="${ANDROID_JAR:-}"
for c in "$ANDROID_JAR" "${PREFIX:-/nonexistent}/share/aapt/android.jar" "${PREFIX:-/nonexistent}/share/java/android.jar" \
         "${ANDROID_HOME:-/nonexistent}/platforms/android-$TARGET_SDK/android.jar" "$TOOLS/android-$TARGET_SDK.jar"; do
  if [ -n "$c" ] && [ -f "$c" ]; then ANDROID_JAR="$c"; break; fi
done
if [ -z "$ANDROID_JAR" ] || [ ! -f "$ANDROID_JAR" ]; then
  say "android.jar (API $TARGET_SDK) not found — downloading the public SDK stub"
  curl -fL --retry 3 -o "$TOOLS/android-$TARGET_SDK.jar" \
    "https://raw.githubusercontent.com/Sable/android-platforms/master/android-$TARGET_SDK/android.jar" || die "download failed; set ANDROID_JAR=/path/to/android.jar"
  ANDROID_JAR="$TOOLS/android-$TARGET_SDK.jar"
fi

JAVAC="$(command -v javac || true)"
ECJ="$(command -v ecj || true)"
D8="$(command -v d8 || true)"
DX_JAR="${DX_JAR:-$TOOLS/dalvik-dx.jar}"
APKSIGNER="$(command -v apksigner || true)"
SIGNER_JAR="${SIGNER_JAR:-$TOOLS/uber-apk-signer.jar}"
PY="$(command -v python3 || command -v python || true)"
[ -n "$PY" ] || die "python is required (pkg install python)"

say "aapt2: $AAPT2"
say "android.jar: $ANDROID_JAR"

# ---------- 1. resources --------------------------------------------------------------
rm -rf "$OUT" && mkdir -p "$OUT/gen" "$OUT/classes" "$OUT/dex"
sed "s#<manifest xmlns:android=\"http://schemas.android.com/apk/res/android\">#<manifest xmlns:android=\"http://schemas.android.com/apk/res/android\" package=\"$PKG\" android:versionCode=\"$VERSION_CODE\" android:versionName=\"$VERSION_NAME\">#" \
  "$APP/AndroidManifest.xml" > "$OUT/AndroidManifest.xml"
say "aapt2 compile"
"$AAPT2" compile --dir "$APP/res" -o "$OUT/res.zip"
say "aapt2 link"
"$AAPT2" link -I "$ANDROID_JAR" --manifest "$OUT/AndroidManifest.xml" --min-sdk-version $MIN_SDK --target-sdk-version $TARGET_SDK \
  --version-code "$VERSION_CODE" --version-name "$VERSION_NAME" --java "$OUT/gen" --auto-add-overlay -o "$OUT/base.apk" "$OUT/res.zip"

# ---------- 2. java -----------------------------------------------------------------------
find "$APP/java" "$OUT/gen" -name '*.java' > "$OUT/sources.txt"
say "compiling $(wc -l < "$OUT/sources.txt") Java files"
if [ -n "$JAVAC" ]; then
  if ! "$JAVAC" -nowarn -encoding UTF-8 -source 8 -target 8 -bootclasspath "$ANDROID_JAR" -cp "$ANDROID_JAR" -d "$OUT/classes" @"$OUT/sources.txt" \
       > "$OUT/javac.log" 2>&1; then
    grep -v -E "^Picked up JAVA_TOOL_OPTIONS" "$OUT/javac.log" >&2
    die "javac failed"
  fi
elif [ -n "$ECJ" ]; then
  "$ECJ" -8 -nowarn -encoding UTF-8 -bootclasspath "$ANDROID_JAR" -d "$OUT/classes" @"$OUT/sources.txt" || die "ecj failed"
else
  die "No Java compiler. Termux: pkg install openjdk-17  (or: pkg install ecj)"
fi

# ---------- 3. dex ----------------------------------------------------------------------------
say "dexing"
if [ -n "$D8" ]; then
  find "$OUT/classes" -name '*.class' > "$OUT/classes.txt"
  "$D8" --release --min-api $MIN_SDK --lib "$ANDROID_JAR" --output "$OUT/dex" @"$OUT/classes.txt"
else
  [ -f "$DX_JAR" ] || curl -fL --retry 3 -o "$DX_JAR" "https://repo1.maven.org/maven2/com/jakewharton/android/repackaged/dalvik-dx/16.0.1/dalvik-dx-16.0.1.jar"
  java -cp "$DX_JAR" com.android.dx.command.Main --dex --min-sdk-version=$MIN_SDK --output="$OUT/dex/classes.dex" "$OUT/classes"
fi
[ -f "$OUT/dex/classes.dex" ] || die "dex step failed"

# ---------- 4. package + align --------------------------------------------------------------
say "packaging"
cp "$OUT/base.apk" "$OUT/unsigned.apk"
"$PY" - "$OUT/unsigned.apk" "$OUT/dex/classes.dex" <<'PYEOF'
import sys, zipfile
apk, dex = sys.argv[1], sys.argv[2]
with zipfile.ZipFile(apk, "a", compression=zipfile.ZIP_DEFLATED) as z:
    z.write(dex, "classes.dex")
PYEOF
"$PY" "$HERE/tools/zipalign.py" "$OUT/unsigned.apk" "$OUT/aligned.apk" || die "zipalign failed"

# ---------- 5. sign ----------------------------------------------------------------------------
if [ ! -f "$KEYSTORE" ]; then
  say "creating signing key $KEYSTORE (keep it! updates must be signed with the same key)"
  keytool -genkeypair -keystore "$KEYSTORE" -storepass "$KS_PASS" -keypass "$KS_PASS" -alias "$KEY_ALIAS" -keyalg RSA -keysize 3072 \
    -validity 10000 -dname "CN=Chat helper Control, O=Chat helper" >/dev/null 2>&1 || die "keytool failed (pkg install openjdk-17)"
fi
FINAL="$DIST/Chat_helper_Control.apk"
say "signing (APK Signature Scheme v2/v3)"
if [ -n "$APKSIGNER" ]; then
  "$APKSIGNER" sign --ks "$KEYSTORE" --ks-pass "pass:$KS_PASS" --ks-key-alias "$KEY_ALIAS" --min-sdk-version $MIN_SDK --out "$FINAL" "$OUT/aligned.apk"
  "$APKSIGNER" verify --verbose "$FINAL" | head -6
elif [ -f "$SIGNER_JAR" ]; then
  rm -rf "$OUT/signed" && mkdir -p "$OUT/signed"
  java -jar "$SIGNER_JAR" --apks "$OUT/aligned.apk" --ks "$KEYSTORE" --ksPass "$KS_PASS" --ksAlias "$KEY_ALIAS" --ksKeyPass "$KS_PASS" \
    --skipZipAlign --out "$OUT/signed" >/dev/null
  cp "$OUT/signed/"*.apk "$FINAL"
  java -jar "$SIGNER_JAR" --apks "$FINAL" --onlyVerify | grep -E "VERIFY|signature|scheme|Subject" | head -8 || true
else
  die "No APK signer. Termux: pkg install apksigner"
fi
"$PY" "$HERE/tools/zipalign.py" -c "$FINAL" && say "alignment OK"
ls -la "$FINAL"
say "done → $FINAL"
