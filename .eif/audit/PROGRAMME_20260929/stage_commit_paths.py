"""Stage the N-0028/N-0044/N-0035/N-0051 close. Explicit paths only."""
from __future__ import annotations

import subprocess
import sys

PATHS = [
    "apps/api/app/services/imports/merged_id_leftover_check.py",
    "apps/api/app/services/imports/dsi_apply_completion.py",
    "apps/api/app/services/imports/shipment_apply_sync.py",
    "apps/api/tests/test_merged_id_leftover_check.py",
    "apps/web/src/features/overview/startWork.ts",
    "apps/web/src/features/overview/startWork.test.ts",
    "apps/web/src/features/overview/StartWorkLaunch.test.tsx",
    "docs/BACKLOG.md",
    "docs/memory/CURRENT.md",
    "CONTEXT.md",
    ".eif/audit/PROGRAMME_20260929",
    ".eif/CURRENT.md",
    ".eif/PROGRAM.md",
    ".eif/ROADMAP.md",
    ".eif/WORK_ITEM.md",
    ".eif/program/PROGRAM.yaml",
    ".eif/program/PROGRAM_LOG.ndjson",
]


def main() -> None:
    subprocess.check_call(["git", "add", "--", *PATHS])


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as exc:
        sys.exit(exc.returncode)
