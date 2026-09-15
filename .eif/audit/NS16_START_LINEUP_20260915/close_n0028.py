"""Implementer quality + validate + lease.release for N-0028. Do not complete (GOV-008 later)."""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
PROG = REPO / ".eif/runtime/programme/program.py"
RUN = "NS16_START_LINEUP_20260915"
ACTOR = "gov-001"
NODE = "N-0028"
EV = ".eif/audit/NS16_START_LINEUP_20260915/implementer-evidence.md"
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
    event(
        "evidence.add",
        {
            "id": "EV-N0028-IMPL",
            "provenance": "implementation-observation",
            "path": EV,
            "note": "N-0028 Start work cards + Lineup cases HeadlineStrip; Playwright 1280; no cip write; no GOV-008",
        },
    )

    quals = [
        ("design_artifact_class", {"class": "high_fidelity", "path": EV}),
        (
            "design_divergence",
            {
                "benchmark": "Start work cards without wrapper; Lineup cases on lab composition",
                "decision": "import_center_cards_and_headline_scope_lineup_leaf",
                "path": EV,
            },
        ),
        (
            "design_signatures",
            {
                "signatures": [
                    "start_work_outlined_cards_no_wrapper",
                    "import_a_lineup_unified_import",
                    "create_promotion_plan_retained",
                    "lineup_cases_headline_strip",
                    "approval_scope_bar_wired",
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
                "viewport": "1280x800",
                "comparison_verdict": "cards_and_lineup_leaf_on_workbench_primitives",
            },
        ),
        (
            "design_sameness_review",
            {
                "visual_vocabulary_challenge": (
                    "Challenged a Panel wrapper around Start work and a second DomainHeader on lineup cases. "
                    "Cards match Import Center. Lineup leaf uses HeadlineStrip + ScopeBar under existing PlanningChrome. Path: " + EV
                ),
                "path": EV,
                "decision": "no_wrapper_card_reuse_planning_chrome",
            },
        ),
        (
            "design_interaction_spec",
            {
                "interactions": [
                    "click_import_a_lineup",
                    "confirm_create_promotion_plan_href",
                    "open_lineup_cases_headline_and_scope",
                ],
                "path": EV,
            },
        ),
        (
            "design_state_coverage",
            {
                "states": [
                    "overview_start_work_cards",
                    "unified_import_dialog",
                    "lineup_cases_1647_lines",
                    "no_fake_trend_bars",
                ],
                "path": EV,
            },
        ),
        (
            "design_identity_tokens",
            {
                "tokens": {
                    "direction_name": "import a lineup",
                    "object": "commercial_lineup_case",
                },
                "path": EV,
            },
        ),
        (
            "design_execution_decisions",
            {
                "responsive_decision": {
                    "status": "applicable",
                    "rationale": "Named 1280: Overview cards and Lineup cases HeadlineStrip.",
                    "evidence": EV,
                },
                "visualisation_decision": {
                    "status": "applicable",
                    "rationale": "Live planned units / net / approval / pending / coverage. Fake Q1/Q2 bars removed.",
                    "evidence": EV,
                },
                "consequential_action_decision": {
                    "status": "applicable",
                    "rationale": "Start work is GET navigation. Lineup approval filter is URL-only. No cip write.",
                    "evidence": EV,
                },
            },
        ),
        (
            "ux",
            {
                "path": EV,
                "summary": "Start work is outlined cards. Import a lineup opens unified import. Lineup cases uses HeadlineStrip and a wired approval ScopeBar.",
            },
        ),
        (
            "a11y",
            {
                "path": EV,
                "summary": "Start work cards are real links. Scope chips are buttons. Keyboard/axe full pass not this session.",
            },
        ),
        (
            "rendered",
            {
                "path": EV,
                "url": "http://localhost:3000/brief",
                "viewports": ["1280x800"],
            },
        ),
        (
            "content",
            {
                "path": EV,
                "summary": "Verb is Import a lineup. Steward queue copy names failure type. Lineup strip uses live plan-line counts.",
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
                    "/lineup/cases",
                ],
                "create_promo_href": "/promotions?propose=1",
                "lineup_plan_lines": 1647,
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
                "product": "StartWorkPanel cards + LineupContainer HeadlineStrip/ScopeBar",
            },
        },
    )
    event("node.stage", {"to": "validate"})
    event(
        "node.stage_note",
        {
            "stage_note": (
                "Implementer validate: Start work outlined cards; Import a lineup opened unified=1; "
                "Create promotion plan href retained. Lineup cases 7309 planned units / 1647 lines; "
                "fake trend removed. BACKLOG-189/190. Independent GOV-008 not recorded. Do not complete."
            )
        },
    )
    event("node.lease.release", {})
    run(["--run", RUN, "--actor", ACTOR, "status", "--node", NODE])


if __name__ == "__main__":
    main()
