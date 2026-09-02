#!/usr/bin/env python3
"""Record the N-0013 r3 design package (React prototype + rendered evidence) on the programme.

Truthful state, not PASS:
- D-0007 (proposed, agent origin): direction H — capability-domain rail, composed Overview, entity
  context panel, command palette + directory, data-gated leaves. Operator acceptance pending.
- Quality dims that the package addresses -> state 'authored_unverified' with evidence pointers.
  The runtime treats anything other than pass/resolved/na as not done, so nothing here can satisfy
  completion; PASS may only be written by a separate GOV-008 session (other model where available).
- verification.rendered -> 'authored_unverified' pointing at rendered-verification.md + manifest.
- Blocker BL-OPERATOR-REJECTION-20260902 stays open (operator acceptance is the release condition).
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
RUN = "NS_REDESIGN_R3_20260902"
N13 = "N-0013"
INDEP = {
    "independence": "NONE — author-rendered, same session, same model (Fable 5.1); CONSULT used other model (claude opus CLI) for IA only",
    "reviewer_required": "separate GOV-008 session, other model where available",
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
    evt("agent", "decision.add", {
        "id": "D-0007", "scope": N13, "origin": "agent", "status": "proposed",
        "statement": (
            "PROPOSED 2026-09-02 (r3): primary navigation = capability domains derived from the data layer "
            "(Overview · Stock & Sell-through · Supply & Inbound · Planning · Funding & Settlement · Commercial inputs · "
            "Data & Stewardship · Administration[admin]); first destination = composed Overview with distinct Business "
            "dashboard (configurable, per-role seeded, governed metrics) and Needs-attention zones; every figure drills "
            "into an entity/case context panel; command palette + capability directory as accelerators; leaves data-gated. "
            "Reports and Dashboards are siblings (saved report pins as widget). Mapping/resolution stays reachable per-job "
            "and as a cross-job Steward queue leaf (D-0002 still deferred). "
            f"Evidence: {AUDIT}/DIRECTION.md, CONCEPTS.md, CONSULT_RESPONSE.md, rendered-verification.md, "
            "prototype apps/web/src/design-lab + app/(design-lab)."
        ),
    })

    r = rev(N13)
    evt("agent", "node.lease.acquire", {"node": N13, "expected_revision": r})

    dims = {
        "design_artifact_class": {"class": "react_prototype_in_repo", "paths": ["apps/web/src/design-lab/", "apps/web/src/app/(design-lab)/"]},
        "design_divergence": {"paths": [f"{AUDIT}/CONCEPTS.md", f"{AUDIT}/CONSULT_SEED.md", f"{AUDIT}/CONSULT_RESPONSE.md"], "consult_model": "claude opus (CLI, separate process)"},
        "rendered_comparison": {"paths": [f"{AUDIT}/rendered-verification.md", f"{AUDIT}/renders/proto/manifest.json"], "viewports": ["1280x800", "390x844"], "captures": 34},
        "rendered": {"paths": [f"{AUDIT}/rendered-verification.md"], "viewports": ["1280x800", "390x844"]},
        "design_sameness_review": {"paths": [f"{AUDIT}/FAULT_FINDINGS.md", f"{AUDIT}/DIRECTION.md#2"], "note": "structural change vs rejected six containers documented"},
        "content": {"paths": [f"{AUDIT}/DIRECTION.md#3", "apps/web/src/design-lab/shell/labNav.ts"], "note": "domain nouns + one-line what-it-computes per leaf"},
        "interaction_spec": {"paths": [f"{AUDIT}/rendered-verification.md"], "note": "edit dashboard, drill panel, approve case, map token, metric switch + pin proven in prototype"},
        "state_coverage": {"paths": [f"{AUDIT}/rendered-verification.md"], "note": "empty/gated (forecast), scope-empty, mobile cards, edit mode"},
        "accessibility": {"paths": ["apps/web/src/design-lab/primitives/Panel.tsx", "apps/web/src/design-lab/primitives/HeadlineFigure.tsx"], "note": "focus-visible outlines, keyboard on PanelRow/HeadlineFigure; NOT audited by axe — UNVERIFIED"},
    }
    for dim, ev in dims.items():
        r = rev(N13)
        evt("agent", "node.quality", {
            "node": N13, "expected_revision": r, "dim": dim, "state": "authored_unverified",
            "evidence": {**ev, **INDEP, "dim": dim},
            "rationale": "r3 package authored 2026-09-02; not PASS — independence none, awaiting separate GOV-008 and operator acceptance.",
        })

    r = rev(N13)
    evt("agent", "node.verification", {
        "node": N13, "expected_revision": r, "kind": "rendered", "state": "authored_unverified",
        "evidence": {"paths": [f"{AUDIT}/rendered-verification.md", f"{AUDIT}/renders/proto/"], **INDEP},
        "rationale": "34 captures, author-rendered; every claim cites file + viewport; UNVERIFIED for independence.",
    })

    r = rev(N13)
    evt("agent", "node.stage_note", {
        "node": N13, "expected_revision": r,
        "note": (
            "r3 design package complete for operator review (2026-09-02): FAULT_FINDINGS, PRODUCT_CAPABILITY_AUDIT, "
            "COMPONENT_ECOSYSTEM_AUDIT, CONCEPTS (3), CONSULT (opus, separate process) -> DIRECTION (hybrid H, D-0007 proposed); "
            "React prototype under apps/web/src/design-lab + app/(design-lab) (fixtures, no API); 34 renders @1280/@390 with "
            "manifest; EIF_REMEDIES_PROPOSAL (not applied); OPERATOR_SUMMARY. Node remains blocked on operator acceptance; "
            "production implementation not started."
        ),
    })
    r = rev(N13)
    evt("agent", "node.lease.release", {"node": N13, "expected_revision": r})
    print("DONE record r3 package")


if __name__ == "__main__":
    main()
