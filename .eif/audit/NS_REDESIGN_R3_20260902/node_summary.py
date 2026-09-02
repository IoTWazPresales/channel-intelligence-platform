#!/usr/bin/env python3
"""Print a compact view of N-0013 (quality dims, blockers, last stage notes) for this run's records."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
PROG = REPO / ".eif/runtime/programme/program.py"

st = subprocess.run([sys.executable, str(PROG), "status", "--node", "N-0013"], cwd=REPO, capture_output=True, text=True)
out = st.stdout or ""
j = json.loads(out[out.index("\n{\n") + 1 :])
print("revision", j["revision"], "status", j["status"], "stage", j["stage"], "acceptance", j["acceptance_state"])
for k, v in j["quality"].items():
    print(f"  quality {k:28s} {v['state']}")
print("keys:", ", ".join(sorted(j.keys())))
for key in ("blockers", "stage_notes", "notes", "decisions", "preservation"):
    if key in j:
        s = json.dumps(j[key], ensure_ascii=False)
        print(f"{key} ({len(s)} chars):", s[-900:])
