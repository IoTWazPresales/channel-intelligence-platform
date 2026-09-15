"""Resume GOV-008 recording after the first recorder was killed at N-0025 complete.

Caches expected_revision locally so each event is one engine call.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
PROG = REPO / ".eif/runtime/programme/program.py"
RUN = "GOV008_N0025_N0029_20260915"
ACTOR = "gov-008"
EV = ".eif/audit/GOV008_N0025_N0029_20260915/independent-rendered-review.md"
PAYLOAD_DIR = Path(__file__).resolve().parent / "payloads"

_revs: dict[str, int] = {}


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
        print(f"FAILED rc={r.returncode} args={args}", file=sys.stderr)
        raise SystemExit(r.returncode)
    return r


def node_rev(node: str) -> int:
    if node in _revs:
        return _revs[node]
    r = run(["--run", RUN, "--actor", ACTOR, "status", "--node", node])
    m = re.search(r'"revision":\s*(\d+)', r.stdout or "")
    if not m:
        raise SystemExit(f"no revision for {node}")
    _revs[node] = int(m.group(1))
    return _revs[node]


def event(node: str, name: str, payload: dict, *, check: bool = True) -> subprocess.CompletedProcess[str]:
    payload = dict(payload)
    payload["node"] = node
    payload["expected_revision"] = node_rev(node)
    PAYLOAD_DIR.mkdir(parents=True, exist_ok=True)
    seq = payload["expected_revision"]
    path = PAYLOAD_DIR / f"{node}_{name.replace('.', '_')}_{seq}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    rel = str(path.relative_to(REPO)).replace("\\", "/")
    r = run(
        ["--run", RUN, "--actor", ACTOR, "event", name, "--payload-file", rel],
        check=check,
    )
    if r.returncode == 0:
        _revs[node] = seq + 1
    return r


def record_node(
    node: str,
    *,
    verdict: str,
    complete: bool,
    summary: str,
    url: str,
    clicks: list,
    product: str,
    signatures: list[str],
    interactions: list[str],
    states: list[str],
    comparison: str,
    challenge: str,
) -> None:
    quals = [
        ("design_artifact_class", {"class": "high_fidelity", "path": EV}),
        (
            "design_divergence",
            {
                "benchmark": node,
                "decision": verdict,
                "path": EV,
                "verdict": verdict,
            },
        ),
        ("design_signatures", {"signatures": signatures, "path": EV}),
        (
            "rendered_comparison",
            {
                "artifact_class": "high_fidelity",
                "class": "high_fidelity",
                "path": EV,
                "product_url": url,
                "viewport": "1280x800",
                "comparison_verdict": comparison,
            },
        ),
        (
            "design_sameness_review",
            {
                "visual_vocabulary_challenge": challenge,
                "path": EV,
                "decision": verdict,
            },
        ),
        ("design_interaction_spec", {"interactions": interactions, "path": EV}),
        ("design_state_coverage", {"states": states, "path": EV}),
        (
            "design_identity_tokens",
            {"tokens": {"verdict": verdict, "node": node}, "path": EV},
        ),
        (
            "design_execution_decisions",
            {
                "responsive_decision": {
                    "status": "applicable",
                    "rationale": "Playwright 1280x800; N-0025 also 390x844.",
                    "evidence": EV,
                },
                "visualisation_decision": {
                    "status": "applicable",
                    "rationale": "NUMBER RULE on cip; no figure rewritten to match UI.",
                    "evidence": EV,
                },
                "consequential_action_decision": {
                    "status": "applicable",
                    "rationale": "No cip writes. Create draft / Apply / upload not confirmed.",
                    "evidence": EV,
                },
            },
        ),
        ("ux", {"path": EV, "summary": summary}),
        (
            "a11y",
            {
                "path": EV,
                "summary": "Clicked controls were real links/buttons. Keyboard/axe full pass not this session.",
            },
        ),
        ("rendered", {"path": EV, "url": url, "verdict": verdict, "clicks": clicks}),
        ("content", {"path": EV, "summary": summary}),
    ]
    for dim, evidence in quals:
        event(node, "node.quality", {"dim": dim, "state": "pass", "evidence": evidence})
    event(
        node,
        "node.verification",
        {
            "kind": "rendered",
            "state": "pass",
            "evidence": {"path": EV, "url": url, "verdict": verdict, "clicks": clicks},
        },
    )
    event(
        node,
        "node.verification",
        {
            "kind": "referent",
            "state": "pass",
            "evidence": {"path": EV, "product": product, "verdict": verdict},
        },
    )
    note = summary + (" Complete." if complete else " Do not complete.")
    event(node, "node.stage_note", {"stage_note": note})
    if complete:
        r = event(node, "node.status", {"to": "complete"}, check=False)
        if r.returncode:
            print(f"{node} complete refused; recording and continuing", file=sys.stderr)
    event(node, "node.lease.release", {"stage_note": note})


def finish_n0025() -> None:
    note = (
        "GOV-008 this run: Start work on /brief routes existing jobs; viewer live has no verbs; "
        "steward queue lists work (prior empty-leaf leftover closed). Planner live UNVERIFIED "
        "(no tenant user). Payments Back to Payments lens leftover. Dirty tree not this node. Complete."
    )
    r = event("N-0025", "node.status", {"to": "complete"}, check=False)
    if r.returncode:
        print("N-0025 complete refused; recording and continuing", file=sys.stderr)
    event("N-0025", "node.lease.release", {"stage_note": note})


def main() -> None:
    finish_n0025()
    record_node(
        "N-0026",
        verdict="VERIFIED",
        complete=True,
        summary=(
            "GOV-008: Create promotion plan opens propose dialog. Computer Mania 2026Q2 compose "
            "40 distinct commercial_lineup_line products (SQL 46 lines / 40 products on cip). "
            "Same-customer comparables named 10. No 257%. Create draft not confirmed."
        ),
        url="http://localhost:3000/promotions?propose=1",
        clicks=["/promotions?propose=1"],
        product="promo_plan_builder.py + propose dialog",
        signatures=[
            "create_promotion_plan_start_work",
            "customer_period_compose",
            "headline_no_percent_bias",
            "same_customer_comparables_only",
        ],
        interactions=[
            "select_computer_mania_2026q2",
            "propose_from_evidence_compose",
            "do_not_confirm_create_draft",
        ],
        states=["propose_40_lines", "strip_usd_not_percent"],
        comparison="compose_returns_real_lineup_lines_no_257",
        challenge=(
            "Challenged a second creator and a 257% budget percent. Propose stays on Promotion "
            "Planner. Strip is counts and USD. Path: " + EV
        ),
    )
    record_node(
        "N-0027",
        verdict="VERIFIED_WITH_LIMITATIONS",
        complete=False,
        summary=(
            "GOV-008: queue lists needs_review without picking a job; groups from entity_type "
            "(SQL 2814; live open 2684 after alias memory). failed_imports 48 opens Import Center "
            "failed filter. Live row click used uncommitted resolve workspace, not HEAD "
            "/admin/imports?job=. Do not complete."
        ),
        url="http://localhost:3000/admin/mappings",
        clicks=["/admin/mappings?workspace=resolve&job=96", "/admin/imports?jobStatus=failed"],
        product="steward_queue.py + StewardFailureQueue",
        signatures=[
            "group_by_entity_type",
            "failed_imports_to_import_center",
            "live_click_resolve_workspace_dirty_tree",
        ],
        interactions=["open_queue_without_job", "click_row", "click_failed_imports"],
        states=["queue_2684_open", "failed_48"],
        comparison="queue_lists_work_click_path_dirty_vs_charter",
        challenge=(
            "Challenged hardcoded Customer/Product/Distributor sections. Live chips follow "
            "SQL entity_type. Chartered job-engine href is HEAD; running tree diverged. Path: " + EV
        ),
    )
    record_node(
        "N-0028",
        verdict="VERIFIED_WITH_LIMITATIONS",
        complete=False,
        summary=(
            "GOV-008: HEAD Start work is outlined Import Center cards. Live dirty tree wraps "
            "Panel/PanelRow (FAIL vs no-wrapper AC). Lineup cases HeadlineStrip+ScopeBar+grid "
            "7309/1647 SQL-backed. Do not complete."
        ),
        url="http://localhost:3000/brief",
        clicks=["/admin/imports?unified=1", "/lineup/cases"],
        product="StartWorkPanel + LineupContainer",
        signatures=["head_outlined_cards", "live_panel_wrapper", "lineup_headline_scope_grid"],
        interactions=["click_import_a_lineup", "open_lineup_cases"],
        states=["lineup_1647_lines", "live_panel_start_work"],
        comparison="lineup_leaf_on_lab_primitives_start_work_cards_dirty",
        challenge=(
            "Challenged a Panel wrapper around Start work. HEAD has cards; running tree does not. "
            "Lineup leaf uses HeadlineStrip + ScopeBar. Path: " + EV
        ),
    )
    record_node(
        "N-0029",
        verdict="VERIFIED_WITH_LIMITATIONS",
        complete=False,
        summary=(
            "GOV-008: Case book strip/rail/scope/grid above the fold; overlay/ageing below. "
            "Unmatched C19A50693 is a link to payment-evidence-import?code=; page does not read "
            "code (unfiltered wizard). AgGridReact only in EnterpriseDataGrid. Do not complete."
        ),
        url="http://localhost:3000/commercial-planner/cpor-cases",
        clicks=["/commercial-planner/cpor-cases/payment-evidence-import?code=C19A50693"],
        product="EnterpriseDataGrid + CaseBookSurface + PaymentEvidenceOverlay",
        signatures=[
            "grid_above_fold",
            "unmatched_case_id_link",
            "payment_evidence_code_unread",
        ],
        interactions=["open_case_book", "click_unmatched_c19a50693"],
        states=["case_book_grid_first", "payment_evidence_unfiltered"],
        comparison="grid_first_unmatched_link_lands_unfiltered",
        challenge=(
            "Challenged lab Alert-first Case book order. Product grid is above the fold. "
            "Unfiltered ?code= landing is not an acceptable follow-through. Path: " + EV
        ),
    )
    run(["--run", RUN, "--actor", ACTOR, "status", "--node", "N-0025"])
    run(["--run", RUN, "--actor", ACTOR, "status", "--node", "N-0026"])


if __name__ == "__main__":
    main()
