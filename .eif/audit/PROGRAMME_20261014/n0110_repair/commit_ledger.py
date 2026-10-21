"""Stage, commit and push the N-0110 repair ledger state. Explicit paths only."""
from __future__ import annotations

import subprocess
import sys

PATHS = [
    ".eif/CURRENT.md",
    ".eif/ESCALATION.md",
    ".eif/PROGRAM.md",
    ".eif/ROADMAP.md",
    ".eif/program/PROGRAM.yaml",
    ".eif/program/PROGRAM_LOG.ndjson",
]
MESSAGE = """eif: re-record N-0110 as verified with limitations after repair

Warren accepted D-0084..D-0087 (week bucket without a calendar, gap per
customer and product across sites, 1-unit highlight, day grain from flat
files). Repair under RUN-20261014-N0110-REPAIR, verified under
RUN-20261015-N0110-VER2. Cause counts on cip: 243 flagged of 314
compared; overwrite 8, unmatched shipment 0, no POD 0, no prior on-hand
29, repeated report 108, unreported weeks 58, unexplained 40. D-0088
(supersede by identical file) and D-0089 (two added causes) proposed;
D-0089 is a decision blocker for Warren. Five deferred findings.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
"""


def main() -> None:
    subprocess.check_call(["git", "add", "--", *PATHS])
    subprocess.check_call(["git", "commit", "-q", "-m", MESSAGE])
    subprocess.check_call(["git", "push", "-q", "origin", "feat/ns-2-brief-nav-collapse"])
    subprocess.check_call(["git", "log", "--oneline", "-1"])


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as exc:
        sys.exit(exc.returncode)
