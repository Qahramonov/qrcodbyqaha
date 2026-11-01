#!/usr/bin/env bash
# Backend test-suite (pytest). Android tests: scripts/run_android_tests.sh (needs JDK + Maven).
set -euo pipefail
. "$(dirname "$0")/_common.sh"
cd "$ROOT"
"$PY" -m pytest -q "$@"
