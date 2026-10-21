"""Stage and commit the N-0111 repair ledger state. Explicit paths only."""
from __future__ import annotations

import subprocess
import sys

PATHS = [
    ".eif/CURRENT.md",
    ".eif/ESCALATION.md",
    ".eif/PROGRAM.md",
    ".eif/ROADMAP.md",
    ".eif/WORK_ITEM.md",
    ".eif/program/PROGRAM.yaml",
    ".eif/program/PROGRAM_LOG.ndjson",
]
MESSAGE = """eif: N-0111 repair recorded; re-verified with limitations; Warren's decisions D-0107 to D-0111

- D-0107 Date is a sale-date column; D-0108 a load that drops rows says so; D-0109 week 52 -> 1
  rolls the year; D-0110 same-invoice distributor reloads keep replaced figures; D-0111 un-merge
  Compuspeed (1152) and Syntech (4145) from OPEN_CHANNEL.
- Repair built (21ea19a5, 26ee1b93, b5a4a342, fa305ce6); 20261016_0042 clone-proved then on cip;
  cip stock positions recomputed. Item 5 (un-merge) not done: rows not traceable exactly (finding).
- Re-recorded VERIFIED_WITH_LIMITATIONS under RUN-20261016-N0111-VER2 (self-verified, not independent).
  Full API pytest on cip_test 3034 passed, 21 skipped, 0 failed; full web vitest 187 files 872 passed.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
"""


def main() -> None:
    subprocess.check_call(["git", "add", "--", *PATHS])
    subprocess.check_call(["git", "commit", "-q", "-m", MESSAGE])


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as exc:
        sys.exit(exc.returncode)
