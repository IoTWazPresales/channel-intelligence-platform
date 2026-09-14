"""Complete N-0024 after correcting design_execution_decisions slot status.

N-0023 already complete. First complete attempt failed QUALITY_GATE because
responsive_decision.status was 'na'; engine requires applicable|not_applicable.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
PROG = REPO / ".eif/runtime/programme/program.py"
RUN = "GOV008_N0023_N0024_20260914"
ACTOR = "gov-008"
EV = ".eif/audit/GOV008_N0023_N0024_20260914/independent-rendered-review.md"
PAYLOAD_DIR = Path(__file__).resolve().parent / "payloads"
LOG = Path(__file__).resolve().parent / "complete_n0024.out"


def run(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    r = subprocess.run(
        [sys.executable, "-B", str(PROG), "--project", str(REPO), *args],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    out = (r.stdout or "") + (r.stderr or "")
    print(out.strip())
    LOG.write_text((LOG.read_text(encoding="utf-8") if LOG.exists() else "") + "\n" + out, encoding="utf-8")
    if check and r.returncode:
        raise SystemExit(r.returncode)
    return r


def node_rev(node: str) -> int:
    r = run(["--run", RUN, "--actor", ACTOR, "status", "--node", node])
    m = re.search(r'"revision":\s*(\d+)', r.stdout or "")
    if not m:
        raise SystemExit(f"no revision for {node}")
    return int(m.group(1))


def event(name: str, payload: dict, *, node: str) -> None:
    payload = dict(payload)
    payload["node"] = node
    payload["expected_revision"] = node_rev(node)
    PAYLOAD_DIR.mkdir(parents=True, exist_ok=True)
    path = PAYLOAD_DIR / f"{node}_{name.replace('.', '_')}_{payload['expected_revision']}_retry.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    run(
        [
            "--run",
            RUN,
            "--actor",
            ACTOR,
            "event",
            name,
            "--payload-file",
            str(path.relative_to(REPO)).replace("\\", "/"),
        ]
    )


def main() -> None:
    LOG.write_text("", encoding="utf-8")
    event(
        "node.quality",
        {
            "dim": "design_execution_decisions",
            "state": "pass",
            "evidence": {
                "responsive_decision": {
                    "status": "not_applicable",
                    "rationale": "Destination URLs; not a 390 named workflow this node.",
                    "evidence": EV,
                },
                "visualisation_decision": {
                    "status": "applicable",
                    "rationale": "Cover under-4w is a real filled filter chip, not a relabel.",
                    "evidence": EV,
                },
                "consequential_action_decision": {
                    "status": "applicable",
                    "rationale": "Clicks land on the named job. No nav restructure. D-0010 Option A kept.",
                    "evidence": EV,
                },
            },
        },
        node="N-0024",
    )
    event("node.status", {"to": "complete"}, node="N-0024")
    run(["--run", RUN, "--actor", ACTOR, "status", "--node", "N-0024"])


if __name__ == "__main__":
    main()
