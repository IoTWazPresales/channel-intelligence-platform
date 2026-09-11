"""Explicit-path git add for N-0018 validate (never -A)."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
PATHS = [
    "apps/web/src/features/supply-inbound/SupplyOverview.tsx",
    "apps/web/src/features/supply-inbound/SupplyChrome.tsx",
    "apps/web/src/features/supply-inbound/SupplyOverview.test.tsx",
    "docs/design/N0018_SUPPLY_INBOUND_COVERAGE.md",
    "docs/memory/CURRENT.md",
    "CONTEXT.md",
    ".eif/audit/NS9_SUPPLY_20260907/RESULTS.md",
    ".eif/audit/NS9_SUPPLY_20260907/number_rule.py",
    ".eif/audit/NS9_SUPPLY_20260907/browser_1280.cjs",
    ".eif/audit/NS9_SUPPLY_20260907/lease_acquire.json",
    ".eif/audit/NS9_SUPPLY_20260907/evidence_validate.json",
    ".eif/audit/NS9_SUPPLY_20260907/stage_validate.json",
    ".eif/audit/NS9_SUPPLY_20260907/stage_validate_git.py",
    ".eif/program/PROGRAM.yaml",
    ".eif/program/PROGRAM_LOG.ndjson",
    ".eif/CURRENT.md",
    ".eif/WORK_ITEM.md",
    ".eif/PROGRAM.md",
    ".eif/ROADMAP.md",
    ".eif/runs/NS9_SUPPLY_20260907/RUN_LOG.ndjson",
]


def main() -> None:
    cmd = ["git", "add", "--", *PATHS]
    r = subprocess.run(cmd, cwd=REPO)
    if r.returncode:
        raise SystemExit(r.returncode)
    subprocess.run(["git", "status", "-sb", "--", *PATHS], cwd=REPO, check=False)


if __name__ == "__main__":
    main()
