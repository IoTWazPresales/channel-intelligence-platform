"""Implementer quality + validate + lease.release for N-0029. Do not complete (GOV-008 later)."""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
PROG = REPO / ".eif/runtime/programme/program.py"
RUN = "NS17_GRID_CASEBOOK_20260915"
ACTOR = "gov-001"
NODE = "N-0029"
EV = ".eif/audit/NS17_GRID_CASEBOOK_20260915/implementer-evidence.md"
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
            "id": "EV-N0029-IMPL",
            "provenance": "implementation-observation",
            "path": EV,
            "note": "N-0029 EnterpriseDataGrid text selection + Case book grid-first; Playwright 1280; no cip write; no GOV-008",
        },
    )

    quals = [
        ("design_artifact_class", {"class": "high_fidelity", "path": EV}),
        (
            "design_divergence",
            {
                "benchmark": "Case book working grid before overlay; community clipboard in one wrapper",
                "decision": "enterprise_datagrid_text_select_casebook_grid_first",
                "path": EV,
            },
        ),
        (
            "design_signatures",
            {
                "signatures": [
                    "enable_cell_text_selection",
                    "case_book_strip_scope_grid_first",
                    "unmatched_case_id_panelrow_href",
                    "settlement_workspace_uncovered",
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
                "product_url": "http://localhost:3000/commercial-planner/cpor-cases",
                "viewport": "1280x800",
                "comparison_verdict": "grid_before_overlay_unmatched_rows_are_links",
            },
        ),
        (
            "design_sameness_review",
            {
                "visual_vocabulary_challenge": (
                    "Challenged copying lab Alert-first Case book order because product overlay "
                    "pushed the working grid below the fold. Path: " + EV
                ),
                "path": EV,
                "decision": "strip_scope_grid_then_overlay",
            },
        ),
        (
            "design_interaction_spec",
            {
                "interactions": [
                    "open_case_book",
                    "click_unmatched_historical_case_id",
                    "land_payment_evidence_import",
                ],
                "path": EV,
            },
        ),
        (
            "design_state_coverage",
            {
                "states": [
                    "case_book_304_rows",
                    "unmatched_c19a50693_link",
                    "settlement_desk_not_opened",
                ],
                "path": EV,
            },
        ),
        (
            "design_identity_tokens",
            {
                "tokens": {
                    "direction_name": "case book",
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
                    "rationale": "Named 1280: Case book strip, scope, grid, overlay order.",
                    "evidence": EV,
                },
                "visualisation_decision": {
                    "status": "applicable",
                    "rationale": "Live open book R4.4m / 74 ended; overlay after grid.",
                    "evidence": EV,
                },
                "consequential_action_decision": {
                    "status": "applicable",
                    "rationale": "Unmatched click is GET to existing steward. No cip write. No mint cpor_case.",
                    "evidence": EV,
                },
            },
        ),
        (
            "ux",
            {
                "path": EV,
                "summary": "Case book working grid is above overlay. Unmatched Case IDs are links into payment-evidence import.",
            },
        ),
        (
            "a11y",
            {
                "path": EV,
                "summary": "Unmatched rows are real links. Grid text selection is native. Keyboard/axe full pass not this session.",
            },
        ),
        (
            "rendered",
            {
                "path": EV,
                "url": "http://localhost:3000/commercial-planner/cpor-cases",
                "viewports": ["1280x800"],
            },
        ),
        (
            "content",
            {
                "path": EV,
                "summary": "Caption names settlement half. Unmatched copy still says not minted as cpor_case.",
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
                "url": "http://localhost:3000/commercial-planner/cpor-cases",
                "clicks": [
                    "/commercial-planner/cpor-cases/payment-evidence-import?code=C19A50693",
                ],
                "open_book": "R4.4m",
                "ended": 74,
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
                "product": "EnterpriseDataGrid text selection + CaseBookSurface grid-first + PaymentEvidenceOverlay href",
            },
        },
    )
    event("node.stage", {"to": "validate"})
    event(
        "node.stage_note",
        {
            "stage_note": (
                "Implementer validate: Case book strip/scope/grid before overlay; unmatched C19A50693 "
                "opened payment-evidence-import?code=. EnterpriseDataGrid enableCellTextSelection. "
                "Settlement workspace UNCOVERED. BACKLOG-191–196. Independent GOV-008 not recorded. Do not complete."
            )
        },
    )
    event("node.lease.release", {})
    run(["--run", RUN, "--actor", ACTOR, "status", "--node", NODE])


if __name__ == "__main__":
    main()
