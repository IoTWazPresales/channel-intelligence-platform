"""Wait until the N-0093 closer finishes. Read-only."""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CLI = [sys.executable, str(ROOT / ".eif/runtime/programme/program.py"), "status", "--node", "N-0093"]


def main() -> None:
    for _ in range(24):
        result = subprocess.run(CLI, capture_output=True, text=True, cwd=ROOT)
        text = result.stdout
        if '"id": "N-0093"' in text and '"status": "complete"' in text:
            print("n0093_complete")
            return
        stage = "unknown"
        key = '"stage":'
        pos = text.rfind(key)
        if pos >= 0:
            stage = text[pos: pos + 40].replace("\n", " ")
        print("waiting", stage)
        time.sleep(15)
    raise SystemExit("n0093_not_complete")


if __name__ == "__main__":
    main()
