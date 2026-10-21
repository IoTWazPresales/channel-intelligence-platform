"""Stage and commit the N-0110 / D-0080 / D-0081 ledger state. Explicit paths only."""
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
MESSAGE = """eif: record N-0110 as verified with limitations

Warren accepted D-0080 (planner margin starts from DAP) and D-0081
(missing customer rebate / distributor margin terms count as 0, flagged,
never blocking). Warren's N-0110 decisions recorded: sales-only only when
the upload is marked; highlight is an editable setting in absolute units.
N-0110 at verify under RUN-20261014-N0110-VER; four proposed decisions,
six deferred findings. Operator acceptance pending.

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
