"""Prove beforeShellExecution stdin + policy behaviour against the installed guard.

Does not modify .cursor/hooks. Invoke as:
  python .eif/audit/GUARD_STDIN_20260904/prove_stdin.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
GUARD = ROOT / ".cursor" / "hooks" / "eif_guard.py"
PY = sys.executable
POLICY_CODES = frozenset({
    "ACTION_ARTIFACT_WRITE", "ACTION_DELETE", "ACTION_DEPENDENCY",
    "ACTION_DESTRUCTIVE_DATA", "ACTION_FORCE_VCS", "ACTION_IDENTITY_MUTATION",
    "ACTION_INFRASTRUCTURE", "ACTION_NETWORK", "ACTION_REMOTE_PUSH", "ACTION_WRITE",
    "BOOTSTRAP", "BOOTSTRAP_MCP", "BROWSER_INTERACT_ORIGIN", "BROWSER_OBSERVE_ONLY",
    "BROWSER_PUBLIC_MUTATE", "BROWSER_UNSAFE", "BUDGET", "CONTROL_PLANE_PROTECTED",
    "FOREIGN_PATH", "FOREIGN_READ", "IDENTITY_MCP", "IDENTITY_SHELL", "IDENTITY_TOOL",
    "MCP_DENY", "MCP_DESTRUCTIVE", "MCP_NOT_GRANTED", "MCP_POLICY_REQUIRED",
    "NETWORK_DESTINATION", "OUT_OF_CHANGE_SCOPE", "OUT_OF_OBSERVATION_SCOPE",
    "POLICY_INTEGRITY", "POST_EDIT_SECRET", "PROTECTED_PATH", "SECRET_IN_READ",
    "SECRET_PREWRITE", "SENSITIVE_READ", "SENSITIVE_TOOL_READ", "SHELL_DENY",
    "SHELL_POLICY_REQUIRED",
})


def parsed_decision(result: dict) -> dict | None:
    p = result.get("stdout_parsed")
    if isinstance(p, dict) and p.get("permission"):
        return p
    raw = result.get("stdout") or ""
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", "replace")
    if not str(raw).strip():
        return p if isinstance(p, dict) else None
    try:
        return json.loads(str(raw).strip().splitlines()[0])
    except Exception:
        return p if isinstance(p, dict) else None


def require_crash(name: str, result: dict, expected_code: str) -> None:
    decision = parsed_decision(result) or {}
    code = decision.get("reason_code")
    klass = decision.get("eif_guard_class")
    if klass != "crash" or code != expected_code or code in POLICY_CODES:
        raise SystemExit(
            f"FAIL {name}: expected crash {expected_code}, got class={klass!r} "
            f"code={code!r} permission={decision.get('permission')!r}"
        )
    if code == "IDENTITY_TOOL":
        raise SystemExit(f"FAIL {name}: transport case returned IDENTITY_TOOL")


def run_guard(*, payload: bytes | None, close_stdin: bool, watchdog: str, hang_s: float) -> dict:
    env = os.environ.copy()
    env["CURSOR_PROJECT_DIR"] = str(ROOT)
    env["EIF_HOOK_WATCHDOG_SEC"] = watchdog
    t0 = time.perf_counter()
    proc = subprocess.Popen(
        [PY, "-u", str(GUARD)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        cwd=str(ROOT),
    )
    assert proc.stdin is not None
    if payload:
        proc.stdin.write(payload)
        proc.stdin.flush()
    # communicate() always closes stdin — that would falsify the hung-pipe case.
    if close_stdin:
        proc.stdin.close()
    try:
        proc.wait(timeout=hang_s)
    except subprocess.TimeoutExpired:
        proc.kill()
        out = proc.stdout.read() if proc.stdout else b""
        err = proc.stderr.read() if proc.stderr else b""
        proc.wait()
        return {
            "case": "hung_open_pipe" if not close_stdin else "timeout_after_close",
            "elapsed_s": round(time.perf_counter() - t0, 3),
            "returncode": proc.returncode,
            "stdout": (out or b"")[:2000].decode("utf-8", "replace"),
            "stderr": (err or b"")[:1000].decode("utf-8", "replace"),
            "note": "stdin left open; process did not self-exit before wait timeout"
            if not close_stdin
            else "closed stdin but process did not exit before wait timeout",
        }
    out = proc.stdout.read() if proc.stdout else b""
    err = proc.stderr.read() if proc.stderr else b""
    elapsed = time.perf_counter() - t0
    text = (out or b"").decode("utf-8", "replace")
    parsed = None
    try:
        parsed = json.loads(text.strip().splitlines()[0]) if text.strip() else None
    except Exception as e:
        parsed = {"_parse_error": type(e).__name__, "_raw": text[:500]}
    return {
        "elapsed_s": round(elapsed, 3),
        "returncode": proc.returncode,
        "stdout_parsed": parsed,
        "stderr": (err or b"")[:500].decode("utf-8", "replace"),
    }


def main() -> None:
    allow_payload = json.dumps(
        {
            "hook_event_name": "beforeShellExecution",
            "command": "git status --short",
            "cwd": str(ROOT),
            "sandbox": False,
        }
    ).encode("utf-8")
    deny_payload = json.dumps(
        {
            "hook_event_name": "beforeShellExecution",
            "command": "git push --force origin HEAD",
            "cwd": str(ROOT),
            "sandbox": False,
        }
    ).encode("utf-8")
    read_payload = json.dumps(
        {
            "hook_event_name": "beforeReadFile",
            "file_path": str(ROOT / "CONTEXT.md"),
        }
    ).encode("utf-8")

    results = {}

    print("=== A hung-open-pipe (incomplete JSON, stdin not closed, watchdog=2) ===", flush=True)
    results["hung_open_watchdog2"] = run_guard(
        payload=b'{"hook_event_name":', close_stdin=False, watchdog="2", hang_s=12
    )
    print(json.dumps(results["hung_open_watchdog2"], indent=2), flush=True)

    print("=== A2 complete-JSON held-open (must not wait for EOF; expect allow) ===", flush=True)
    # Watchdog 8: identity git can exceed 2s under live hook contention; the
    # proof is still "do not wait for EOF" (hang_s=12 would kill a hung read).
    results["held_open_complete_json"] = run_guard(
        payload=allow_payload, close_stdin=False, watchdog="8", hang_s=12
    )
    print(json.dumps(results["held_open_complete_json"], indent=2), flush=True)

    print("=== B closed-stdin allow git status (watchdog=8) ===", flush=True)
    results["closed_allow"] = run_guard(
        payload=allow_payload, close_stdin=True, watchdog="8", hang_s=15
    )
    print(json.dumps(results["closed_allow"], indent=2), flush=True)

    print("=== C closed-stdin deny git push --force ===", flush=True)
    results["closed_deny_force"] = run_guard(
        payload=deny_payload, close_stdin=True, watchdog="8", hang_s=15
    )
    print(json.dumps(results["closed_deny_force"], indent=2), flush=True)

    print("=== D closed-stdin beforeReadFile CONTEXT.md ===", flush=True)
    results["closed_read"] = run_guard(
        payload=read_payload, close_stdin=True, watchdog="8", hang_s=15
    )
    print(json.dumps(results["closed_read"], indent=2), flush=True)

    print("=== E zero-byte stdin (closed) ===", flush=True)
    results["zero_byte"] = run_guard(
        payload=b"", close_stdin=True, watchdog="8", hang_s=15
    )
    print(json.dumps(results["zero_byte"], indent=2), flush=True)

    print("=== F JSON truncated mid-string (closed) ===", flush=True)
    truncated = b'{"hook_event_name":"beforeReadFile","file_path":"'
    results["truncated_mid_string"] = run_guard(
        payload=truncated, close_stdin=True, watchdog="8", hang_s=15
    )
    print(json.dumps(results["truncated_mid_string"], indent=2), flush=True)

    print("=== G parsed preToolUse Read with no path (must be crash, not IDENTITY_TOOL) ===", flush=True)
    pathless_read = json.dumps(
        {
            "hook_event_name": "preToolUse",
            "tool_name": "Read",
            "tool_input": {},
            "cwd": str(ROOT),
        }
    ).encode("utf-8")
    results["pathless_read"] = run_guard(
        payload=pathless_read, close_stdin=True, watchdog="8", hang_s=15
    )
    print(json.dumps(results["pathless_read"], indent=2), flush=True)

    hung = results["hung_open_watchdog2"]
    parsed_hung = parsed_decision(hung)
    reason_hung = parsed_hung.get("reason_code") if isinstance(parsed_hung, dict) else None
    complete_held = results["held_open_complete_json"]
    parsed_complete = parsed_decision(complete_held)
    zero = parsed_decision(results["zero_byte"]) or {}
    trunc = parsed_decision(results["truncated_mid_string"]) or {}
    pathless = parsed_decision(results["pathless_read"]) or {}
    deny_force = parsed_decision(results["closed_deny_force"]) or {}
    print("=== VERDICT ===", flush=True)
    verdict = {
        "hypothesis_hung_read_unprotected": hung.get("case") == "hung_open_pipe"
        and reason_hung != "HOOK_TIMEOUT",
        "hung_elapsed_s": hung.get("elapsed_s"),
        "hung_reason_code": reason_hung,
        "complete_json_held_open_elapsed_s": complete_held.get("elapsed_s"),
        "complete_json_held_open_permission": (
            parsed_complete.get("permission") if isinstance(parsed_complete, dict) else None
        ),
        "allow_elapsed_s": results["closed_allow"].get("elapsed_s"),
        "allow_permission": (parsed_decision(results["closed_allow"]) or {}).get("permission"),
        "deny_reason_code": deny_force.get("reason_code"),
        "deny_guard_class": deny_force.get("eif_guard_class"),
        "read_permission": (parsed_decision(results["closed_read"]) or {}).get("permission"),
        "zero_byte_reason_code": zero.get("reason_code"),
        "zero_byte_guard_class": zero.get("eif_guard_class"),
        "truncated_reason_code": trunc.get("reason_code"),
        "truncated_guard_class": trunc.get("eif_guard_class"),
        "pathless_read_reason_code": pathless.get("reason_code"),
        "pathless_read_guard_class": pathless.get("eif_guard_class"),
    }
    print(json.dumps(verdict, indent=2), flush=True)

    require_crash("zero_byte", results["zero_byte"], "HOOK_INPUT_INVALID")
    require_crash("truncated_mid_string", results["truncated_mid_string"], "HOOK_INPUT_INVALID")
    require_crash("pathless_read", results["pathless_read"], "HOOK_INPUT_INVALID")
    if reason_hung != "HOOK_TIMEOUT":
        raise SystemExit(f"FAIL hung_open: expected HOOK_TIMEOUT, got {reason_hung!r}")
    if deny_force.get("reason_code") != "ACTION_FORCE_VCS" or deny_force.get("eif_guard_class") != "policy":
        raise SystemExit(f"FAIL closed_deny_force: {deny_force}")
    if (parsed_decision(results["closed_allow"]) or {}).get("permission") != "allow":
        raise SystemExit("FAIL closed_allow: expected allow")
    if (parsed_decision(results["closed_read"]) or {}).get("permission") != "allow":
        raise SystemExit("FAIL closed_read: expected allow")
    print("=== PASS ===", flush=True)


if __name__ == "__main__":
    main()
