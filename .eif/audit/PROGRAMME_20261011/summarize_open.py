"""Print a one-line summary for built-but-open candidates. One status call each."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
NODES = [
    "N-0065",
    "N-0068",
    "N-0075",
    "N-0078",
    "N-0079",
    "N-0086",
    "N-0087",
    "N-0092",
    "N-0109",
]


def one(node: str) -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / ".eif/runtime/programme/program.py"), "status", "--node", node],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    if result.returncode != 0:
        print(node, "ERROR", (result.stderr or result.stdout)[-300:])
        return
    text = result.stdout
    marker = f'"id": "{node}"'
    start = text.find(marker)
    start = text.rfind("{", 0, start)
    data = json.loads(text[start:])
    ac = data.get("acceptance_criteria") or []
    if isinstance(ac, str):
        ac_text = ac
    else:
        ac_text = " | ".join(str(x) for x in ac)
    title = str(data.get("title") or data.get("name") or "")[:80]
    print(
        "\t".join(
            [
                node,
                str(data.get("status")),
                str(data.get("stage")),
                str(data.get("class")),
                "R" + str(data.get("risk")),
                "rev" + str(data.get("revision")),
                "accept=" + str(data.get("acceptance_state")),
                "lease=" + ("yes" if data.get("lease") else "no"),
                title,
            ]
        )
    )
    print("  AC:", ac_text[:400].replace("\n", " "))


if __name__ == "__main__":
    for node in NODES:
        one(node)
