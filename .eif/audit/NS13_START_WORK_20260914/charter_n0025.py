"""Charter N-0025: Start work surface + remaining obstruct findings.

D-0010 Option A remains accepted. Do not reopen N-0013.
D-0002, N-0006, BACKLOG-181 untouched. Do not complete this node (GOV-008 later).
No writes to cip.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
PROG = REPO / ".eif/runtime/programme/program.py"
RUN = "NS13_START_WORK_20260914"
NODE = "N-0025"
ACTOR = "gov-001"
PAYLOAD_DIR = Path(__file__).resolve().parent / "payloads"

PRESERVATION = {
    "customer_account_sell_out_gap": "brief sell_out_gap grain unchanged",
    "pipeline_fill_pct": "inbound_open pipeline_fill_pct documentation unchanged",
    "response_container_badge": "unchanged this node",
    "rail_expand_state": "NAV_STORAGE_GROUP_EXPANDED localStorage contract unchanged",
    "d0010": "Option A accepted; rail expansion and LensTabs kept; Data still four grouped tabs",
    "d0002": "mapping-queue disposition untouched; steward-queue verb uses existing /admin/mappings",
    "n0006": "not reopened",
    "n0013": "not reopened",
    "backlog_181": "rail tokens untouched",
    "movement_execution_workspaces": "not unwound",
    "attention_exceptions_only": "Overview Needs attention remains blotter-only; verbs live on Start work",
}


def prog(args: list[str]) -> str:
    r = subprocess.run([sys.executable, str(PROG), *args], cwd=REPO, capture_output=True, text=True)
    out = ((r.stdout or "") + (r.stderr or "")).strip()
    print(out)
    if r.returncode:
        raise SystemExit(r.returncode)
    return out


def node_rev(nid: str = NODE) -> int:
    r = subprocess.run(
        [sys.executable, str(PROG), "status", "--node", nid],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    combined = (r.stdout or "") + (r.stderr or "")
    m = re.search(r'"revision":\s*(\d+)', combined)
    if not m:
        print(combined)
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
    prog(["status"])
    prog(["frontier"])
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
    prog(["status", "--node", NODE])
    prog(["frontier"])


if __name__ == "__main__":
    main()
