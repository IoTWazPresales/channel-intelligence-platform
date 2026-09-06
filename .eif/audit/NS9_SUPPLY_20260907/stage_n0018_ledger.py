"""Stage N-0018 ledger paths (explicit; never -A)."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
PATHS = [
    ".eif/program/PROGRAM.yaml",
    ".eif/program/PROGRAM_LOG.ndjson",
    ".eif/audit/NS9_SUPPLY_20260907/charter_n0018.py",
    ".eif/audit/NS9_SUPPLY_20260907/resume_n0018_baseline.py",
    ".eif/audit/NS9_SUPPLY_20260907/stage_n0018_ledger.py",
]


def main() -> None:
    cmd = ["git", "add", "--", *PATHS]
    r = subprocess.run(cmd, cwd=REPO)
    if r.returncode:
        raise SystemExit(r.returncode)
    subprocess.run(["git", "status", "-sb"], cwd=REPO, check=False)


if __name__ == "__main__":
    main()
