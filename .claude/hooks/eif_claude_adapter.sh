#!/bin/sh
# Thin launcher: find an interpreter, run the adapter, pass its exit code
# through unchanged. See eif_claude_adapter.cmd for the rationale (Claude
# Code's exit-2-alone-blocks contract means no JSON body is needed here).
set -u
DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd) || exit 2
SCRIPT="$DIR/eif_claude_adapter.py"

if command -v python3 >/dev/null 2>&1; then
  exe=python3
elif command -v python >/dev/null 2>&1; then
  exe=python
else
  printf '%s\n' 'EIF claude-code adapter fault SHIM_NO_INTERPRETER: no Python interpreter found on PATH (tried python3, python)' >&2
  exit 2
fi

"$exe" -u -X utf8 "$SCRIPT"
rc=$?
if [ "$rc" -eq 0 ] || [ "$rc" -eq 2 ]; then
  exit "$rc"
fi
printf '%s\n' "EIF claude-code adapter fault SHIM_LAUNCHER_CRASH: adapter exited $rc before a decision; fail-closed" >&2
exit 2
