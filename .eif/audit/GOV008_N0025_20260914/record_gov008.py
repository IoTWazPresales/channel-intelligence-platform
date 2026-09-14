"""Record independent GOV-008 on N-0025. Do not complete.

Run/actor: GOV008_N0025_20260914 / gov-008
Implementation remains NS13_START_WORK_20260914 / gov-001.
Verdict: VERIFIED_WITH_LIMITATIONS — node stays in_progress at validate.
Windows: every event uses --payload-file. Does not edit product source.
Does not remediate N-0025. Does not touch D-0002.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
PROG = REPO / ".eif/runtime/programme/program.py"
RUN = "GOV008_N0025_20260914"
ACTOR = "gov-008"
EV = ".eif/audit/GOV008_N0025_20260914/independent-rendered-review.md"
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
        raise SystemExit(r.returncode)
    return r


def node_rev() -> int:
    r = run(["--run", RUN, "--actor", ACTOR, "status", "--node", NODE])
    m = re.search(r'"revision":\s*(\d+)', r.stdout or "")
    if not m:
        raise SystemExit("no revision for N-0025")
    return int(m.group(1))


def event(name: str, payload: dict) -> subprocess.CompletedProcess[str]:
    payload = dict(payload)
    payload["node"] = NODE
    payload["expected_revision"] = node_rev()
    PAYLOAD_DIR.mkdir(parents=True, exist_ok=True)
    path = PAYLOAD_DIR / f"{NODE}_{name.replace('.', '_')}_{payload['expected_revision']}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return run(
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
    quals = [
        ("design_artifact_class", {"class": "high_fidelity", "path": EV}),
        (
            "design_divergence",
            {
                "benchmark": "actionable work reachable from Overview without stuffing Attention",
                "decision": "start_work_panel_plus_named_leaf_defaults",
                "path": EV,
                "verdict": "VERIFIED_WITH_LIMITATIONS",
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
                    "viewer_no_start_verbs",
                    "steward_queue_empty_legacy",
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
                "comparison_verdict": "start_work_reaches_existing_screens_steward_queue_cannot_complete",
            },
        ),
        (
            "design_sameness_review",
            {
                "visual_vocabulary_challenge": (
                    "Challenged stuffing verbs into Attention or a new rail domain. "
                    "Independent enum of palette, directory, hub Workflows, headlines, "
                    "headers, Import Center cards, Start work. Every clicked verb opened "
                    "an existing screen. Steward queue is the existing empty legacy leaf "
                    "(D-0002). Payments back-link is leftover same-URL chrome. Path: " + EV
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
                    "click_start_work_import_cst_to_choose_file",
                    "click_start_work_import_shipping",
                    "click_start_work_settle_to_confirm_dialog",
                    "click_start_work_steward_queue_empty",
                    "open_payments_wizard_default",
                    "click_payments_back_to_lens_noop",
                    "open_terms_editor_default",
                    "click_claims_import_row",
                    "open_data_also_here_products",
                    "open_sell_through_workspace_names",
                    "login_viewer_no_verbs",
                ],
                "path": EV,
            },
        ),
        (
            "design_state_coverage",
            {
                "states": [
                    "overview_start_work_admin",
                    "overview_start_work_viewer_empty",
                    "empty_dashboard_compact",
                    "attention_431px",
                    "overview_390",
                    "cst_wizard_upload_step",
                    "settle_confirm_dialog",
                    "mappings_empty_legacy",
                    "payments_wizard",
                    "terms_editor",
                    "claims_rows",
                    "data_also_here",
                    "sell_through_named_filters",
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
                    "verdict": "VERIFIED_WITH_LIMITATIONS",
                },
                "path": EV,
            },
        ),
        (
            "design_execution_decisions",
            {
                "responsive_decision": {
                    "status": "applicable",
                    "rationale": "Named 390 workflow: Start work remains first, above Attention.",
                    "evidence": EV,
                },
                "visualisation_decision": {
                    "status": "applicable",
                    "rationale": "Attention column 431px at 1280; production grid not lab 312px.",
                    "evidence": EV,
                },
                "consequential_action_decision": {
                    "status": "applicable",
                    "rationale": (
                        "Clicked verbs open existing job screens. Settle reached Confirm settlement. "
                        "Steward queue cannot complete 2814 per-job candidates (D-0002). "
                        "No complete() this review."
                    ),
                    "evidence": EV,
                },
            },
        ),
        (
            "ux",
            {
                "path": EV,
                "summary": (
                    "Start work begins four of five named jobs on existing screens. "
                    "Viewer has no verbs (live). Steward queue is an empty legacy leaf. "
                    "Payments wizard is the named leaf; Back to Payments lens is a same-URL leftover."
                ),
            },
        ),
        (
            "a11y",
            {
                "path": EV,
                "summary": "Start work rows are real links. Viewer empty state is text. Keyboard/axe full pass not this session.",
            },
        ),
        (
            "rendered",
            {
                "path": EV,
                "url": "http://localhost:3000/brief",
                "clicks": [
                    "/admin/imports?template=customer_sell_through",
                    "/commercial-planner/cpor-cases",
                    "/commercial-planner/cpor-cases/46",
                    "/admin/mappings",
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
        ),
        (
            "content",
            {
                "path": EV,
                "summary": (
                    "Start work verbs name existing jobs. Viewer copy: nothing this role can start. "
                    "Steward queue copy admits per-job work stays on the import job."
                ),
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
                "verdict": "VERIFIED_WITH_LIMITATIONS",
                "clicks": [
                    "/admin/imports?template=customer_sell_through",
                    "/commercial-planner/cpor-cases/46",
                    "/admin/mappings",
                    "/admin/imports?unified=1",
                    "/admin/imports?template=inbound_shipments",
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
                "verdict": "VERIFIED_WITH_LIMITATIONS",
            },
        },
    )
    note = (
        "GOV-008 VERIFIED_WITH_LIMITATIONS. Independent clicks: CST to Choose file, "
        "settle to Confirm settlement dialog, steward queue empty (2814 per-job, D-0002). "
        "Viewer live: no verbs. Planner live UNVERIFIED (no tenant user). "
        "Payments Back to Payments lens is same-URL residual. Do not complete. Do not remediate in this run."
    )
    event("node.stage_note", {"stage_note": note})
    event("node.lease.release", {"stage_note": note})
    run(["--run", RUN, "--actor", ACTOR, "status", "--node", NODE])


if __name__ == "__main__":
    main()
