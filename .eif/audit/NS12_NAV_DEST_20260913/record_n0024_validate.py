"""Implementer quality + validate + lease.release for N-0024. Do not complete (GOV-008 later)."""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
PROG = REPO / ".eif/runtime/programme/program.py"
RUN = "NS12_NAV_DEST_20260913"
ACTOR = "gov-001"
NODE = "N-0024"
EV = ".eif/audit/NS12_NAV_DEST_20260913/implementer-evidence.md"
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
            "id": "EV-N0024-IMPL",
            "provenance": "implementation-observation",
            "path": EV,
            "note": "N-0024 label vs destination; Playwright clicks; no browser_cdp; no cip writes",
        },
    )

    quals = [
        ("design_artifact_class", {"class": "high_fidelity", "path": EV}),
        (
            "design_divergence",
            {
                "benchmark": "control label names the job the href must open",
                "decision": "fix_href_keep_ia_add_under4w_filter",
                "path": EV,
            },
        ),
        (
            "design_signatures",
            {
                "signatures": [
                    "rail_lineup_cases_to_workspace",
                    "rail_users_to_list",
                    "cover_breach_to_cover_under4w",
                    "failed_imports_to_steward_queue",
                    "inbound_to_supply_shipments",
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
                "viewport": "desktop",
                "comparison_verdict": "label_matches_final_url",
            },
        ),
        (
            "design_sameness_review",
            {
                "visual_vocabulary_challenge": (
                    "Challenged whether hub landings for Lineup cases / Users & roles were intentional "
                    "IA. Operator: label names the workspace. D-0010 Option A kept (rail+tabs). Path: " + EV
                ),
                "path": EV,
                "decision": "align_href_to_label",
            },
        ),
        (
            "design_interaction_spec",
            {
                "interactions": [
                    "click_rail_leaf",
                    "click_hub_figure",
                    "click_workflows_row",
                    "click_attention_signal",
                    "cover_under4w_chip",
                ],
                "path": EV,
            },
        ),
        (
            "design_state_coverage",
            {
                "states": ["attention_blotter", "planning_hub", "admin_hub", "supply_hub", "cover_filtered"],
                "path": EV,
            },
        ),
        (
            "design_identity_tokens",
            {
                "tokens": {
                    "direction_name": "label equals destination",
                    "under4w": "union of breach and watch chips",
                },
                "path": EV,
            },
        ),
        (
            "design_execution_decisions",
            {
                "responsive_decision": {
                    "status": "na",
                    "rationale": "Destination URLs; not a 390 named workflow this node.",
                    "evidence": EV,
                },
                "visualisation_decision": {
                    "status": "applicable",
                    "rationale": "Cover under-4w is a real filter chip, not a relabel.",
                    "evidence": EV,
                },
                "consequential_action_decision": {
                    "status": "applicable",
                    "rationale": "Clicks must land on the named job. No nav restructure.",
                    "evidence": EV,
                },
            },
        ),
        (
            "ux",
            {
                "path": EV,
                "summary": "A labelled control opens the job it names. Cover under-4w matches the attention grain.",
            },
        ),
        (
            "a11y",
            {
                "path": EV,
                "summary": "Workflows and attention rows remain real links. Headline figures remain buttons. Keyboard full pass not this session.",
            },
        ),
        (
            "rendered",
            {
                "path": EV,
                "url": "http://localhost:3000/brief",
                "viewports": ["desktop"],
            },
        ),
        (
            "content",
            {
                "path": EV,
                "summary": "Inbound action_label Open Supply · Shipments. Failed-imports steward-queue label unchanged. Under 4w chip added.",
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
                    "/lineup/cases",
                    "/admin/users/list",
                    "/admin/mappings",
                    "/stock?lens=cover&status=under4w",
                    "/supply/shipments",
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
                "product": "navConfig + brief_signals + hub figures",
            },
        },
    )
    event("node.stage", {"to": "validate"})
    event(
        "node.stage_note",
        {
            "stage_note": (
                "Implementer validate: enumeration + Playwright clicks for named destinations; "
                "under-4w Cover chip; inbound to Supply shipments. Independent GOV-008 not recorded. Do not complete."
            )
        },
    )
    event("node.lease.release", {})
    run(["status", "--node", NODE])
    run(["frontier"])


if __name__ == "__main__":
    main()
