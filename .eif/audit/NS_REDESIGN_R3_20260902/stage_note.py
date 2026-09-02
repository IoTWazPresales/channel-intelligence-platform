#!/usr/bin/env python3
"""Park a stage note on N-0013 (PowerShell mangles inline JSON quoting)."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
PROG = REPO / ".eif/runtime/programme/program.py"
RUN = "NS_REDESIGN_R3_20260902"

note = sys.argv[1] if len(sys.argv) > 1 else (
    "R3 redesign run in progress (2026-09-02): operator rejection recorded (D-0004/5/6, blocker "
    "BL-OPERATOR-REJECTION-20260902); FAULT_FINDINGS, PRODUCT_CAPABILITY_AUDIT, COMPONENT_ECOSYSTEM_AUDIT, "
    "CONCEPTS written; CONSULT executed via claude CLI (opus, separate process/model) -> CONSULT_RESPONSE.md "
    "recommends hybrid H (domains primary + composed Overview + entity context panel + palette); React design "
    "prototype under apps/web/src/design-lab + app/(design-lab) in build; rendered evidence pending."
)
import re

st = subprocess.run([sys.executable, str(PROG), "status", "--node", "N-0013"], cwd=REPO, capture_output=True, text=True)
m = re.search(r'"revision":\s*(\d+)', st.stdout or "")
if not m:
    raise SystemExit("no revision")
r = subprocess.run(
    [sys.executable, str(PROG), "--run", RUN, "--actor", "agent", "event", "node.stage_note",
     "--payload", json.dumps({"node": "N-0013", "expected_revision": int(m.group(1)), "note": note})],
    cwd=REPO, capture_output=True, text=True,
)
print((r.stdout or r.stderr).strip()[:300])
raise SystemExit(r.returncode)
