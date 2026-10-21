"""N-0110: implement run through validate, then a different run for verification. No accept, no complete.
Lease was acquired under RUN-20261014-N0110-IMPL at node revision 0."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
NODE = "N-0110"
OUT = Path(__file__).resolve().parent
PRODUCT = "5ae106ad"
GAP = "apps/api/app/services/channel_intelligence/customer_stock_gap.py"
GRAIN = "apps/api/app/services/imports/parsers/customer_sell_through_grain.py"
INGEST = "apps/api/app/services/imports/customer_sell_through.py"
MIG = "apps/api/alembic/versions/20261014_0037_customer_stock_gap.py"
PROOF = ".eif/audit/PROGRAMME_20261014/N0110_CLONE_PROOF.md"
PANEL = "apps/web/src/app/(app)/admin/cst-steward/CstStockGapSection.tsx"
TOGGLE = "apps/web/src/app/(app)/admin/imports/CstSalesOnlyToggle.tsx"
TESTS = "apps/api/tests/test_customer_stock_gap.py"
DBTEST = "apps/api/tests/test_customer_stock_gap_db.py"
GRAINTEST = "apps/api/tests/test_cst_period_grain.py"


def cli(run: str) -> list[str]:
    return [sys.executable, str(ROOT / ".eif/runtime/programme/program.py"), "--run", run, "--actor", "gov-001"]


def revision(run: str) -> int:
    result = subprocess.run(cli(run) + ["status", "--node", NODE], capture_output=True, text=True, cwd=ROOT)
    if result.returncode != 0:
        raise SystemExit(result.stderr or result.stdout)
    text = result.stdout
    start = text.rfind("{", 0, text.find(f'"id": "{NODE}"'))
    return int(json.loads(text[start:])["revision"])


def emit(run: str, event: str, body: dict, *, node_scoped: bool = True, tag: str = "") -> None:
    body = dict(body)
    if node_scoped:
        body["node"] = NODE
        body["expected_revision"] = revision(run)
    path = OUT / f"_n0110_{event.replace('.', '_')}{tag}.json"
    path.write_text(json.dumps(body), encoding="utf-8")
    result = subprocess.run(cli(run) + ["event", event, "--payload-file", str(path)], capture_output=True, text=True, cwd=ROOT)
    print(run, event, tag, result.returncode, (result.stdout or "").strip(), (result.stderr or "").strip()[-600:])
    if result.returncode != 0:
        raise SystemExit(1)


PRESERVE = {
    "cst-fact-rows": "kept: fact_customer_sellthrough rows, units and reported on-hand unchanged (1823 rows, 6159 units, 28812 on-hand on cip)",
    "cst-read-models": "kept: weekly/monthly read models; legacy rows keep NULL grain and are read by period_type",
    "distributor-derived-stock": "kept: distributor derived stock and its 10 percent band untouched",
}


def main() -> None:
    impl = "RUN-20261014-N0110-IMPL"
    ver = "RUN-20261014-N0110-VER"
    emit(
        impl,
        "baseline.add",
        {
            "id": "BLN-N0110",
            "provenance": "implementation-observation",
            "tree_hash": "bc598f04",
            "path": INGEST,
            "observed_behavior": (
                "Customer sell-through rows stored reported_soh but no expected position or gap. Every row date was "
                "moved to its Monday and typed weekly, so two days in one week shared a source key and the last won. "
                "A file with units and no on-hand loaded silently. In transit and on order were not read. The "
                "distributor side already had a derived-stock flag with a 10 percent band."
            ),
            "latent_capabilities": list(PRESERVE),
            "preservation": PRESERVE,
        },
        node_scoped=False,
    )
    emit(impl, "node.baseline", {"baseline_ref": "BLN-N0110", "preservation": PRESERVE})
    emit(impl, "node.stage", {"stage": "discovery", "stage_note": "N-0079 closed. CST facts carry reported_soh; fact_inbound_shipment has pod_date, line_state and resolved_customer_id; the distributor derived-stock formula is the pattern."}, tag="_1")
    emit(impl, "node.stage", {"stage": "challenge", "stage_note": "Warren 2026-10-12: sales-only only when the upload is marked; highlight is an editable setting in absolute units; no 10 percent variance. Parser Monday-snapping loses day rows."}, tag="_2")
    emit(impl, "node.stage", {"stage": "design", "stage_note": "Grain fields on staging and fact rows; derived customer_stock_position recomputed after apply; tenant setting stock_gap_highlight_units; CST steward Stock gap tab; sales-only checkbox on both upload paths."}, tag="_3")
    emit(impl, "node.stage", {"stage": "implement", "stage_note": f"Product commit {PRODUCT}. 20261014_0037 on cip after clone proof; positions recomputed on cip (701, 314 compared)."}, tag="_4")
    decisions = (
        "A week with a number and year but no known customer calendar keeps period_start_date as the ISO Monday of that number "
        "and year, as a sort and source-key bucket only; week_start_date stays empty. A date in a column whose header names a "
        "week is a stated week start, not a sale day. Reversible: grain module only.",
        "The gap is compared per customer and product, summed across the customer's sites for each report period. Units sold "
        "count when a period ends after the previous stock report and by this one (so a sales-only upload in between counts). "
        "Receipts count when shipped, POD-dated after the previous report's end and by this report's end, and matched to the customer.",
        "Until Warren sets a number, the highlight threshold defaults to 1 unit (any whole-unit gap is highlighted). It is "
        "editable in CST steward > Stock gap and stored in the tenant profile.",
        "Day grain is read from flat files (row sale date or a one-day file-name range). Pivoted, multi-sheet, wide and "
        "month-to-date layouts keep weeks or months. All layouts are refused without on-hand unless marked sales-only.",
    )
    for i, statement in enumerate(decisions, 1):
        emit(impl, "decision.add", {"scope": NODE, "origin": "implementation", "status": "proposed", "statement": statement}, node_scoped=False, tag=f"_{i}")
    for path, note in (
        (GAP, "N-0110 expected position and gap beside reported on-hand; customer_stock_position recomputed after apply."),
        (GRAIN, "N-0110 period grain: day / week (number + year; start only with a known calendar) / month."),
        (INGEST, "N-0110 sales-only rule: units without on-hand refused unless the upload is marked sales-only."),
        (MIG, "N-0110 migration 20261014_0037 (grain, in transit, on order, customer_stock_position with product-line RLS)."),
        (PROOF, "N-0110 clone proof of 20261014_0037 on cip_n0110, then applied to cip. Fact and staging numbers unchanged; 701 positions, 314 compared."),
        (PANEL, "N-0110 CST steward Stock gap tab: unit gap on every compared row, editable absolute-unit highlight, recompute."),
        (TOGGLE, "N-0110 sales-only checkbox on Import Center and CST batch upload."),
    ):
        emit(impl, "evidence.add", {"path": path, "note": note, "provenance": "implementation-observation"}, tag="_" + Path(path).stem)
    tests = (
        "pytest 245 passed on touched CST areas plus 119 on period read models (cip_test, incl. 1 DB test); "
        "vitest 13 passed on touched files; web tsc exit 0; next lint 0 errors on changed files."
    )
    dims = (
        ("testing", "pass", TESTS, tests),
        ("observability", "pass", GAP, "A recompute failure after apply is logged and added to the apply summary errors; it never undoes the load. Each position carries computed_at and the import job that reported it."),
        ("data_integrity", "pass", DBTEST, "Reported on-hand and units are never rewritten (DB test asserts fact on-hand unchanged). Positions are derived and replaced per customer and product, never duplicated. Unmatched and open shipments stay out."),
        ("backup_recovery", "pass", GAP, "customer_stock_position is derived: Recompute (or recompute_all_customer_stock_positions) rebuilds it from facts and shipments. Downgrade drops it and the new columns without touching existing data."),
        ("migration_safety", "pass", PROOF, "Clone proof on cip_n0110: upgrade, downgrade, upgrade and recompute with fact rows 1823, units 6159, on-hand 28812, staging 43472 unchanged; then applied to cip. cip_test round trip clean."),
        ("ux", "pass", PANEL, "Stock gap tab: Flag, Customer, Customer code, SKU, Product, Report period, Reported on-hand, Expected position, Gap, Previous on-hand, Delivered (POD, matched), Units sold since, In transit, On order, What it can mean. Threshold field with save, Highlighted only, Recompute, counts line."),
        ("a11y", "pass", PANEL, "Highlight is not colour only: a Flag column says Over threshold and the gap cell is bold. Threshold input is labelled with helper text; sales-only checkbox has a label and aria-describedby. Tests query by role. No axe run."),
        ("content", "pass", GAP, "Gap words: Short: stock not delivered, lost, or sold outside the file (with an in-transit hint); Over: a receipt CIP does not have, a return, or overlapping periods. Refusal: This file has units sold and no on-hand column."),
    )
    for dim, state, path, rationale in dims:
        emit(impl, "node.quality", {"dim": dim, "state": state, "evidence": {"path": path, "summary": rationale[:200]}, "rationale": rationale}, tag="_" + dim)
    emit(
        impl,
        "node.quality",
        {
            "dim": "rendered",
            "rationale": "UNABLE_TO_RENDER in the browser: /admin/cst-steward?tab=stock-gap on 127.0.0.1:3000 redirected to the sign-in form and no account password may be entered by the agent. Web build ucxLixhJsBuG8OzYirAmF is live; /api/v1/cst-steward/stock-gap answers 401 without a session (an unknown path answers 404). Component tests cover the tab.",
        },
        tag="_rendered",
    )
    emit(impl, "node.stage", {"stage": "validate", "stage_note": "Built and tested. Rendered check blocked by sign-in. Verification is a different run."}, tag="_5")
    emit(impl, "node.lease.release", {})
    emit(ver, "node.lease.acquire", {"ttl_seconds": 3600}, tag="_ver")
    emit(ver, "node.verification", {"kind": "behavioral", "state": "pass", "evidence": TESTS}, tag="_b")
    emit(ver, "node.verification", {"kind": "referent", "state": "pass", "evidence": DBTEST, "path": GAP}, tag="_r")
    emit(
        ver,
        "node.stage",
        {
            "stage": "verify",
            "stage_note": (
                "VERIFIED_WITH_LIMITATIONS. Self-verified under RUN-20261014-N0110-VER, different from implementation run "
                "RUN-20261014-N0110-IMPL; same session, same model, not independent. N-0099 does the second look. "
                "Limits: Stock gap tab not rendered in the browser (sign-in); existing fact rows keep NULL grain; shipment "
                "loads do not trigger a recompute (Recompute button); re-uploading an old file can add day rows beside its "
                "old Monday rows; highlight default 1 unit until Warren sets one. Operator acceptance pending."
            ),
        },
        tag="_6",
    )
    findings = (
        "N-0110: re-uploading a file loaded before 20261014_0037 can store day or stated-week rows beside its old Monday-keyed rows (different source keys), so units could count twice. No detection was built.",
        "N-0110: a shipment or POD load does not recompute customer stock positions. Late POD data needs CST steward > Stock gap > Recompute.",
        "N-0110: the 1823 fact rows on cip keep NULL grain; they are read by period_type (all weekly today). Not re-classified.",
        "N-0110: a customer's week calendar is set only through feed profile JSON (week_calendar iso, or fiscal with fiscal_year_start_month). No dedicated control.",
        "N-0110: pivoted, multi-sheet, wide and month-to-date CST files without on-hand are now refused unless marked sales-only; existing feeds of those layouts may need the mark on the next upload.",
        "N-0110: admin imports page.test.tsx has 5 failing historical_lineup mapping tests; the same 5 fail on HEAD before this node.",
    )
    for i, note in enumerate(findings, 1):
        emit(ver, "finding.defer", {"note": note, "code": "DOES_NOT_FIT"}, tag=f"_{i}")
    emit(ver, "node.lease.release", {}, tag="_ver")
    print("done", revision(ver))


if __name__ == "__main__":
    main()
