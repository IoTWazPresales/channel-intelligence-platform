"""Lease and stage N-0017 implement. Recording run is the implementer for this node."""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
PROG = REPO / ".eif/runtime/programme/program.py"
RUN = "NS7_EXEC_20260906"


def prog(args: list[str]) -> str:
    r = subprocess.run([sys.executable, str(PROG), *args], cwd=REPO, capture_output=True, text=True)
    out = (r.stdout or r.stderr).strip()
    print(out)
    if r.returncode:
        raise SystemExit(r.returncode)
    return out


def node_rev(nid: str) -> int:
    r = subprocess.run(
        [sys.executable, str(PROG), "status", "--node", nid],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    m = re.search(r'"revision":\s*(\d+)', r.stdout or "")
    if not m:
        raise SystemExit("no revision")
    return int(m.group(1))


def main() -> None:
    rev = node_rev("N-0017")
    prog(
        [
            "--run",
            RUN,
            "--actor",
            "gov-001",
            "event",
            "node.lease.acquire",
            "--payload",
            json.dumps({"node": "N-0017", "expected_revision": rev}),
        ]
    )
    rev = node_rev("N-0017")
    prog(
        [
            "--run",
            RUN,
            "--actor",
            "gov-001",
            "event",
            "node.stage",
            "--payload",
            json.dumps({"node": "N-0017", "expected_revision": rev, "to": "implement"}),
        ]
    )


if __name__ == "__main__":
    main()
