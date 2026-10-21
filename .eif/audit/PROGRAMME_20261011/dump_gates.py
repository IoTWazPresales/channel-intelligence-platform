"""Dump gate-relevant fields for nodes that may be closable."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
NODES = ["N-0065", "N-0068", "N-0086", "N-0087", "N-0092"]


def one(node: str) -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / ".eif/runtime/programme/program.py"), "status", "--node", node],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    text = result.stdout
    marker = f'"id": "{node}"'
    start = text.rfind("{", 0, text.find(marker))
    data = json.loads(text[start:])
    q = data.get("quality") or {}
    pending = [k for k, rec in q.items() if rec.get("required") and rec.get("state") not in {"pass", "resolved", "na"}]
    print("=" * 20, node, data.get("status"), data.get("stage"), data.get("risk"), "rev", data.get("revision"))
    print("impl", data.get("implementation_run"), "accept", data.get("acceptance"), data.get("acceptance_state"))
    print("facets", data.get("facets"))
    print("blockers", json.dumps(data.get("blockers"))[:500])
    print("verification", json.dumps(data.get("verification"))[:800])
    print("pending", pending)
    print("stage_note", str(data.get("stage_note") or "")[:400])
    for k, rec in q.items():
        if rec.get("required"):
            print(f"  Q {k}: {rec.get('state')}")


if __name__ == "__main__":
    for node in NODES:
        one(node)
