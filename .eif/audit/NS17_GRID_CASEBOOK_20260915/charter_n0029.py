"""Charter N-0029: grid community clipboard + Case book working content first.

Cites D-0008 / N-0027 / N-0028. No GOV-008. Do not complete.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
PROG = REPO / ".eif/runtime/programme/program.py"
RUN = "NS17_GRID_CASEBOOK_20260915"
NODE = "N-0029"
ACTOR = "gov-001"
PAYLOAD_DIR = Path(__file__).resolve().parent / "payloads"

PRESERVATION = {
    "d0008": "accepted; Case book is settlement half of one cpor_case lifecycle",
    "n0027": "StewardFailureQueue grid remains a consumer of EnterpriseDataGrid",
    "n0028": "Start work cards and Lineup cases composition not reverted",
    "n0025": "GOV-008 leftovers not remediated",
    "n0026": "Create promotion plan verb not re-audited",
    "n0013": "not reopened",
    "d0002": "mapping-queue disposition untouched",
    "n0006": "not reopened",
    "d0010": "Option A untouched",
    "backlog_181": "rail tokens untouched",
    "movement_execution_workspaces": "not unwound",
    "settlement_workspace": "UNCOVERED — no lab render; not designed in this node",
}


def prog(args: list[str]) -> str:
    r = subprocess.run(
        [sys.executable, "-B", str(PROG), "--project", str(REPO), *args],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    out = ((r.stdout or "") + (r.stderr or "")).strip()
    print(out)
    if r.returncode:
        raise SystemExit(r.returncode)
    return out


def node_rev(nid: str = NODE) -> int:
    out = prog(["--run", RUN, "--actor", ACTOR, "status", "--node", nid])
    m = re.search(r'"revision":\s*(\d+)', out)
    if not m:
        raise SystemExit("no revision")
    return int(m.group(1))


def event(name: str, payload: dict) -> None:
    path = PAYLOAD_DIR / f"{name.replace('.', '_')}.json"
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    prog(
        [
            "--run",
            RUN,
            "--actor",
            ACTOR,
            "event",
            name,
            "--payload-file",
            str(path.relative_to(REPO)).replace("\\", "/"),
        ]
    )


def main() -> None:
    PAYLOAD_DIR.mkdir(parents=True, exist_ok=True)
    prog(["--run", RUN, "--actor", ACTOR, "status"])
    add_path = PAYLOAD_DIR / "node.add.json"
    prog(
        [
            "--run",
            RUN,
            "--actor",
            ACTOR,
            "event",
            "node.add",
            "--payload-file",
            str(add_path.relative_to(REPO)).replace("\\", "/"),
        ]
    )
    rev = node_rev()
    event("node.lease.acquire", {"node": NODE, "expected_revision": rev, "ttl_seconds": 14400})
    rev = node_rev()
    event(
        "node.baseline",
        {
            "node": NODE,
            "expected_revision": rev,
            "baseline_ref": "BLN-0001",
            "preservation": PRESERVATION,
        },
    )
    rev = node_rev()
    event("node.stage", {"node": NODE, "expected_revision": rev, "to": "implement"})
    prog(["--run", RUN, "--actor", ACTOR, "status", "--node", NODE])


if __name__ == "__main__":
    main()
