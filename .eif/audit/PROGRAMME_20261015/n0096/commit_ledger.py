"""Stage and commit the N-0096 session ledger state. Explicit paths only."""
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
MESSAGE = """eif: record D-0093 accepted, N-0096 in progress, Takealot findings on N-0110

D-0093 (FX date = approval date) accepted by Warren; D-0094 superseded as a duplicate;
D-0095 records the Takealot one-week fact; BL-N0110-ONHAND and BL-N0083-CASEDATE closed.
N-0096 is in progress and NOT closed: the final full web vitest run did not complete.
Two Part B findings added to N-0110.

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
"""


def main() -> None:
    subprocess.check_call(["git", "add", "--", *PATHS])
    subprocess.check_call(["git", "commit", "-q", "-m", MESSAGE])


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as exc:
        sys.exit(exc.returncode)
