"""Compact node fields. No secrets."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PROGRAM = [sys.executable, str(ROOT / ".eif/runtime/programme/program.py"), "status", "--node"]


def load(node_id: str) -> dict:
    result = subprocess.run(PROGRAM + [node_id], capture_output=True, text=True, cwd=ROOT)
    if result.returncode != 0:
        raise SystemExit(result.stderr or result.stdout)
    text = result.stdout
    start = text.rfind("{", 0, text.find(f'"id": "{node_id}"'))
    return json.loads(text[start:])


def main() -> None:
    lines: list[str] = []

    def say(message: str) -> None:
        lines.append(message)
        print(message, flush=True)

    for node_id in ("N-0078", "N-0079", "N-0086"):
        node = load(node_id)
        say(f"--- {node_id}")
        say(f"status {node.get('status')} stage {node.get('stage')} rev {node.get('revision')}")
        say(
            f"risk {node.get('risk')} class {node.get('class')} acceptance {node.get('acceptance')} {node.get('acceptance_state')}"
        )
        say("facets " + ",".join(node.get("facets") or []))
        say(f"lease {node.get('lease') is not None}")
        for criterion in node.get("acceptance_criteria") or []:
            say(f"criterion {criterion}")
        for dim, rec in (node.get("quality") or {}).items():
            if rec.get("required"):
                say(f"quality {dim} {rec.get('state')}")
        for blocker in node.get("blockers") or []:
            say(f"blocker {blocker.get('id')} {blocker.get('type')}")
    out = ROOT / ".eif" / "audit" / "PROGRAMME_20261011" / "n0078_node_dump.txt"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
