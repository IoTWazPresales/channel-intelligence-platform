"""Record independent GOV-008 on N-0023 and N-0024 and complete if gates pass.

Run/actor: GOV008_N0023_N0024_20260914 / gov-008
Implementation remains NS11_RAIL_20260913 and NS12_NAV_DEST_20260913 / gov-001.
Windows: every event uses --payload-file. Does not edit product source.
Does not touch D-0002.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
PROG = REPO / ".eif/runtime/programme/program.py"
RUN = "GOV008_N0023_N0024_20260914"
ACTOR = "gov-008"
EV = ".eif/audit/GOV008_N0023_N0024_20260914/independent-rendered-review.md"
PAYLOAD_DIR = Path(__file__).resolve().parent / "payloads"


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


def node_rev(node: str) -> int:
    r = run(["--run", RUN, "--actor", ACTOR, "status", "--node", node])
    m = re.search(r'"revision":\s*(\d+)', r.stdout or "")
    if not m:
        raise SystemExit(f"no revision for {node}")
    return int(m.group(1))


def event(name: str, payload: dict, *, node: str) -> subprocess.CompletedProcess[str]:
    payload = dict(payload)
    payload["node"] = node
    payload["expected_revision"] = node_rev(node)
    PAYLOAD_DIR.mkdir(parents=True, exist_ok=True)
    path = PAYLOAD_DIR / f"{node}_{name.replace('.', '_')}_{payload['expected_revision']}.json"
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


def record_n0023() -> None:
    node = "N-0023"
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
                    "sticky_pin_during_scroll_data_group",
                    "no_guide_rail",
                    "leaf_3px_bar_plus_weight",
                    "collapsed_active_no_fill_after_blur",
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
                "comparison_verdict": "lab_rail_tokens_ported_sticky_pin_verified",
            },
        ),
        (
            "design_sameness_review",
            {
                "visual_vocabulary_challenge": (
                    "Challenged whether production CapabilityRail is still the old selected-fill "
                    "instrument. Independent 1280 measure matches LabShell: raised paper header, "
                    "3x15 r=2 bar, transparent leaf fill, 34px indent, no guide rail. Sticky "
                    "pin-during-scroll verified by expanding all groups and scrolling Data. "
                    "Path: " + EV
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
                    "collapsed_active_icon_weight_only_after_blur",
                    "sticky_pin_during_data_scroll",
                ],
                "path": EV,
            },
        ),
        (
            "design_state_coverage",
            {
                "states": [
                    "expanded_active",
                    "collapsed_active",
                    "sticky_pin_during_scroll",
                    "mobile_drawer_390",
                ],
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
                    "collapsed_active": "transparent after blur + primary icon + weight 600",
                },
                "path": EV,
            },
        ),
        (
            "design_execution_decisions",
            {
                "responsive_decision": {
                    "status": "applicable",
                    "rationale": "Verified 1280x800 vs lab and 390x844 drawer. Same tokens.",
                    "evidence": EV,
                },
                "visualisation_decision": {
                    "status": "applicable",
                    "rationale": "No charts. Selection is bar+weight, not fill.",
                    "evidence": EV,
                },
                "consequential_action_decision": {
                    "status": "applicable",
                    "rationale": "Rail still navigates; chevron still expands. D-0010 Option A kept.",
                    "evidence": EV,
                },
            },
        ),
        (
            "ux",
            {
                "path": EV,
                "summary": "Active leaf is bar+weight; expanded group reads as a container; collapsed-active is weaker after blur; Data header pins while leaves scroll under.",
            },
        ),
        (
            "a11y",
            {
                "path": EV,
                "summary": "Chevron aria-label expand/collapse retained; colour is not the only leaf signal (bar+weight). Keyboard not a full pass.",
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
                "path": EV,
                "summary": "No label/href/order change this node. D-0010 Option A already accepted on ledger.",
            },
        ),
    ]
    for dim, evidence in quals:
        event("node.quality", {"dim": dim, "state": "pass", "evidence": evidence}, node=node)
    event(
        "node.verification",
        {
            "kind": "rendered",
            "state": "pass",
            "evidence": {
                "path": EV,
                "url": "http://localhost:3000/stock?lens=cover",
                "viewports": ["desktop_1280", "drawer_390"],
                "sticky_pin": "verified_data_group_scroll",
            },
        },
        node=node,
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
        node=node,
    )
    event("node.status", {"to": "complete"}, node=node)


def record_n0024() -> None:
    node = "N-0024"
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
                    "systematic_enum_rail_brief_workflows_figures",
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
                "comparison_verdict": "label_matches_final_url_limitations_non_live_controls",
            },
        ),
        (
            "design_sameness_review",
            {
                "visual_vocabulary_challenge": (
                    "Challenged whether five named fixes were the whole mismatch class. "
                    "Independent enum of rail leaves, brief hrefs, hub Workflows, and headline "
                    "figures. No additional live mismatch of the Lineup-cases-to-hub class. "
                    "Getting-started is retired to /brief. Market Planning lineup and PO chip "
                    "source-only. Path: " + EV
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
                "states": [
                    "attention_blotter",
                    "planning_hub",
                    "admin_hub",
                    "supply_hub",
                    "cover_filtered",
                ],
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
                    "status": "not_applicable",
                    "rationale": "Destination URLs; not a 390 named workflow this node.",
                    "evidence": EV,
                },
                "visualisation_decision": {
                    "status": "applicable",
                    "rationale": "Cover under-4w is a real filled filter chip, not a relabel.",
                    "evidence": EV,
                },
                "consequential_action_decision": {
                    "status": "applicable",
                    "rationale": "Clicks land on the named job. No nav restructure. D-0010 Option A kept.",
                    "evidence": EV,
                },
            },
        ),
        (
            "ux",
            {
                "path": EV,
                "summary": "A labelled control opens the job it names. Cover under-4w chip is the union filter. Some same-class links were source-only this session.",
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
                "clicks": [
                    "/lineup/cases",
                    "/admin/users/list",
                    "/admin/mappings",
                    "/stock?lens=cover&status=under4w",
                    "/supply/shipments",
                    "/commercial-planner",
                    "/stock?lens=execution",
                ],
            },
        ),
        (
            "content",
            {
                "path": EV,
                "summary": "Inbound action_label Open Supply · Shipments. Failed-imports steward-queue label unchanged. Under 4w chip filled after cover-breach click.",
            },
        ),
    ]
    for dim, evidence in quals:
        event("node.quality", {"dim": dim, "state": "pass", "evidence": evidence}, node=node)
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
        node=node,
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
        node=node,
    )
    event("node.status", {"to": "complete"}, node=node)


def main() -> None:
    record_n0023()
    record_n0024()
    run(["--run", RUN, "--actor", ACTOR, "status", "--node", "N-0023"])
    run(["--run", RUN, "--actor", ACTOR, "status", "--node", "N-0024"])


if __name__ == "__main__":
    main()
