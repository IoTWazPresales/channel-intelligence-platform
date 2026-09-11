"""Commit staged N-0018 validate paths. Does not add files."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
MSG = """supply: N-0018 validate empty states and NUMBER RULE remeasure

Hub loading/unavailable states, focused vitest, cip grains as of 2026-09-12, browser journey. Independent GOV-008 not recorded.
"""


def main() -> None:
    r = subprocess.run(["git", "commit", "-m", MSG], cwd=REPO)
    raise SystemExit(r.returncode)


if __name__ == "__main__":
    main()
