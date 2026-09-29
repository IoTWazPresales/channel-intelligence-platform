"""Print a one-line summary of every non-complete node. Read-only."""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
PROG = REPO / ".eif/runtime/programme/program.py"
OPEN = [
    "N-0028", "N-0034", "N-0035", "N-0036", "N-0041", "N-0042", "N-0043", "N-0044",
    "N-0045", "N-0046", "N-0049", "N-0051", "N-0052", "N-0053", "N-0054", "N-0055",
    "N-0056", "N-0057", "N-0058", "N-0059", "N-0060", "N-0061", "N-0062", "N-0063",
    "N-0064", "N-0065", "N-0066", "N-0067", "N-0068", "N-0069", "N-0070", "N-0071",
    "N-0072",
]


def status(node: str) -> dict:
    r = subprocess.run(
        [sys.executable, "-B", str(PROG), "--project", str(REPO), "status", "--node", node],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    text = (r.stdout or "") + (r.stderr or "")
    start = text.find("{")
    if start < 0:
        raise SystemExit(f"no json for {node}: {text[:400]}")
    # status prints a header then the node object; take the last JSON object
    blob = text[text.rfind("\n{") + 1 :]
    return json.loads(blob)


def main() -> None:
    for node in OPEN:
        n = status(node)
        q = n.get("quality") or {}
        qsum = ",".join(
            f"{dim}:{info.get('state')}" for dim, info in q.items() if isinstance(info, dict)
        )
        v = n.get("verification") or {}
        vsum = ",".join(
            f"{k}:{info.get('state')}" for k, info in v.items() if isinstance(info, dict)
        )
        blockers = n.get("blockers") or []
        bsum = "; ".join(
            f"{b.get('type')}:{b.get('status')}:{(b.get('note') or b.get('ref') or '')[:80]}"
            for b in blockers
            if isinstance(b, dict)
        )
        note = (n.get("stage_note") or "").replace("\n", " ")[:160]
        print(
            f"{n['id']}\t{n.get('status')}\tstage={n.get('stage')}\trisk={n.get('risk')}\t"
            f"rev={n.get('revision')}\taccept={n.get('acceptance')}/{n.get('acceptance_state')}\t"
            f"q=[{qsum}]\tv=[{vsum}]\tblock=[{bsum}]\t{n.get('title')}\tNOTE:{note}"
        )


if __name__ == "__main__":
    main()
