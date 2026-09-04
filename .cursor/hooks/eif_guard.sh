#!/bin/sh
# POSIX launcher for Cursor project hooks. stdin/stdout are JSON.
# Always emit a permission JSON object and exit 0 so failClosed does not
# treat a launcher/interpreter failure as a mute empty-stdout crash.
set -eu
DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
SCRIPT="$DIR/eif_guard.py"

eif_root="${CURSOR_PROJECT_DIR:-$PWD}"
emit_static() {
  kind=$1
  code=$2
  msg=$3
  mkdir -p "$eif_root/.eif" 2>/dev/null || true
  printf '%s\n' "$code: $msg" >> "$eif_root/.eif/hook-guard.log" || true
  if [ -f "$DIR/eif_guard_${kind}.json" ]; then
    cat "$DIR/eif_guard_${kind}.json"
  else
    printf '%s\n' "{\"permission\":\"deny\",\"reason_code\":\"$code\",\"eif_guard_class\":\"crash\",\"user_message\":\"EIF_GUARD_CRASH: $code: $msg\",\"agent_message\":\"EIF_GUARD_CRASH: $code: $msg\"}"
  fi
}

run_python() {
  exe=$1
  set +e
  "$exe" -u "$SCRIPT"
  rc=$?
  set -e
  if [ "$rc" -ne 0 ]; then
    emit_static crash HOOK_INTERNAL_ERROR "Python interpreter exited before a permission JSON decision"
  fi
  exit 0
}

if command -v python3 >/dev/null 2>&1; then
  run_python python3
fi
if command -v python >/dev/null 2>&1; then
  run_python python
fi
emit_static failclosed HOOK_LAUNCHER_ERROR "no Python interpreter found on PATH (tried python3, python)"
exit 0
