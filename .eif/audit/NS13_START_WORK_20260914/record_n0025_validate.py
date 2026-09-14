"""Implementer quality + validate + lease.release for N-0025. Do not complete (GOV-008 later)."""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
PROG = REPO / ".eif/runtime/programme/program.py"
RUN = "NS13_START_WORK_20260914"
ACTOR = "gov-001"
NODE = "N-0025"
EV = ".eif/audit/NS13_START_WORK_20260914/implementer-evidence.md"
PAYLOAD_DIR = Path(__file__).resolve().parent / "payloads"


def run(args: list[str]) -> str:
    r = subprocess.run([sys.executable, str(PROG), *args], cwd=REPO, capture_output=True, text=True)
    out = (r.stdout or "") + (r.stderr or "")
    print(out.strip())
    if r.returncode:
        raise SystemExit(r.returncode)
    return out


def node_rev() -> int:
    out = run(["status", "--node", NODE])
    m = re.search(r'"revision":\s*(\d+)', out)
    if not m:
        raise SystemExit("no revision")
    return int(m.group(1))


def event(name: str, payload: dict) -> None:
    payload = dict(payload)
    payload["node"] = NODE
    payload["expected_revision"] = node_rev()
    PAYLOAD_DIR.mkdir(parents=True, exist_ok=True)
    path = PAYLOAD_DIR / f"{name.replace('.', '_')}.json"
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
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
    event("node.lease.heartbeat", {"ttl_seconds": 3600})
    event(
        "evidence.add",
        {
            "id": "EV-N0025-IMPL",
            "provenance": "implementation-observation",
            "path": EV,
            "note": "N-0025 Start work + remaining obstruct findings; Playwright MCP; no browser_cdp; no cip writes",
        },
    )

    quals = [
        ("design_artifact_class", {"class": "high_fidelity", "path": EV}),
        (
            "design_divergence",
            {
                "benchmark": "actionable work reachable from Overview without stuffing Attention",
                "decision": "start_work_panel_plus_named_leaf_defaults",
                "path": EV,
            },
        ),
        (
            "design_signatures",
            {
                "signatures": [
                    "overview_start_work_prime",
                    "attention_exceptions_only",
                    "empty_dashboard_compact_below",
                    "payments_terms_named_leaf_is_the_work",
                    "claims_rows_to_import_center_and_case_book",
                    "data_also_here_strip",
                    "sell_through_names_not_ids",
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
                "product_url": "http://localhost:3000/brief",
                "viewport": "desktop+390",
                "comparison_verdict": "start_work_reaches_existing_job_screens",
            },
        ),
        (
            "design_sameness_review",
            {
                "visual_vocabulary_challenge": (
                    "Challenged stuffing verbs into Attention or adding a rail domain. "
                    "Start work is one Overview panel; Attention stays blotter-only. Path: " + EV
                ),
                "path": EV,
                "decision": "one_start_work_surface_on_overview",
            },
        ),
        (
            "design_interaction_spec",
            {
                "interactions": [
                    "click_start_work_create_lineup",
                    "click_start_work_import_shipping",
                    "open_payments_wizard_default",
                    "open_terms_editor_default",
                    "click_claims_import_row",
                    "open_data_also_here_products",
                    "open_sell_through_workspace_names",
                ],
                "path": EV,
            },
        ),
        (
            "design_state_coverage",
            {
                "states": [
                    "overview_start_work",
                    "empty_dashboard_compact",
                    "payments_wizard",
                    "terms_editor",
                    "claims_rows",
                    "data_also_here",
                    "sell_through_named_filters",
                    "overview_390",
                ],
                "path": EV,
            },
        ),
        (
            "design_identity_tokens",
            {
                "tokens": {
                    "direction_name": "start work from overview",
                    "attention": "exceptions only",
                },
                "path": EV,
            },
        ),
        (
            "design_execution_decisions",
            {
                "responsive_decision": {
                    "status": "applicable",
                    "rationale": "Named 390 workflow: Start work remains visible above Attention.",
                    "evidence": EV,
                },
                "visualisation_decision": {
                    "status": "applicable",
                    "rationale": "Attention column 431px at 1280; production grid not lab 312px.",
                    "evidence": EV,
                },
                "consequential_action_decision": {
                    "status": "applicable",
                    "rationale": "Start work and named leaves open existing job screens. No second creator.",
                    "evidence": EV,
                },
            },
        ),
        (
            "ux",
            {
                "path": EV,
                "summary": "Overview Start work begins the five jobs on existing screens. Named Payments/Terms/Claims/Data leaves no longer dump to empty pointers.",
            },
        ),
        (
            "a11y",
            {
                "path": EV,
                "summary": "Start work rows are real links. Keyboard/axe full pass not this session.",
            },
        ),
        (
            "rendered",
            {
                "path": EV,
                "url": "http://localhost:3000/brief",
                "viewports": ["1280x800", "390x844"],
            },
        ),
        (
            "content",
            {
                "path": EV,
                "summary": "Start work verbs name existing jobs. Attention copy unchanged. Data also-here names rail-only leaves.",
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
                "url": "http://localhost:3000/brief",
                "clicks": [
                    "/admin/imports?unified=1",
                    "/admin/imports?template=inbound_shipments",
                    "/commercial-planner/cpor-cases/payment-evidence-import",
                    "/admin/customer-commercial-terms",
                    "/commercial-planner/cpor-cases/claims",
                    "/admin/imports?template=cpor_claim_evidence",
                    "/admin/products",
                    "/channel-intelligence/workspace",
                ],
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
                "product": "startWork.ts + named leaf defaults + dataAlsoHere + cst display names",
            },
        },
    )
    event("node.stage", {"to": "validate"})
    event(
        "node.stage_note",
        {
            "stage_note": (
                "Implementer validate: Start work on Overview; Payments/Terms/Claims/Data/sell-through "
                "obstruct findings closed without inventing screens. Playwright 1280 + 390. Independent "
                "GOV-008 not recorded. Do not complete."
            )
        },
    )
    event("node.lease.release", {})
    run(["status", "--node", NODE])
    run(["frontier"])


if __name__ == "__main__":
    main()
