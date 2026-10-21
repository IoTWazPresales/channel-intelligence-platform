"""Stage and commit the N-0080 / D-0079 / N-0100 ledger state. Explicit paths only."""
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
MESSAGE = """eif: record N-0080 as verified with limitations

D-0079 accepted by Warren (random token, server stores and looks up its
hash). N-0100 gains the public case-approval throttle criterion.
N-0080 at verify under RUN-20261014-N0080-VER; two proposed decisions,
two deferred findings. Operator acceptance pending.

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
