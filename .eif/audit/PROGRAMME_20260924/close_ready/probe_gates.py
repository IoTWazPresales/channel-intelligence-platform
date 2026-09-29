"""Probe whether shipped nodes can complete, and print the gate that refuses."""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
PROG = REPO / ".eif/runtime/programme/program.py"
RUN = "CLOSE_SEQ_20260929"
ACTOR = "close-seq"
HERE = Path(__file__).resolve().parent


def run(args: list[str]) -> tuple[int, str]:
    r = subprocess.run(
        [sys.executable, "-B", str(PROG), "--project", str(REPO), *args],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    return r.returncode, ((r.stdout or "") + (r.stderr or "")).strip()


def node(nid: str) -> dict:
    code, text = run(["--run", RUN, "--actor", ACTOR, "status", "--node", nid])
    if code:
        raise SystemExit(text)
    return json.loads(text[text.rfind("\n{") + 1 :])


def rev(nid: str) -> int:
    return int(node(nid)["revision"])


def event(nid: str, name: str, payload: dict) -> tuple[int, str]:
    payload = dict(payload)
    payload["node"] = nid
    payload["expected_revision"] = rev(nid)
    path = HERE / f"probe_{nid}_{name.replace('.', '_')}.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    rel = str(path.relative_to(REPO)).replace("\\", "/")
    return run(["--run", RUN, "--actor", ACTOR, "event", name, "--payload-file", rel])


def main() -> None:
    for nid in ("N-0053", "N-0035", "N-0044", "N-0049", "N-0028"):
        n = node(nid)
        q = n.get("quality") or {}
        interesting = {}
        for dim, rec in q.items():
            if rec.get("state") in {"fail", "na", "pending"} or dim in {"content", "a11y", "testing", "observability"}:
                interesting[dim] = {
                    "state": rec.get("state"),
                    "required": rec.get("required"),
                    "rationale": rec.get("rationale"),
                    "pass_run": rec.get("pass_run"),
                }
        ver = {
            k: {"state": (v or {}).get("state"), "pass_run": (v or {}).get("pass_run")}
            for k, v in (n.get("verification") or {}).items()
        }
        print(f"--- {nid} impl={n.get('implementation_run')} stage={n.get('stage')} accept={n.get('acceptance_state')}")
        print("quality", json.dumps(interesting))
        print("verification", json.dumps(ver))

    code, text = event("N-0053", "node.lease.acquire", {"ttl_seconds": 7200})
    print("LEASE", code, text[-500:])
    code, text = event("N-0053", "node.status", {"to": "complete"})
    print("COMPLETE", code)
    # reason line only
    for line in text.splitlines():
        if "QUALITY" in line or "GATE" in line or "JOURNEY" in line or "Error" in line or "ProgramError" in line or "reason" in line.lower():
            print(line)
    if code:
        print(text[-800:])
        event("N-0053", "node.lease.release", {})


if __name__ == "__main__":
    main()
