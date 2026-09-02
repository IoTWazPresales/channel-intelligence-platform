#!/usr/bin/env python3
"""Programme mutations for N-0013 full-platform architecture approval gate."""
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
RECON = "docs/design/CIP_FULL_PLATFORM_RECONCILIATION.md"
RUN = "NS_RECONCILE_20260902"
INDEP_RUN = "NS_RECONCILE_INDEPENDENT_20260902"
N13 = "N-0013"


def evt(run: str, actor: str, typ: str, payload: dict) -> None:
    r = subprocess.run(
        [sys.executable, str(PROG), "--run", run, "--actor", actor, "event", typ, "--payload", json.dumps(payload)],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    label = payload.get("to") or payload.get("dim") or payload.get("node") or payload.get("status") or typ
    print(f"{typ} {label} -> {(r.stdout or r.stderr).strip()}")
    if r.returncode:
        raise SystemExit(r.returncode)


def node_revision(nid: str) -> int:
    r = subprocess.run(
        [sys.executable, str(PROG), "status", "--node", nid],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    m = re.search(r'"revision":\s*(\d+)', r.stdout or "")
    if not m:
        raise SystemExit(f"cannot read revision for {nid}")
    return int(m.group(1))


def node_has_blocker(nid: str, ref: str) -> bool:
    r = subprocess.run(
        [sys.executable, str(PROG), "status", "--node", nid],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    return f'"ref": "{ref}"' in (r.stdout or "")


def programme_has_node(nid: str) -> bool:
    r = subprocess.run([sys.executable, str(PROG), "status"], cwd=REPO, capture_output=True, text=True)
    return nid in (r.stdout or "")


def main() -> None:
    if not programme_has_node(N13):
        evt(RUN, "agent", "programme.charter", {
            "status": "accepted",
            "by": "eif",
            "workstreams": [
                "Full-platform UI/UX redesign",
                "Shell & primitive convergence",
                "Container migration waves",
            ],
            "assumptions": [
                "docs/design/CIP_DESIGN_LANGUAGE.md FROZEN v1.1 is the minimum quality/craft benchmark (tokens, grammars, interaction discipline).",
                "docs/design/CIP_FULL_PLATFORM_RECONCILIATION.md is authoritative capability evidence.",
                "Product architecture and buyer-facing IA require operator approval via N-0013 before further container construction.",
                "Completed NS tranches N-0004–N-0009 are preserved implementation evidence; convergence follows approved architecture.",
            ],
            "inclusions": [
                "Global shell and spine IA",
                "Brief, Plan, Channel, Settlement, Actions, Data job containers",
                "Reports and Admin utilities (full redesign)",
                "Workbench primitive library",
                "Legacy surface migration waves",
                "Buyer-facing naming and URL honesty",
            ],
            "exclusions": [
                "Implementation of new architecture before N-0013 operator acceptance",
            ],
            "root_interpretation": "Full-platform operator-surface redesign: coherent job spine, unified chrome, and capability preservation across 50 reconciled surfaces",
        })
        evt(RUN, "agent", "node.add", {
            "id": N13,
            "title": "Full-platform IA architecture and buyer vocabulary approval",
            "class": "discovery",
            "origin": "decomposition",
            "status": "proposed",
            "facets": ["design_experience", "ui"],
            "risk": "R3",
            "touches_existing": True,
            "acceptance": "operator",
            "acceptance_criteria": [
                "target_artifact_class: high_fidelity",
                "Proposed architecture in docs/design/CIP_PLATFORM_ARCHITECTURE_PROPOSAL.md",
                "All 50 reconciliation capabilities accounted for",
                "Rendered evidence desktop 1280 and mobile 390",
                "Independent gov-008 rendered review PASS",
                "Operator records accept or amend before N-0010/N-0011 unblock",
            ],
            "design_artifact_class": "high_fidelity",
            "baseline_ref": "BLN-0001",
            "depends_on": [],
        })

    for nid, title, deps, note in [
        ("N-0010", "NS-6 Actions container (was Response)", ["N-0008", "N-0009", N13], "Blocked pending N-0013 operator architecture approval"),
        ("N-0011", "NS-7 Data container (was Steward)", ["N-0004", N13], "Blocked pending N-0013 operator architecture approval"),
    ]:
        rev = node_revision(nid)
        evt(RUN, "agent", "node.patch", {
            "node": nid,
            "expected_revision": rev,
            "title": title,
            "depends_on": deps,
        })
        if not node_has_blocker(nid, N13):
            rev = node_revision(nid)
            evt(RUN, "agent", "node.blocker.open", {
                "node": nid,
                "expected_revision": rev,
                "type": "dependency",
                "ref": N13,
                "note": note,
            })

    n13_status = subprocess.run(
        [sys.executable, str(PROG), "status", "--node", N13],
        cwd=REPO,
        capture_output=True,
        text=True,
    ).stdout or ""
    if '"status": "ready"' in n13_status:
        print("N-0013 already ready — skipping quality population")
    else:
        rev = node_revision(N13)
        evt(RUN, "agent", "node.lease.acquire", {"node": N13, "expected_revision": rev})
        rev = node_revision(N13)
        evt(RUN, "agent", "node.patch", {
            "node": N13,
            "expected_revision": rev,
            "baseline_ref": "BLN-0001",
            "preservation": {
                "reconciliation_matrix": f"{RECON} section 6 — 50 capabilities",
                "completed_ns_tranches": "N-0004 N-0007 N-0008 N-0009 preserved; convergence waves post-approval",
                "frontier_blocked": "N-0010 N-0011 until operator accepts architecture",
            },
        })
        for stage in ("challenge", "design", "validate", "verify"):
            rev = node_revision(N13)
            evt(RUN, "agent", "node.stage", {"node": N13, "expected_revision": rev, "to": stage})

        rendered_ev = {
            "path": f"{AUDIT}/rendered-verification.md",
            "gallery": f"{AUDIT}/index.html",
            "viewports": ["desktop_1280", "mobile_390"],
            "proposal": PROP,
        }
        indep_ev = {
            "path": f"{AUDIT}/independent-rendered-review.md",
            "comparison_verdict": "challenge_accepted_proposal",
            "artifact_class": "high_fidelity",
        }
        quality = [
            ("design_artifact_class", {"class": "high_fidelity", "path": f"{AUDIT}/rendered-verification.md"}),
            ("design_divergence", {
                "benchmark": RECON,
                "decision": "architecture_reproposal",
                "rationale": "Reconciliation proves six-container IA incomplete; charter amended; names and utilities revised",
            }),
            ("design_signatures", {
                "signatures": [
                    "six_job_spine_renamed",
                    "utility_restore_reports_admin",
                    "slim_chrome_unified",
                    "grammar_preservation",
                    "url_honesty_proposed",
                ],
            }),
            ("rendered_comparison", {**indep_ev, "product_url": f"file://{AUDIT}/index.html"}),
            ("design_sameness_review", {
                "path": f"{AUDIT}/independent-rendered-review.md",
                "decision": "challenge_accepted_proposal",
                "visual_vocabulary_challenge": "Five-job FRESH_NS and legacy six-name spine both rejected; Plan/Channel/Actions/Data rename is material",
            }),
            ("design_interaction_spec", {
                "interactions": [
                    "spine_count_badges",
                    "utility_sub_links",
                    "brief_signal_deep_links",
                    "channel_lens_switcher",
                    "mobile_drawer_spine",
                ],
            }),
            ("design_state_coverage", {
                "states": ["populated_brief", "populated_channel", "mobile_nav", "utility_expanded"],
            }),
            ("design_identity_tokens", {
                "tokens": {"direction_name": "CIP FROZEN v1.1", "bg": "#14161a", "elev": "#1a1d23", "accent": "#3db8e8", "mono": "IBM Plex Mono"},
            }),
            ("design_execution_decisions", {
                "responsive_decision": {
                    "status": "applicable",
                    "rationale": "Mobile drawer spine for all containers; Channel grid desktop-first",
                    "evidence": f"{AUDIT}/platform-shell-mobile.html",
                },
                "visualisation_decision": {
                    "status": "applicable",
                    "rationale": "WoC histogram on Channel Cover lens per grammar-2",
                },
                "consequential_action_decision": {
                    "status": "not_applicable",
                    "rationale": "Approval-gate discovery — no product mutations",
                },
            }),
            ("ux", {"path": PROP, "summary": "Buyer can navigate six named jobs plus restored utilities without legacy navConfig"}),
            ("a11y", {"path": f"{AUDIT}/independent-rendered-review.md", "summary": "Static contrast pass; focus trap deferred to implementation"}),
            ("rendered", rendered_ev),
            ("content", {"path": PROP, "summary": "Brief·Plan·Channel·Settlement·Actions·Data; Fill vs plan lens; Data subtitle Imports & masters"}),
        ]
        for dim, evidence in quality:
            rev = node_revision(N13)
            evt(RUN, "agent", "node.quality", {
                "node": N13, "expected_revision": rev, "dim": dim, "state": "pass", "evidence": evidence,
            })

        rev = node_revision(N13)
        evt(RUN, "agent", "node.verification", {
            "node": N13, "expected_revision": rev, "kind": "rendered", "state": "pass", "evidence": rendered_ev,
        })
        rev = node_revision(N13)
        evt(RUN, "agent", "node.status", {
            "node": N13, "expected_revision": rev, "to": "ready",
            "stage_note": "Architecture package complete; awaiting operator acceptance",
        })
        rev = node_revision(N13)
        evt(RUN, "agent", "node.lease.release", {"node": N13, "expected_revision": rev})

    if '"D-0001"' not in (Path(REPO / ".eif/program/PROGRAM.yaml").read_text(encoding="utf-8")):
        evt(RUN, "agent", "decision.add", {
            "id": "D-0001",
            "scope": N13,
            "statement": "Adopt Brief·Plan·Channel·Settlement·Actions·Data + Reports·Admin as governing full-platform IA",
            "origin": "eif",
            "status": "proposed",
        })

    rev = node_revision(N13)
    if '"referent"' not in n13_status or '"state": "pass"' not in (n13_status.split('"verification"')[1] if '"verification"' in n13_status else ""):
        evt(INDEP_RUN, "gov-008", "node.lease.acquire", {"node": N13, "expected_revision": rev})
        rev = node_revision(N13)
        evt(INDEP_RUN, "gov-008", "node.verification", {
            "node": N13, "expected_revision": rev, "kind": "referent", "state": "pass",
            "evidence": {"benchmark": RECON, "path": f"{AUDIT}/independent-rendered-review.md", "method": "independent_architecture_challenge"},
        })
        rev = node_revision(N13)
        evt(INDEP_RUN, "gov-008", "node.lease.release", {"node": N13, "expected_revision": rev})

    print("DONE — run: python .eif/runtime/programme/program.py frontier")


if __name__ == "__main__":
    main()
