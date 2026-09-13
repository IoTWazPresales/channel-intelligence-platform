"""Record D-0010 as proposed. Operator accepts or rejects; no IA implementation."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
PROG = REPO / ".eif/runtime/programme/program.py"
RUN = "NS11_RAIL_20260913"

STATEMENT = (
    "PROPOSED 2026-09-13: rail expansion vs in-page LensTabs. The two controls do not "
    "share one destination set (Data 13 rail leaves vs 4 grouped tabs; Funding/Market tabs "
    "include substrate/planned; Overview has no tabs; Planning/Admin rail hrefs point at "
    "hubs while tabs point at relocated workspaces). Recommended Option A: keep rail "
    "expansion; N-0023 ports LabShell tokens only. Option B (domains-only rail) needs a "
    "later node after hubs/Overview/Data catalogs are unified. Option C (remove matching "
    "tabs) not recommended. Collapsed-active domain: no fill, no 3px bar, primary icon + "
    "weight 600. Evidence: .eif/audit/NS11_RAIL_20260913/D0010_RAIL_VS_TABS.md. D-0002 "
    "untouched. Operator accepts A/B/C or rejects."
)


def main() -> None:
    r = subprocess.run(
        [
            sys.executable,
            str(PROG),
            "--run",
            RUN,
            "--actor",
            "gov-001",
            "event",
            "decision.add",
            "--payload",
            json.dumps(
                {
                    "id": "D-0010",
                    "scope": "N-0023",
                    "statement": STATEMENT,
                    "origin": "agent",
                    "status": "proposed",
                }
            ),
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    print(((r.stdout or "") + (r.stderr or "")).strip())
    raise SystemExit(r.returncode)


if __name__ == "__main__":
    main()
