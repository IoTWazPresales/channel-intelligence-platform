"""Write generated programme views after N-0028 ledger events."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
PROG = REPO / ".eif/runtime/programme/program.py"
RUN = "NS16_START_LINEUP_20260915"
ACTOR = "gov-001"

r = subprocess.run(
    [sys.executable, "-B", str(PROG), "--project", str(REPO), "--run", RUN, "--actor", ACTOR, "views"],
    cwd=REPO,
    capture_output=True,
    text=True,
)
print((r.stdout or "") + (r.stderr or ""))
raise SystemExit(r.returncode)
