"""Implementer quality + validate + lease.release for N-0026. Do not complete (GOV-008 later)."""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
PROG = REPO / ".eif/runtime/programme/program.py"
RUN = "NS14_PROMO_PLAN_20260914"
ACTOR = "gov-001"
NODE = "N-0026"
EV = ".eif/audit/NS14_PROMO_PLAN_20260914/implementer-evidence.md"
PAYLOAD_DIR = Path(__file__).resolve().parent / "payloads" / "validate"


def run(args: list[str]) -> str:
    r = subprocess.run(
        [sys.executable, "-B", str(PROG), "--project", str(REPO), *args],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    out = (r.stdout or "") + (r.stderr or "")
    print(out.strip())
    if r.returncode:
        raise SystemExit(r.returncode)
    return out


def node_rev() -> int:
    out = run(["--run", RUN, "--actor", ACTOR, "status", "--node", NODE])
    m = re.search(r'"revision":\s*(\d+)', out)
    if not m:
        raise SystemExit("no revision")
    return int(m.group(1))


def event(name: str, payload: dict) -> None:
    payload = dict(payload)
    payload["node"] = NODE
    payload["expected_revision"] = node_rev()
    PAYLOAD_DIR.mkdir(parents=True, exist_ok=True)
    path = PAYLOAD_DIR / f"{NODE}_{name.replace('.', '_')}_{payload['expected_revision']}.json"
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
    event("node.lease.reclaim", {"ttl_seconds": 14400})
    event(
        "evidence.add",
        {
            "id": "EV-N0026-IMPL",
            "provenance": "implementation-observation",
            "path": EV,
            "note": "N-0026 propose from customer+period; Playwright 1280 compose 40 lineup lines; no cip write; no GOV-008",
        },
    )

    quals = [
        ("design_artifact_class", {"class": "high_fidelity", "path": EV}),
        (
            "design_divergence",
            {
                "benchmark": "propose a cpor_case from customer and period on Promotion Planner",
                "decision": "customer_period_compose_on_existing_planner",
                "path": EV,
            },
        ),
        (
            "design_signatures",
            {
                "signatures": [
                    "create_promotion_plan_start_work",
                    "propose_dialog_customer_period",
                    "headline_no_percent_bias",
                    "same_customer_comparables_only",
                    "origin_proposed_by_cip",
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
                "product_url": "http://localhost:3000/promotions?propose=1",
                "viewport": "1280x800",
                "comparison_verdict": "start_work_opens_existing_propose_workbench",
            },
        ),
        (
            "design_sameness_review",
            {
                "visual_vocabulary_challenge": (
                    "Challenged a second creator and a 257% budget-reservation percent. "
                    "Propose stays on Promotion Planner. Strip shows counts and USD, not a ratio. Path: " + EV
                ),
                "path": EV,
                "decision": "one_propose_workbench_on_planner",
            },
        ),
        (
            "design_interaction_spec",
            {
                "interactions": [
                    "click_start_work_create_promotion_plan",
                    "select_customer_and_period",
                    "propose_from_evidence_compose",
                    "do_not_confirm_create_draft",
                ],
                "path": EV,
            },
        ),
        (
            "design_state_coverage",
            {
                "states": [
                    "overview_create_promotion_plan",
                    "propose_dialog_empty",
                    "propose_dialog_40_lineup_lines",
                    "planner_strip_usd_not_percent",
                ],
                "path": EV,
            },
        ),
        (
            "design_identity_tokens",
            {
                "tokens": {
                    "direction_name": "create promotion plan",
                    "object": "cpor_case",
                },
                "path": EV,
            },
        ),
        (
            "design_execution_decisions",
            {
                "responsive_decision": {
                    "status": "applicable",
                    "rationale": "Named 1280 workflow: Start work verb to propose dialog.",
                    "evidence": EV,
                },
                "visualisation_decision": {
                    "status": "applicable",
                    "rationale": "Strip uses case counts and USD; does not show actual/planned as a percent.",
                    "evidence": EV,
                },
                "consequential_action_decision": {
                    "status": "applicable",
                    "rationale": "Compose is GET. Create draft not confirmed (cip write). Existing case/line path.",
                    "evidence": EV,
                },
            },
        ),
        (
            "ux",
            {
                "path": EV,
                "summary": "Create promotion plan opens the existing propose dialog. Customer+period compose 40 lineup lines. Create draft not confirmed.",
            },
        ),
        (
            "a11y",
            {
                "path": EV,
                "summary": "Start work is a real link. Propose controls are labelled. Keyboard/axe full pass not this session.",
            },
        ),
        (
            "rendered",
            {
                "path": EV,
                "url": "http://localhost:3000/promotions?propose=1",
                "viewports": ["1280x800"],
            },
        ),
        (
            "content",
            {
                "path": EV,
                "summary": "Verb is Create promotion plan. Strip captions refuse the 257% ratio. Product-set source commercial_lineup_line named in the dialog.",
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
                    "/promotions?propose=1",
                ],
                "compose": {
                    "customer_id": 18,
                    "period_label": "2026Q2",
                    "lines": 40,
                    "product_set_source": "commercial_lineup_line",
                    "same_customer_comparables": 10,
                    "create_draft_clicked": False,
                },
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
                "product": "promo_plan_builder.py + PromoPlanBuilderPanel + startWork create-promo-plan",
            },
        },
    )
    event("node.stage", {"to": "validate"})
    event(
        "node.stage_note",
        {
            "stage_note": (
                "Implementer validate: customer+period compose on Promotion Planner "
                "(40 commercial_lineup_line rows, Computer Mania 2026Q2). Start work Create promotion plan. "
                "No 257% on the strip. Create draft not confirmed. Independent GOV-008 not recorded. Do not complete."
            )
        },
    )
    event("node.lease.release", {})
    run(["--run", RUN, "--actor", ACTOR, "status", "--node", NODE])
    run(["--run", RUN, "--actor", ACTOR, "frontier"])


if __name__ == "__main__":
    main()
