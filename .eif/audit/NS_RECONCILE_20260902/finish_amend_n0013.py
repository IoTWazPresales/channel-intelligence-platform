#!/usr/bin/env python3
"""Finalize N-0013 amended package: r2 quality refs + ready status."""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
PROG = REPO / ".eif/runtime/programme/program.py"
AUDIT = ".eif/audit/NS_RECONCILE_20260902"
RUN = "NS_RECONCILE_AMEND_FINISH_20260902"
N13 = "N-0013"


def evt(run: str, actor: str, typ: str, payload: dict) -> None:
    r = subprocess.run(
        [sys.executable, str(PROG), "--run", run, "--actor", actor, "event", typ, "--payload", json.dumps(payload)],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    print(f"{typ} -> {(r.stdout or r.stderr).strip()}")
    if r.returncode:
        raise SystemExit(r.returncode)


def rev(nid: str) -> int:
    r = subprocess.run([sys.executable, str(PROG), "status", "--node", nid], cwd=REPO, capture_output=True, text=True)
    m = re.search(r'"revision":\s*(\d+)', r.stdout or "")
    if not m:
        raise SystemExit(f"no revision for {nid}")
    return int(m.group(1))


def main() -> None:
    updates = [
        (
            "design_artifact_class",
            {
                "class": "high_fidelity",
                "path": f"{AUDIT}/rendered-verification-r2.md",
                "gallery": f"{AUDIT}/index.html",
                "r1_superseded": f"{AUDIT}/rendered-verification.md",
            },
        ),
        (
            "a11y",
            {
                "path": f"{AUDIT}/independent-rendered-review-r2.md",
                "summary": "r2: focus-visible in cip-base.css; contrast pass; trap deferred to implementation",
                "r1_superseded": f"{AUDIT}/independent-rendered-review.md",
            },
        ),
        (
            "design_interaction_spec",
            {
                "interactions": [
                    "spine_count_badges",
                    "utility_sub_links",
                    "brief_signal_deep_links",
                    "position_lens_switcher",
                    "mobile_drawer_spine",
                ]
            },
        ),
        (
            "design_state_coverage",
            {
                "states": [
                    "populated_brief",
                    "populated_position",
                    "mobile_nav",
                    "utility_hubs",
                ]
            },
        ),
    ]

    for dim, evidence in updates:
        r = rev(N13)
        evt(RUN, "agent", "node.quality", {
            "node": N13,
            "expected_revision": r,
            "dim": dim,
            "state": "pass",
            "evidence": evidence,
        })

    r = rev(N13)
    evt(RUN, "agent", "node.status", {
        "node": N13,
        "expected_revision": r,
        "to": "ready",
        "stage_note": "Amended r2 package; D-0001+D-0002+D-0003 pending operator; no Phase A",
    })
    print("DONE finish amend N-0013")


if __name__ == "__main__":
    main()
