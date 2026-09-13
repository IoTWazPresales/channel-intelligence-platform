"""Implementer quality + validate + lease.release for N-0023. Do not complete (GOV-008 pending)."""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
PROG = REPO / ".eif/runtime/programme/program.py"
RUN = "NS11_RAIL_20260913"
ACTOR = "gov-001"
NODE = "N-0023"
EV = ".eif/audit/NS11_RAIL_20260913/implementer-evidence.md"
D10 = ".eif/audit/NS11_RAIL_20260913/D0010_RAIL_VS_TABS.md"


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
    run(
        [
            "--run",
            RUN,
            "--actor",
            ACTOR,
            "event",
            name,
            "--payload",
            json.dumps(payload),
        ]
    )


def main() -> None:
    event("node.lease.heartbeat", {"ttl_seconds": 3600})
    event(
        "evidence.add",
        {
            "id": "EV-N0023-IMPL",
            "provenance": "implementation-observation",
            "path": EV,
            "note": "N-0023 LabShell rail port + D-0010 proposed; Playwright 1280/390; no browser_cdp; no cip writes",
        },
    )

    quals = [
        ("design_artifact_class", {"class": "high_fidelity", "path": EV}),
        (
            "design_divergence",
            {
                "benchmark": "apps/web/src/design-lab/shell/LabShell.tsx Rail",
                "decision": "port_lab_tokens_keep_production_badges_persist_footer",
                "path": EV,
            },
        ),
        (
            "design_signatures",
            {
                "signatures": [
                    "raised_expanded_header_background_paper",
                    "sticky_group_header",
                    "no_guide_rail",
                    "leaf_3px_bar_plus_weight",
                    "collapsed_active_no_fill",
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
                "product_url": "http://localhost:3000/stock?lens=cover",
                "lab_url": "http://localhost:3000/design-lab/stock?lens=cover",
                "viewport": "1280x800",
                "drawer_viewport": "390x844",
                "comparison_verdict": "lab_rail_tokens_ported",
            },
        ),
        (
            "design_sameness_review",
            {
                "visual_vocabulary_challenge": (
                    "Challenged whether CapabilityRail was still the old selected-fill instrument. "
                    "After port it is the same rail treatment as LabShell (raised paper, sticky, "
                    "3px bar, no guide rail). Remaining deltas are production-only and chartered: "
                    "badges, localStorage persist, session footer, testids, label wrap. D-0010 IA "
                    "is proposed, not implemented. Path: " + EV
                ),
                "path": EV,
                "decision": "retain_lab_rail_tokens",
            },
        ),
        (
            "design_interaction_spec",
            {
                "interactions": [
                    "domain_header_navigates",
                    "chevron_expand_collapse_without_navigate",
                    "leaf_bar_marks_active",
                    "collapsed_active_icon_weight_only",
                ],
                "path": EV,
            },
        ),
        (
            "design_state_coverage",
            {
                "states": ["expanded_active", "collapsed_active", "collapsed_inactive", "mobile_drawer"],
                "path": EV,
            },
        ),
        (
            "design_identity_tokens",
            {
                "tokens": {
                    "direction_name": "LabShell rail after 130189e",
                    "leaf_bar": "3x15 r=2 primary",
                    "expanded_header": "background.paper sticky z=2",
                    "collapsed_active": "transparent + primary icon + weight 600",
                },
                "path": EV,
            },
        ),
        (
            "design_execution_decisions",
            {
                "responsive_decision": {
                    "status": "applicable",
                    "rationale": "1280 aside and 390 drawer both measured; same tokens.",
                    "evidence": EV,
                },
                "visualisation_decision": {
                    "status": "applicable",
                    "rationale": "No charts. Selection is bar+weight, not fill.",
                    "evidence": EV,
                },
                "consequential_action_decision": {
                    "status": "applicable",
                    "rationale": "Rail still navigates; chevron still expands. D-0010 IA not implemented.",
                    "evidence": EV,
                },
            },
        ),
        (
            "ux",
            {
                "path": EV,
                "summary": "Active leaf is bar+weight; expanded group reads as a container; collapsed-active is weaker by design.",
            },
        ),
        (
            "a11y",
            {
                "path": EV,
                "summary": "Chevron aria-label expand/collapse retained; selected still on ListItemButton; colour is not the only leaf signal (bar+weight). Keyboard not a full pass this session.",
            },
        ),
        (
            "rendered",
            {
                "path": EV,
                "url": "http://localhost:3000/stock?lens=cover",
                "viewports": ["desktop_1280", "drawer_390"],
            },
        ),
        (
            "content",
            {
                "path": D10,
                "summary": "No label/href/order change. D-0010 proposed Option A keep expansion.",
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
                "url": "http://localhost:3000/stock?lens=cover",
                "viewports": ["desktop_1280", "drawer_390"],
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
                "lab": "apps/web/src/design-lab/shell/LabShell.tsx",
                "product": "apps/web/src/features/shell/CapabilityRail.tsx",
            },
        },
    )
    event("node.stage", {"to": "validate"})
    event(
        "node.stage_note",
        {
            "stage_note": (
                "Implementer validate: LabShell rail tokens ported; collapsed-active recorded; "
                "D-0010 proposed Option A; vitest 4; Playwright 1280+390. Independent GOV-008 not recorded."
            )
        },
    )
    event("node.lease.release", {})
    run(["status", "--node", NODE])
    run(["frontier"])


if __name__ == "__main__":
    main()
