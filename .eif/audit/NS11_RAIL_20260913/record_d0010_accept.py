"""Record operator acceptance of D-0010 Option A. No IA implementation. No node complete."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
PROG = REPO / ".eif/runtime/programme/program.py"
RUN = "NS11_D0010_ACCEPT_20260913"
EVIDENCE = ".eif/audit/NS11_RAIL_20260913/D0010_OPERATOR_ACCEPTANCE.md"
STATEMENT_NOTE = (
    "ACCEPTED 2026-09-13 Option A: keep rail expansion. The two controls are not one "
    "destination set — Overview has no tabs, Data has 13 rail leaves against 4 grouped "
    "tabs with products/customers/duplicates/CST rail-only, and Funding's tabs include a "
    "substrate leaf the rail omits. Only Stock is a true duplicate, which is a Stock-level "
    "question not an IA one. No IA change implemented. Evidence: " + EVIDENCE
)


def evt(actor: str, typ: str, payload: dict) -> None:
    r = subprocess.run(
        [
            sys.executable,
            str(PROG),
            "--run",
            RUN,
            "--actor",
            actor,
            "event",
            typ,
            "--payload",
            json.dumps(payload),
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    out = ((r.stdout or "") + (r.stderr or "")).strip()
    print(out)
    if r.returncode:
        raise SystemExit(r.returncode)


def main() -> None:
    evt(
        "operator",
        "evidence.add",
        {
            "id": "EV-D0010-ACCEPT",
            "provenance": "operator-acceptance",
            "path": EVIDENCE,
            "note": STATEMENT_NOTE,
        },
    )
    evt(
        "operator",
        "decision.status",
        {"id": "D-0010", "status": "accepted"},
    )
    r = subprocess.run(
        [sys.executable, str(PROG), "status"],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    print(((r.stdout or "") + (r.stderr or "")).strip())


if __name__ == "__main__":
    main()
