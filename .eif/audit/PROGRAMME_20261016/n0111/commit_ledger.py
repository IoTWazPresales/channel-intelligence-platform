"""Stage and commit the N-0111 session ledger state. Explicit paths only."""
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
MESSAGE = """eif: N-0111 chartered and verified with limitations; Warren accepts N-0095 and its three decisions

- N-0111 "Sell-through and distributor history upload readiness (2 years: Amazon, Takealot,
  Pinnacle)" chartered (R3, depends on N-0110 and N-0095) with Warren's six decisions accepted;
  built, at verify, VERIFIED_WITH_LIMITATIONS (self-verified, N-0099 does the second look).
  Full API pytest on cip_test 3017 passed, 21 skipped, 0 failed; full web vitest 186 files 869 passed.
- N-0095 accepted by Warren; D-0096, D-0097, D-0098 accepted. Amazon keeper stays 299.
  Compuspeed (1152) and Syntech (4145) are not to be merged into OPEN_CHANNEL (still merged on cip).
- N-0100 criteria: the older customer-merge endpoints must require the steward role.

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
