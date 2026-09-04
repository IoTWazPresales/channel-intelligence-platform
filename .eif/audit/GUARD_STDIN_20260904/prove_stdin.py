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
    results["held_open_complete_json"] = run_guard(
        payload=allow_payload, close_stdin=False, watchdog="2", hang_s=12
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

    hung = results["hung_open_watchdog2"]
    parsed_hung = hung.get("stdout_parsed")
    if parsed_hung is None and hung.get("stdout"):
        try:
            parsed_hung = json.loads(str(hung.get("stdout")).strip().splitlines()[0])
        except Exception:
            parsed_hung = None
    reason_hung = parsed_hung.get("reason_code") if isinstance(parsed_hung, dict) else None
    complete_held = results["held_open_complete_json"]
    parsed_complete = complete_held.get("stdout_parsed")
    print("=== VERDICT ===", flush=True)
    print(
        json.dumps(
            {
                "hypothesis_hung_read_unprotected": hung.get("case") == "hung_open_pipe"
                and reason_hung != "HOOK_TIMEOUT",
                "hung_elapsed_s": hung.get("elapsed_s"),
                "hung_reason_code": reason_hung,
                "complete_json_held_open_elapsed_s": complete_held.get("elapsed_s"),
                "complete_json_held_open_permission": (
                    parsed_complete.get("permission")
                    if isinstance(parsed_complete, dict)
                    else None
                ),
                "allow_elapsed_s": results["closed_allow"].get("elapsed_s"),
                "allow_permission": (results["closed_allow"].get("stdout_parsed") or {}).get(
                    "permission"
                )
                if isinstance(results["closed_allow"].get("stdout_parsed"), dict)
                else None,
                "deny_reason_code": (results["closed_deny_force"].get("stdout_parsed") or {}).get(
                    "reason_code"
                )
                if isinstance(results["closed_deny_force"].get("stdout_parsed"), dict)
                else None,
                "read_permission": (results["closed_read"].get("stdout_parsed") or {}).get(
                    "permission"
                )
                if isinstance(results["closed_read"].get("stdout_parsed"), dict)
                else None,
            },
            indent=2,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
