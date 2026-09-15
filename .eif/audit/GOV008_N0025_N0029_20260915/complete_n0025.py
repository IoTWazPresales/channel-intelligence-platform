"""Fix N-0025 identity tokens and retry complete.

QUALITY_GATE: design_identity_tokens evidence.tokens.direction_name must be declared.
This run overwrote the prior GOV-008 tokens map with verdict/node only.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
PROG = REPO / ".eif/runtime/programme/program.py"
RUN = "GOV008_N0025_N0029_20260915"
ACTOR = "gov-008"
EV = ".eif/audit/GOV008_N0025_N0029_20260915/independent-rendered-review.md"
PAYLOAD_DIR = Path(__file__).resolve().parent / "payloads"
NODE = "N-0025"


def run(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    r = subprocess.run(
        [sys.executable, "-B", str(PROG), "--project", str(REPO), *args],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    out = (r.stdout or "") + (r.stderr or "")
    print(out.strip())
    if check and r.returncode:
        print(f"FAILED rc={r.returncode} args={args}", file=sys.stderr)
        raise SystemExit(r.returncode)
    return r


def node_rev() -> int:
    r = run(["--run", RUN, "--actor", ACTOR, "status", "--node", NODE])
    m = re.search(r'"revision":\s*(\d+)', r.stdout or "")
    if not m:
        raise SystemExit("no revision")
    return int(m.group(1))


def event(name: str, payload: dict, *, check: bool = True) -> subprocess.CompletedProcess[str]:
    payload = dict(payload)
    payload["node"] = NODE
    payload["expected_revision"] = node_rev()
    PAYLOAD_DIR.mkdir(parents=True, exist_ok=True)
    seq = payload["expected_revision"]
    path = PAYLOAD_DIR / f"{NODE}_{name.replace('.', '_')}_{seq}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    rel = str(path.relative_to(REPO)).replace("\\", "/")
    return run(
        ["--run", RUN, "--actor", ACTOR, "event", name, "--payload-file", rel],
        check=check,
    )


def main() -> None:
    event("node.lease.reclaim", {"ttl_seconds": 14400})
    event(
        "node.quality",
        {
            "dim": "design_identity_tokens",
            "state": "pass",
            "evidence": {
                "tokens": {
                    "direction_name": "start work from overview",
                    "attention": "exceptions only",
                    "verdict": "VERIFIED_WITH_LIMITATIONS",
                    "node": NODE,
                },
                "path": EV,
            },
        },
    )
    r = event("node.status", {"to": "complete"}, check=False)
    if r.returncode:
        print("N-0025 complete still refused", file=sys.stderr)
        event(
            "node.lease.release",
            {
                "stage_note": (
                    "GOV-008 VERIFIED_WITH_LIMITATIONS. Identity tokens restored. "
                    "Complete refused. Do not complete."
                )
            },
        )
        raise SystemExit(r.returncode)
    run(["--run", RUN, "--actor", ACTOR, "status", "--node", NODE])


if __name__ == "__main__":
    main()
