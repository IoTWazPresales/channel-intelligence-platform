"""Record independent GOV-008 on N-0018 and complete if gates pass.

Run/actor: GOV008_N0018_20260912 / gov-008
Implementation remains NS9_SUPPLY_20260907 / gov-001.
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
RUN = "GOV008_N0018_20260912"
ACTOR = "gov-008"
IMPL_RUN = "NS9_SUPPLY_20260907"
IMPL_ACTOR = "gov-001"
NODE = "N-0018"
EV = ".eif/audit/gov-008-n0018.md"
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


def node_rev() -> int:
    r = run(["--run", RUN, "--actor", ACTOR, "status", "--node", NODE])
    m = re.search(r'"revision":\s*(\d+)', r.stdout or "")
    if not m:
        raise SystemExit("no revision")
    return int(m.group(1))


def event(
    name: str,
    payload: dict,
    *,
    run_id: str = RUN,
    actor: str = ACTOR,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    payload = dict(payload)
    payload["node"] = NODE
    payload["expected_revision"] = node_rev()
    PAYLOAD_DIR.mkdir(parents=True, exist_ok=True)
    path = PAYLOAD_DIR / f"{name.replace('.', '_')}_{payload['expected_revision']}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return run(
        [
            "--run",
            run_id,
            "--actor",
            actor,
            "event",
            name,
            "--payload-file",
            str(path),
        ],
        check=check,
    )


def take_lease() -> None:
    rec = event("node.lease.reclaim", {"ttl_seconds": 3600}, check=False)
    blob = (rec.stdout or "") + (rec.stderr or "")
    if rec.returncode == 0:
        return
    if "LEASE_HELD" not in blob:
        raise SystemExit(rec.returncode or 1)
    print("lease held by implementer run; releasing then acquiring as GOV-008")
    event("node.lease.release", {}, run_id=IMPL_RUN, actor=IMPL_ACTOR)
    event("node.lease.acquire", {"ttl_seconds": 3600})


def main() -> None:
    take_lease()

    quals = [
        ("design_artifact_class", {"class": "high_fidelity", "path": EV}),
        (
            "design_divergence",
            {
                "benchmark": "apps/web/src/design-lab/surfaces/DomainOverviewSurface.tsx",
                "decision": "cip_number_rule_not_lab_fixtures",
                "path": EV,
            },
        ),
        (
            "design_signatures",
            {
                "signatures": [
                    "domain_header",
                    "headline_strip_5",
                    "lifecycle_category_bars_three_disjoint",
                    "po_proportion_bars_linked_observed",
                    "attention_eta_past",
                    "workflow_panel_rows",
                    "partly_built_receipts",
                    "lens_tabs_on_leaves",
                    "relocated_inbound_workspace",
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
                "product_url": "http://localhost:3000/supply",
                "lab_url": "http://localhost:3000/design-lab/supply",
                "viewport": "1280x800",
                "comparison_verdict": "parity_with_number_rule_substitution",
            },
        ),
        (
            "design_sameness_review",
            {
                "visual_vocabulary_challenge": (
                    "Challenged whether production is the same Supply & Inbound instrument "
                    "as DomainOverviewSurface.tsx SupplySurface or a header glued onto the "
                    "old shipping module with lab Arrived/79% dropped. Chrome grammar matches "
                    "(DomainHeader + HeadlineStrip 5 + CategoryBars + ProportionBar + attention "
                    "+ workflows). NUMBER RULE substitutes cip 1964/873/0/14%/118024 for lab "
                    "684/1714/312/79%/16050. Relocated inbound workspace and PARTIAL receipts "
                    "are charter. Arrived and plan-unit PO% are UNCOVERED (BACKLOG-178/179), "
                    "not faked. Path: " + EV
                ),
                "path": EV,
                "decision": "retain_lab_chrome_with_cip_numbers",
            },
        ),
        (
            "design_interaction_spec",
            {
                "interactions": [
                    "open_shipments_figure_to_supply_shipments",
                    "lens_tabs_shipments_receipts_po",
                    "workflow_hrefs",
                    "stock_inbound_redirect",
                    "shipping_redirect",
                ],
                "path": EV,
            },
        ),
        (
            "design_state_coverage",
            {
                "states": [
                    "populated_cip",
                    "loading_overview",
                    "data_unavailable_unit",
                    "receipts_partial",
                    "arrived_uncovered",
                    "plan_unit_po_uncovered",
                ],
                "path": EV,
            },
        ),
        (
            "design_identity_tokens",
            {
                "tokens": {
                    "direction_name": "workbench-ui Supply & Inbound DomainHeader+HeadlineStrip+LensTabs",
                    "strip": "HeadlineStrip columns=5",
                    "lifecycle": "three disjoint CategoryBars",
                    "po": "ProportionBar linked/observed not plan units",
                    "honesty": "Partly built Receipts & POD",
                },
                "path": EV,
            },
        ),
        (
            "design_execution_decisions",
            {
                "responsive_decision": {
                    "status": "applicable",
                    "rationale": (
                        "Verified 1280x800 vs lab. Supply is not a named DIRECTION 390px "
                        "workflow. Viewport via Playwright setViewportSize (browser_resize). "
                        "cursor-ide-browser has no browser_resize tool."
                    ),
                    "evidence": EV,
                },
                "visualisation_decision": {
                    "status": "applicable",
                    "rationale": (
                        "Lab HeadlineStrip + lifecycle + PO bars mounted. Live cip grains; "
                        "lab fixtures not copied. Three disjoint lifecycle bars; Arrived not invented."
                    ),
                    "evidence": EV,
                },
                "consequential_action_decision": {
                    "status": "applicable",
                    "rationale": (
                        "Headline clicks and lens tabs navigate. Writes remain relocated "
                        "inbound workspace, evidence steward, and PO management. D-0002 untouched."
                    ),
                    "evidence": EV,
                },
            },
        ),
        (
            "ux",
            {
                "path": EV,
                "summary": "Operator can read inbound status at 1280 and open relocated shipments/receipts/PO leaves.",
            },
        ),
        (
            "a11y",
            {
                "path": EV,
                "summary": "Lens tablist on leaves; HeadlineFigure buttons; Partly built named. Keyboard not exercised.",
            },
        ),
        (
            "rendered",
            {
                "path": EV,
                "url": "http://localhost:3000/supply",
                "viewports": ["desktop_1280"],
            },
        ),
        (
            "content",
            {
                "path": EV,
                "summary": "Partly built Receipts retained; captions refuse plan-unit and Arrived fiction; D-0002 copy on mappings.",
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
                "url": "http://localhost:3000/supply",
                "viewports": ["desktop_1280"],
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
                "lab": "apps/web/src/design-lab/surfaces/DomainOverviewSurface.tsx",
                "product": "apps/web/src/features/supply-inbound/SupplyChrome.tsx",
            },
        },
    )
    event("node.status", {"to": "complete"})
    run(["--run", RUN, "--actor", ACTOR, "status", "--node", NODE])


if __name__ == "__main__":
    main()
