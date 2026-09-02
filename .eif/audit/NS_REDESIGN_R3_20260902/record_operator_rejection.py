#!/usr/bin/env python3
"""Record the 2026-09-02 operator rejection of the N-0013 r2 design package.

Historical events are preserved. This script appends supersession events so the
r1/r2 PASS records can no longer satisfy the current N-0013 approval state.

Effective state after this script:
- D-0001 and D-0003: superseded by operator decisions D-0004 / D-0005 that record
  the rejection (the runtime has no 'rejected' decision status — see FAULT_FINDINGS.md E-3).
- D-0002: remains 'proposed'; deferral recorded in D-0006 (operator, accepted).
- N-0013 quality dims that were passed against the rejected artifacts -> 'pending'
  with supersession evidence; verification.rendered / referent -> 'pending'.
- N-0013 blocked on operator decision BL-OPERATOR-REJECTION-20260902.
- Acceptance criteria replaced: React design prototype in the real repo is the artifact class.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
PROG = REPO / ".eif/runtime/programme/program.py"
AUDIT = ".eif/audit/NS_REDESIGN_R3_20260902"
RUN = "NS_REDESIGN_R3_REJECTION_20260902"
N13 = "N-0013"
REJECTED_EVIDENCE = [
    ".eif/audit/NS_RECONCILE_20260902/rendered-verification.md",
    ".eif/audit/NS_RECONCILE_20260902/rendered-verification-r2.md",
    ".eif/audit/NS_RECONCILE_20260902/independent-rendered-review.md",
    ".eif/audit/NS_RECONCILE_20260902/independent-rendered-review-r2.md",
    ".eif/audit/NS_RECONCILE_20260902/index.html",
    "docs/design/CIP_PLATFORM_ARCHITECTURE_PROPOSAL.md",
]
SUPERSESSION = {
    "superseded_by_operator": True,
    "operator_decision_date": "2026-09-02",
    "rejected_package": "N-0013 amended architecture r2 (Brief·Plan·Position·Settlement·Actions·Imports)",
    "rejected_evidence": REJECTED_EVIDENCE,
    "reason": (
        "Standalone HTML/CSS artifacts recreated application UI and did not prove the real React product; "
        "insufficient information scent; sparse generic console; weak analytical visualisation; "
        "independence was actor-label only (same run, same process, same model)."
    ),
    "replacement_required": f"{AUDIT}/ — React design prototype in the real apps/web stack + rendered evidence",
}


def evt(actor: str, typ: str, payload: dict) -> None:
    r = subprocess.run(
        [sys.executable, str(PROG), "--run", RUN, "--actor", actor, "event", typ, "--payload", json.dumps(payload)],
        cwd=REPO, capture_output=True, text=True,
    )
    print(f"{typ} -> {(r.stdout or r.stderr).strip()[:200]}")
    if r.returncode:
        raise SystemExit(r.returncode)


def rev(nid: str) -> int:
    r = subprocess.run([sys.executable, str(PROG), "status", "--node", nid], cwd=REPO, capture_output=True, text=True)
    m = re.search(r'"revision":\s*(\d+)', r.stdout or "")
    if not m:
        raise SystemExit(f"no revision for {nid}")
    return int(m.group(1))


def main() -> None:
    # Operator decisions recording the rejection / deferral.
    evt("operator", "decision.add", {
        "id": "D-0004", "scope": N13, "origin": "operator", "status": "accepted", "supersedes": "D-0001",
        "statement": "REJECTED 2026-09-02: D-0001 amended IA (Brief·Plan·Position·Settlement·Actions·Imports) is not accepted. "
                     "Not a rename problem: insufficient information scent for an unfamiliar commercial operator; "
                     "architecture must be re-derived from the real product with no target container count.",
    })
    evt("operator", "decision.add", {
        "id": "D-0005", "scope": N13, "origin": "operator", "status": "accepted", "supersedes": "D-0003",
        "statement": "REJECTED 2026-09-02: D-0003 framing of Dashboards as a saved-report destination under Reports is rejected. "
                     "Dashboards are a strategically important configurable view of the business; prominence, location, "
                     "relationship to reporting/landing and configuration model must be re-derived.",
    })
    evt("operator", "decision.add", {
        "id": "D-0006", "scope": N13, "origin": "operator", "status": "accepted",
        "statement": "DEFERRED 2026-09-02: D-0002 (mapping queue UI restore vs retire) is deferred, not rejected. "
                     "Mapping/resolution capability must remain accounted for and reachable until Warren explicitly "
                     "accepts retirement/replacement after the new architecture is known.",
    })
    evt("operator", "decision.status", {"id": "D-0001", "status": "superseded"})
    evt("operator", "decision.status", {"id": "D-0003", "status": "superseded"})

    r = rev(N13)
    evt("agent", "node.lease.acquire", {"node": N13, "expected_revision": r})

    # Quality dims passed against the rejected artifacts revert to pending with supersession evidence.
    for dim in [
        "design_artifact_class", "design_divergence", "design_sameness_review", "rendered_comparison",
        "rendered", "content", "accessibility", "interaction_spec", "state_coverage",
    ]:
        r = rev(N13)
        evt("agent", "node.quality", {
            "node": N13, "expected_revision": r, "dim": dim, "state": "pending",
            "evidence": {**SUPERSESSION, "dim": dim},
            "rationale": "Operator rejected the r2 package on 2026-09-02; prior PASS preserved in log, no longer satisfies approval.",
        })
    for kind in ["rendered", "referent"]:
        r = rev(N13)
        evt("agent", "node.verification", {
            "node": N13, "expected_revision": r, "kind": kind, "state": "pending",
            "evidence": {**SUPERSESSION, "verification_kind": kind},
            "rationale": "Superseded by operator rejection 2026-09-02; independence of prior pass was actor-label only.",
        })

    r = rev(N13)
    evt("agent", "node.patch", {
        "node": N13, "expected_revision": r,
        "acceptance_criteria": [
            "target_artifact_class: high_fidelity",
            "high_fidelity MEANS: interactive React design prototype inside apps/web using the real stack and component ecosystem "
            "with fixture data — standalone HTML/CSS is not acceptable design evidence",
            "Architecture derived from source-level product + component discovery; no assumed container count",
            "Materially different product concepts compared with evidence before convergence; CONSULT with genuine model separation recorded",
            "Rendered evidence: 1280px every prototyped surface; 390px shell + every mobile-required workflow; each claim cites screenshot + viewport",
            "D-0001/D-0003 rejected (D-0004/D-0005); D-0002 deferred (D-0006) — mapping/resolution remains reachable",
            "Production redesign implementation remains blocked until operator accepts the new direction",
        ],
    })
    r = rev(N13)
    evt("agent", "node.blocker.open", {
        "node": N13, "expected_revision": r, "id": "BL-OPERATOR-REJECTION-20260902", "type": "decision",
        "ref": "D-0004,D-0005,D-0006", "release_lease": True,
        "note": "Operator rejected r2 package 2026-09-02. New design package (React prototype + rendered evidence) required; "
                "Phase A / production redesign implementation blocked until operator accepts a direction.",
    })
    print("DONE record operator rejection")


if __name__ == "__main__":
    main()
