#!/bin/sh
# POSIX launcher for Cursor project hooks. stdin/stdout are JSON.
set -eu
DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
SCRIPT="$DIR/eif_guard.py"

if command -v python3 >/dev/null 2>&1; then
  exec python3 -u "$SCRIPT"
fi
if command -v python >/dev/null 2>&1; then
  exec python -u "$SCRIPT"
fi
echo "EIF hook launcher: no Python interpreter found on PATH (tried python3, python)" >&2
exit 1
