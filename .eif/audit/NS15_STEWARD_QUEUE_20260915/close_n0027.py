"""Implementer quality + validate + lease.release for N-0027. Do not complete (GOV-008 later)."""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
PROG = REPO / ".eif/runtime/programme/program.py"
RUN = "NS15_STEWARD_QUEUE_20260915"
ACTOR = "gov-001"
NODE = "N-0027"
EV = ".eif/audit/NS15_STEWARD_QUEUE_20260915/implementer-evidence.md"
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
            "id": "EV-N0027-IMPL",
            "provenance": "implementation-observation",
            "path": EV,
            "note": "N-0027 steward queue GROUP BY entity_type; Playwright 1280 job=900 + failed_imports jobStatus=failed; no cip write; no GOV-008",
        },
    )

    quals = [
        ("design_artifact_class", {"class": "high_fidelity", "path": EV}),
        (
            "design_divergence",
            {
                "benchmark": "cross-job steward queue grouped by failure type routing into existing engines",
                "decision": "group_by_entity_type_route_to_job_engines",
                "path": EV,
            },
        ),
        (
            "design_signatures",
            {
                "signatures": [
                    "steward_queue_group_by_entity_type",
                    "job_as_row_provenance",
                    "route_to_existing_dsi_cst_shipment_engines",
                    "failed_imports_to_import_center_failed_filter",
                    "uncovered_types_listed_not_invented",
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
                "product_url": "http://localhost:3000/admin/mappings",
                "viewport": "1280x800",
                "comparison_verdict": "queue_lists_needs_review_and_opens_existing_engine",
            },
        ),
        (
            "design_sameness_review",
            {
                "visual_vocabulary_challenge": (
                    "Challenged a parallel resolver and hardcoded Customer/Product/Distributor sections. "
                    "Queue groups from entity_type in data. Click opens the existing job steward. Path: " + EV
                ),
                "path": EV,
                "decision": "one_queue_leaf_existing_engines",
            },
        ),
        (
            "design_interaction_spec",
            {
                "interactions": [
                    "open_steward_queue_leaf",
                    "filter_by_entity_type_chip",
                    "open_existing_cst_steward_from_row",
                    "open_failed_imports_from_brief",
                ],
                "path": EV,
            },
        ),
        (
            "design_state_coverage",
            {
                "states": [
                    "queue_2814_open_candidates",
                    "type_chips_from_groups",
                    "legacy_mapping_queue_empty",
                    "brief_47_failed_imports",
                    "import_center_failed_filter",
                ],
                "path": EV,
            },
        ),
        (
            "design_identity_tokens",
            {
                "tokens": {
                    "direction_name": "steward queue",
                    "object": "import_entity_mapping_candidate",
                    "group_key": "entity_type",
                },
                "path": EV,
            },
        ),
        (
            "design_execution_decisions",
            {
                "responsive_decision": {
                    "status": "applicable",
                    "rationale": "Named 1280 workflow: mappings leaf to existing job steward; brief failed_imports to Import Center.",
                    "evidence": EV,
                },
                "visualisation_decision": {
                    "status": "applicable",
                    "rationale": "Headline strip is counts (candidates, types, jobs, uncovered). Grouping is SQL GROUP BY.",
                    "evidence": EV,
                },
                "consequential_action_decision": {
                    "status": "applicable",
                    "rationale": "Queue does not accept/reject. Steward hrefs are GET navigation. No cip write.",
                    "evidence": EV,
                },
            },
        ),
        (
            "ux",
            {
                "path": EV,
                "summary": "Steward queue lists needs_review by entity_type. Steward opens existing job engine. failed_imports opens Import Center failed filter.",
            },
        ),
        (
            "a11y",
            {
                "path": EV,
                "summary": "Steward is a real link. Failure-type chips are buttons. Keyboard/axe full pass not this session.",
            },
        ),
        (
            "rendered",
            {
                "path": EV,
                "url": "http://localhost:3000/admin/mappings",
                "viewports": ["1280x800"],
            },
        ),
        (
            "content",
            {
                "path": EV,
                "summary": "Copy: grouped by failure type stored on each candidate, not by import job. Job is provenance. Legacy entity_mapping_queue is D-0002.",
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
                "url": "http://localhost:3000/admin/mappings",
                "clicks": [
                    "/admin/imports?job=900",
                    "/admin/imports?jobStatus=failed",
                ],
                "open_candidates": 2814,
                "failed_imports": 47,
                "failed_imports_href": "/admin/imports?jobStatus=failed",
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
                "product": "steward_queue.py + StewardFailureQueue + brief_signals failed_imports href",
            },
        },
    )
    event("node.stage", {"to": "validate"})
    event(
        "node.stage_note",
        {
            "stage_note": (
                "Implementer validate: steward queue GROUP BY entity_type lists 2814 needs_review on cip. "
                "Steward click opened /admin/imports?job=900. failed_imports opened Import Center jobStatus=failed (47). "
                "BACKLOG-187/188 for re-resolution and non-candidate types. Independent GOV-008 not recorded. Do not complete."
            )
        },
    )
    event("node.lease.release", {})
    run(["--run", RUN, "--actor", ACTOR, "status", "--node", NODE])
    run(["--run", RUN, "--actor", ACTOR, "frontier"])


if __name__ == "__main__":
    main()
