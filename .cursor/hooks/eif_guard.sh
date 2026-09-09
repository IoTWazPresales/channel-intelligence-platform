#!/bin/sh
# Hold child bytes until one complete permission response has been validated.
# Fallback state exists before path discovery or optional shell strictness.
eif_root=${CURSOR_PROJECT_DIR:-${PWD:-.}}
capture_dir=
emitted=0

emit_static() {
  code=$1
  mkdir -p "$eif_root/.eif" 2>/dev/null || true
  if ! printf '%s\n' "{\"decision_kind\":\"harness_fault\",\"reason_code\":\"$code\",\"permission\":\"deny\"}" >> "$eif_root/.eif/hook-guard.log"; then
    printf '%s\n' 'EIF harness fault HOOK_LOG_FAILURE: launcher could not write hook-guard.log' >&2
  fi
  printf '%s\n' "EIF harness fault $code: launcher could not obtain a valid permission decision" >&2
  emitted=1
  printf '%s\n' "{\"permission\":\"deny\",\"decision_kind\":\"harness_fault\",\"reason_code\":\"$code\",\"user_message\":\"$code: guard launcher failed\",\"agent_message\":\"EIF harness fault: launcher could not obtain a valid permission decision; repair before retrying\"}"
}

cleanup() {
  if [ -n "$capture_dir" ]; then
    rm -f -- "$capture_dir/response.json" 2>/dev/null || true
    rmdir -- "$capture_dir" 2>/dev/null || true
  fi
}

finish() {
  rc=$?
  trap - 0
  cleanup
  if [ "$emitted" -eq 0 ]; then
    emit_static HOOK_LAUNCHER_ERROR
    exit 0
  fi
  exit "$rc"
}
trap finish 0
set -u

DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd) || exit 0
SCRIPT="$DIR/eif_guard.py"
if command -v python3 >/dev/null 2>&1; then
  exe=python3
elif command -v python >/dev/null 2>&1; then
  exe=python
else
  emit_static HOOK_LAUNCHER_ERROR
  exit 0
fi

mkdir -p "$eif_root/.eif/runtime/hook-launcher" 2>/dev/null || exit 0
capture_dir=$(mktemp -d "$eif_root/.eif/runtime/hook-launcher/invoke.XXXXXXXX") || exit 0
capture="$capture_dir/response.json"
"$exe" -u -X utf8 "$SCRIPT" > "$capture"
rc=$?
if [ "$rc" -ne 0 ] && [ "$rc" -ne 2 ]; then
  emit_static HOOK_INTERNAL_ERROR
  exit 0
fi

# The exact marker proves the validator ran; exit zero alone is not evidence
# when the selected executable can itself be a broken command shim.
validated=$("$exe" -u -X utf8 -I -B -c "import json,sys; d=json.load(open(sys.argv[1],encoding='utf-8')); valid=isinstance(d,dict) and d.get('permission') in ('allow','deny') and d.get('decision_kind') in ('policy','harness_fault') and isinstance(d.get('reason_code'),str) and bool(d['reason_code']) and ((int(sys.argv[2])==2)==(d['permission']=='deny' and d['decision_kind']=='policy')); json.dumps(d,allow_nan=False); print('EIF_VALID' if valid else 'INVALID',end='')" "$capture" "$rc" </dev/null 2>/dev/null)
validation_rc=$?
if [ "$validation_rc" -ne 0 ] || [ "$validated" != 'EIF_VALID' ]; then
  emit_static HOOK_INTERNAL_ERROR
  exit 0
fi

# Mark delivery before cat so a stdout failure cannot concatenate fallback JSON.
emitted=1
if ! cat "$capture"; then
  printf '%s\n' 'EIF harness fault HOOK_EMIT_FAILURE: validated response could not be delivered' >&2
  exit 1
fi
exit "$rc"
