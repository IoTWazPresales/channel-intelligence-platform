#!/usr/bin/env python3
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
PROG = REPO / ".eif/runtime/programme/program.py"
payload = json.dumps({
    "node": "N-0013",
    "expected_revision": 25,
    "to": "ready",
    "stage_note": "Architecture package complete; awaiting operator acceptance",
})
subprocess.run(
    [sys.executable, str(PROG), "--run", "NS_RECONCILE_20260902", "--actor", "agent", "event", "node.status", "--payload", payload],
    cwd=REPO,
    check=True,
)
