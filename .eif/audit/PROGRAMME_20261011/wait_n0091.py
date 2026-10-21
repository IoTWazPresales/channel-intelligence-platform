"""Wait until the N-0091 closer finishes. Read-only."""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CLI = [sys.executable, str(ROOT / ".eif/runtime/programme/program.py"), "status", "--node", "N-0091"]


def main() -> None:
    for _ in range(30):
        result = subprocess.run(CLI, capture_output=True, text=True, cwd=ROOT)
        text = result.stdout
        if '"id": "N-0091"' in text and '"status": "complete"' in text:
            print("n0091_complete")
            return
        if result.returncode != 0:
            print("status_fail", (result.stderr or "")[-200:])
        else:
            pos = text.rfind('"stage":')
            print("waiting", text[pos: pos + 40].replace("\n", " ") if pos >= 0 else "nostage")
        time.sleep(15)
    raise SystemExit("n0091_not_complete")


if __name__ == "__main__":
    main()
