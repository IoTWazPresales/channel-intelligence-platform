#!/usr/bin/env python3
"""Amend N-0013 after operator challenge — r2 evidence, split decisions."""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
PROG = REPO / ".eif/runtime/programme/program.py"
AUDIT = ".eif/audit/NS_RECONCILE_20260902"
PROP = "docs/design/CIP_PLATFORM_ARCHITECTURE_PROPOSAL.md"
RUN = "NS_RECONCILE_AMEND_20260902"
INDEP = "NS_RECONCILE_INDEPENDENT_R2_20260902"
N13 = "N-0013"


def evt(run: str, actor: str, typ: str, payload: dict) -> None:
    r = subprocess.run(
        [sys.executable, str(PROG), "--run", run, "--actor", actor, "event", typ, "--payload", json.dumps(payload)],
        cwd=REPO, capture_output=True, text=True,
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
    evt(RUN, "agent", "decision.add", {
        "id": "D-0001",
        "scope": N13,
        "statement": "Adopt amended IA: Brief·Plan·Position·Settlement·Actions·Imports + Reports·Admin utilities (r2 evidence)",
        "origin": "eif",
        "status": "proposed",
    })
    for did, stmt in [
        ("D-0002", "Mapping queue UI: RESTORE under Imports (recommended) vs RETIRE UI — operator choice"),
        ("D-0003", "KPI analytical capability vs Brief landing: Dashboards under Reports (recommended) vs Brief strip vs secondary /dashboard"),
    ]:
        evt(RUN, "agent", "decision.add", {"id": did, "scope": N13, "statement": stmt, "origin": "eif", "status": "proposed"})

    r = rev(N13)
    evt(RUN, "agent", "node.lease.acquire", {"node": N13, "expected_revision": r})

    r = rev(N13)
    evt(RUN, "agent", "node.patch", {
        "node": N13,
        "expected_revision": r,
        "acceptance_criteria": [
            "target_artifact_class: high_fidelity",
            f"Amended architecture in {PROP}",
            "r2 rendered evidence — mobile 390px honestly verified",
            "Utility hubs demonstrated for Reports and Admin",
            "D-0001 amended core IA; D-0002 mapping queue; D-0003 KPI vs Brief — operator records all three",
        ],
    })

    rendered_ev = {
        "path": f"{AUDIT}/rendered-verification-r2.md",
        "gallery": f"{AUDIT}/index.html",
        "viewports": ["desktop_1280", "mobile_390"],
        "r1_superseded": f"{AUDIT}/rendered-verification.md",
        "amendment": "2026-09-02 mobile CSS correction + utility mockups",
    }
    indep_ev = {
        "path": f"{AUDIT}/independent-rendered-review-r2.md",
        "r1_superseded": f"{AUDIT}/independent-rendered-review.md",
        "r1_failure": "mobile_pass_unsupported; focus_visible_claim_false",
        "eif_defect": "none — reviewer execution failure",
        "comparison_verdict": "amended_pass",
    }

    for dim, evidence in [
        ("rendered_comparison", {**indep_ev, "artifact_class": "high_fidelity"}),
        ("design_sameness_review", {
            "path": f"{AUDIT}/independent-rendered-review-r2.md",
            "decision": "amended_pass",
            "r1_withdrawn": True,
            "visual_vocabulary_challenge": "Channel→Position (product name collision); Data→Imports (job clarity)",
        }),
        ("rendered", rendered_ev),
        ("content", {"path": PROP, "summary": "Brief·Plan·Position·Settlement·Actions·Imports; Reports Build/Dashboards/Inbox; Admin Access/Settings/Ops/Trust"}),
        ("design_divergence", {
            "benchmark": f"{AUDIT}/rendered-verification.md",
            "decision": "amendment_r2",
            "rationale": "r1 mobile PASS withdrawn; naming and utility evidence strengthened",
        }),
    ]:
        r = rev(N13)
        evt(RUN, "agent", "node.quality", {
            "node": N13, "expected_revision": r, "dim": dim, "state": "pass", "evidence": evidence,
        })

    r = rev(N13)
    evt(RUN, "agent", "node.verification", {
        "node": N13, "expected_revision": r, "kind": "rendered", "state": "pass", "evidence": rendered_ev,
    })

    r = rev(N13)
    evt(RUN, "agent", "node.status", {
        "node": N13, "expected_revision": r, "to": "ready",
        "stage_note": "Amended package r2; D-0001+D-0002+D-0003 pending operator; no Phase A",
    })

    r = rev(N13)
    evt(RUN, "agent", "node.lease.release", {"node": N13, "expected_revision": r})

    r = rev(N13)
    evt(INDEP, "gov-008", "node.lease.acquire", {"node": N13, "expected_revision": r})
    r = rev(N13)
    evt(INDEP, "gov-008", "node.verification", {
        "node": N13, "expected_revision": r, "kind": "referent", "state": "pass",
        "evidence": {"path": f"{AUDIT}/independent-rendered-review-r2.md", "method": "r2_independent_amendment_review"},
    })
    r = rev(N13)
    evt(INDEP, "gov-008", "node.lease.release", {"node": N13, "expected_revision": r})

    print("DONE amend N-0013")


if __name__ == "__main__":
    main()
