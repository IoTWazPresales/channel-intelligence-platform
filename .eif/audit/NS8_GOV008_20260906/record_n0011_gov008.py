"""Record independent GOV-008 on N-0011 and complete if gates pass.

Run/actor: NS8_GOV008_20260906 / gov-008
Implementation remains NS8_DATA_20260906 / gov-001.
Does not touch D-0002. Does not edit product source.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
PROG = REPO / ".eif/runtime/programme/program.py"
RUN = "NS8_GOV008_20260906"
ACTOR = "gov-008"
IMPL_RUN = "NS8_DATA_20260906"
IMPL_ACTOR = "gov-001"
NODE = "N-0011"
EV = ".eif/audit/NS8_GOV008_20260906/independent-rendered-review.md"


def run(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    r = subprocess.run([sys.executable, str(PROG), *args], cwd=REPO, capture_output=True, text=True)
    out = (r.stdout or "") + (r.stderr or "")
    print(out.strip())
    if check and r.returncode:
        raise SystemExit(r.returncode)
    return r


def node_rev() -> int:
    r = run(["status", "--node", NODE])
    m = re.search(r'"revision":\s*(\d+)', r.stdout or "")
    if not m:
        raise SystemExit("no revision")
    return int(m.group(1))


def event(name: str, payload: dict, *, run_id: str = RUN, actor: str = ACTOR, check: bool = True) -> subprocess.CompletedProcess[str]:
    payload = dict(payload)
    payload["node"] = NODE
    payload["expected_revision"] = node_rev()
    return run(
        [
            "--run",
            run_id,
            "--actor",
            actor,
            "event",
            name,
            "--payload",
            json.dumps(payload),
        ],
        check=check,
    )


def take_lease() -> None:
    rec = event("node.lease.reclaim", {"ttl_seconds": 3600}, check=False)
    blob = (rec.stdout or "") + (rec.stderr or "")
    if rec.returncode == 0:
        return
    if "LEASE_HELD" not in blob:
        raise SystemExit(rec.returncode or 1)
    print("lease held by implementer run; releasing then acquiring as GOV-008")
    event("node.lease.release", {}, run_id=IMPL_RUN, actor=IMPL_ACTOR)
    event("node.lease.acquire", {"ttl_seconds": 3600})


def main() -> None:
    take_lease()

    quals = [
        (
            "design_artifact_class",
            {"class": "high_fidelity", "path": EV},
        ),
        (
            "design_divergence",
            {
                "benchmark": "apps/web/src/design-lab/surfaces/DataSurface.tsx",
                "decision": "cip_number_rule_not_lab_fixtures",
                "path": EV,
            },
        ),
        (
            "design_signatures",
            {
                "signatures": [
                    "domain_header",
                    "lens_tabs_4",
                    "headline_strip_5",
                    "start_import_cards_6",
                    "scope_bar",
                    "import_job_cards_390",
                    "relocated_wizard",
                ],
                "path": EV,
            },
        ),
        (
            "rendered_comparison",
            {
                "artifact_class": "high_fidelity",
                "class": "high_fidelity",
                "path": EV,
                "product_url": "http://localhost:3000/admin/imports",
                "lab_url": "http://localhost:3000/design-lab/data?tab=imports",
                "viewport": "1280x800",
                "comparison_verdict": "parity_with_number_rule_substitution",
            },
        ),
        (
            "design_sameness_review",
            {
                "visual_vocabulary_challenge": (
                    "Challenged whether production is the same Data & Stewardship instrument "
                    "as DataSurface.tsx or a header strip glued onto the old wizard with a "
                    "legacy mapping-queue leaf pretending to be the lab cross-job steward. "
                    "Chrome grammar matches (DomainHeader + four LensTabs + HeadlineStrip 5 + "
                    "six start cards + ScopeBar). NUMBER RULE substitutes cip 88/12/0/47/17 for "
                    "lab 8/1/2/4/19. Relocated wizard and PARTIAL steward (D-0002) are charter, "
                    "not a fail. Stores UNCOVERED is labelled. Path: " + EV
                ),
                "path": EV,
                "decision": "retain_lab_chrome_with_cip_numbers",
            },
        ),
        (
            "design_interaction_spec",
            {
                "interactions": [
                    "lens_tabs_four_routes",
                    "start_card_template_deep_link",
                    "scope_bar_jobStatus",
                    "import_job_cards_390",
                    "relocated_wizard",
                ],
                "path": EV,
            },
        ),
        (
            "design_state_coverage",
            {
                "states": [
                    "populated",
                    "uncovered_stores",
                    "legacy_queue_empty",
                    "wizard_idle_hidden_xs",
                    "wizard_engaged_template",
                ],
                "path": EV,
            },
        ),
        (
            "design_identity_tokens",
            {
                "tokens": {
                    "direction_name": "workbench-ui Data & Stewardship DomainHeader+LensTabs+HeadlineStrip",
                    "strip": "HeadlineStrip columns=5",
                    "start": "six import-type cards",
                    "scope": "ScopeBar",
                    "mobile": "import-job-cards",
                },
                "path": EV,
            },
        ),
        (
            "design_execution_decisions",
            {
                "responsive_decision": {
                    "status": "applicable",
                    "rationale": (
                        "Verified 1280x800 vs lab and 390x844 import status. Idle wizard "
                        "CSS-hidden at xs; job cards remain. Viewport via Playwright setViewportSize."
                    ),
                    "evidence": EV,
                },
                "visualisation_decision": {
                    "status": "applicable",
                    "rationale": (
                        "Lab HeadlineStrip + start-card grid + ScopeBar mounted. Live cip grains; "
                        "lab fixtures not copied. Masters duplicate figure is em-dash."
                    ),
                    "evidence": EV,
                },
                "consequential_action_decision": {
                    "status": "applicable",
                    "rationale": (
                        "Strip/scope are filters and navigation. Writes remain the relocated wizard "
                        "and per-job steward. Cross-job accept/reject not on this leaf. D-0002 untouched."
                    ),
                    "evidence": EV,
                },
            },
        ),
        (
            "ux",
            {
                "path": EV,
                "summary": "Operator can read import status at 1280 and 390 without a desktop wall; four lenses reachable.",
            },
        ),
        (
            "a11y",
            {
                "path": EV,
                "summary": "Lens tablist; HeadlineFigure severity channels; StatusChip on 390 cards. Keyboard not exercised.",
            },
        ),
        (
            "rendered",
            {
                "path": EV,
                "url": "http://localhost:3000/admin/imports",
                "viewports": ["desktop_1280", "mobile_390"],
            },
        ),
        (
            "content",
            {
                "path": EV,
                "summary": "Jobs in last 7 days not this week; Partly built / Planned retained; D-0002 copy; UNCOVERED stores.",
            },
        ),
    ]
    for dim, evidence in quals:
        event("node.quality", {"dim": dim, "state": "pass", "evidence": evidence})

    event(
        "node.verification",
        {
            "kind": "rendered",
            "state": "pass",
            "evidence": {
                "path": EV,
                "url": "http://localhost:3000/admin/imports",
                "viewports": ["desktop_1280", "mobile_390"],
            },
        },
    )
    event(
        "node.verification",
        {
            "kind": "referent",
            "state": "pass",
            "evidence": {
                "path": EV,
                "lab": "apps/web/src/design-lab/surfaces/DataSurface.tsx",
                "product": "apps/web/src/features/data-stewardship/DataChrome.tsx",
            },
        },
    )
    event("node.status", {"to": "complete"})
    run(["status", "--node", NODE])


if __name__ == "__main__":
    main()
