"""Generates finding.defer payloads (f_01.json ...) for open items from the 2 Nov review and batches 1-3."""
import json
import pathlib

root = pathlib.Path(__file__).resolve().parent
R = ".eif/audit/REVIEW_20261102/"
F = R + "FINDINGS.md"
B1, B2, B3, DP = R + "BATCH1_REPORT.md", R + "BATCH2_REPORT.md", R + "BATCH3_REPORT.md", R + "DEPLOY_20261102.md"

items = [
    ("N-0119", f"Mapping memory (source_definition.column_mapping_memory: header mappings, remembered sheets, cleared tokens) and the alias tables carry no tenant and are reused automatically across tenants (review M5; M5c not fixed). Options need a decision: tenant_id on source_definition and alias tables with a backfill, or a per-tenant namespace in the JSON. One tenant on cip today. See {B2} Needs Warren 1 and {F} M5."),
    ("N-0119", f"AUD-PARI test facts still on cip: 3 shipped-turned-open facts (ids 99964, 99966, 99968; 30 units) leaked by tests/test_data_integrity_audit.py count in open units. Cleanup script scripts/ops/remove_leaked_test_shipment_facts.py exists (dry run default); plan batch2/AUD_PARI_CLEANUP_PLAN.md needs a clone proof, then Warren's go. See {B2} Needs Warren 4 and {F} Minor."),
    (None, f"D-0132 status mismatch: the ledger records it accepted by Warren on 26 Oct (EIF 2778) but .eif/DECISIONS.md lists it PROPOSED (written that way by batch 2 on instruction). Not changed tonight (standing instruction: do not confirm D-0132). See {B2} Needs Warren 2."),
    ("N-0119", f"Partial shipment remainder: the open quantity not shipped is flagged but the line closes as closed_shipped; Warren to decide the remainder state (open line for the difference, or a closed_cancelled state). See {B2} Needs Warren 5."),
    ("N-0119", f"Orphan retire where the replacement has another quantity is left open and flagged; the alternative is to retire anyway. Warren's call. See {B2} Needs Warren 6."),
    ("N-0116", f"Migrated v1 saved reports keep the v1 rows, untruncated and in the handler order (batch 2 reading of the code comment); if they should take the v2 cap and order it is one condition. Warren's call. See {B2} Needs Warren 7 and {F} M3."),
    ("N-0119", f"M2 rule for an undated complete-book file (closed facts stay closed, no second open fact for a line already open under another key) is a proposed rule Warren can overrule. See {B1} M2 and {B2} Needs Warren 8."),
    ("N-0119", f"cst_alias_era_derive still counts closed shipment rows for first-movement dates (min pod_date, min ship_confirm_date); batch 1 left it as evidence of first movement. Warren's call. See {B1} 'Not filtered, and why' and {B2} Needs Warren 8."),
    ("N-0119", f"0050 downgrade limit: an orphaned open Shipped-sheet line with a future confirm date whose replacement has since closed comes back as shipped; removing the limit needs a column recording the prior state (new migration). See {B1} M1."),
    ("N-0119", f"import_job_delete_figures._shipments (restores only from the same tenant's earlier loads) has no test of its own; covered only by the existing delete-figures tests. See {B2} Not done."),
    ("N-0115", f"catalog_for_tenant_cached has no TTL (a changed tenant model is not seen until restart). Untouched. See {B2} Not done and {F} Minor."),
    ("N-0115", f"On-hand for a product absent from the latest report is a null row, not 0. Untouched. See {B2} Not done and {F} Minor."),
    ("N-0119", f"A cancelled remainder can be labelled closed_shipped; not fixable from the data (the sheets do not say why a line is gone). The partial-shipment flag is the part that can be done. See {B2} Not done."),
    (None, f"API lint not run: ruff is not installed in apps/api/.venv (batches 1 and 2); web lint was run (0 errors, 50 warnings). See {B1} Gates and {B2} Gate."),
    (None, f"tests/test_shipment_resolved_entities.py::test_branch_bill_to_variants_resolve_same_root_distributor catches every exception including its own failed assert and skips with 'DB not available'; on cip_test the resolver returns None for two aliases of one distributor, so the skip hides a failure (the 25th skip). Not investigated. See {B2} 'Test counts and mutation checks'."),
    (None, f"Batch 2 tests not mutation-checked: four sheet-memory tests (remember and store round trip, nothing remembered, unchanged workbook, memory from before the seen list) and the cleanup script's delete-and-audit test. See {B2} Test counts."),
    ("N-0114", f"Decision for Warren: dual axis chart now starts at the top 10 categories (it plotted every category before), with Show all and the Sort menu. Keep, or start with all? See {B3} Needs Warren 1."),
    ("N-0114", f"Decision for Warren: comparison chart over categories uses a two-entry legend and one colour for current bars (previously one colour and a legend pair per category). Keep? See {B3} Needs Warren 2."),
    ("N-0119", f"Decision for Warren: tiles keep their query while a vessel is selected; the alternative is to follow the filters the click clears (tiles then change on every click). See {B3} Needs Warren 3."),
    ("N-0114", f"Decision for Warren: editor default top N (columns 10, ranked bars 15, the renderer's own); the other way round is one number. See {B3} Needs Warren 4."),
    ("N-0119", f"Decision for Warren: the multi-vessel cluster label at the busiest port is not drawn at 1280 on the fixture map (no free place); draw it over a port name, or use a smaller cluster label? See {B3} Needs Warren 5 and 'What the renders showed that I did not fix'."),
    ("N-0114", f"Dual axis at 390 px: ten long names are drawn as angled one-line ticks cut to the same first words; a dual axis cannot use horizontal bars. Full name is in the tick title and the data table. Not fixed. See {B3} Not done."),
    ("N-0114", f"Four fixture widgets (a line, an area, a scatter and one starter) have the first x label or origin tick sharing a corner with the y-axis '0'. Not fixed. See {B3} Renders."),
    ("N-0114", f"Render limits: no render on cip data, none by a person, no real-device or screen reader check; every visual and starter in N-0114/N-0116 not independently seen light and dark at both widths; side panel minimum 360 px source-only; hover and keyboard state of the new charts not captured. See {F} (UNABLE_TO_RENDER) and {B3} 'What these renders cannot show'."),
    ("N-0114", f"LABEL_HEIGHT_PX >= 49 and the render metrics are not mutation-checked; design-lab surfaces (own chart primitives) were not changed. See {B3} Not done."),
    (None, f"Invalid batch 3 API run: Postgres went into recovery mode during a full suite run started alongside the render harness on cip_test (28 failed, 3,583 passed); cause not established. Rule: run the full suite alone. See {B3} Gate."),
    ("N-0115", f"avg/min/max measures are declared only for sell-out and sell-through units and average prices; none for shipments, stock, returns, lineup or CPOR (N-0115 requirement not met). See {F} N-0115 table, row 'Measures with sum/count/distinct/avg/min/max'."),
    ("N-0115", f"Sell-in and recorded-price measures cannot be verified (both tables empty on cip); sales value is still a decision (D-0117, D-0118). Lineup drops 53 lines / 553 units with no product. See {F} N-0115 E7 row."),
    ("N-0115", f"No RLS policy checks tenant on any table (all policies are product-line only), so tenant isolation rests on the application; non-owner RLS, concurrency and HTTP timing were not tested (role cip is the table owner). dashboard, dashboard_widget, saved_report, cpor_case and report_schedule have no RLS on cip. See {F} N-0115 table and N-0116 table."),
    ("N-0115", f"Parity: no per-caller parity matrix was re-run for 'every existing caller keeps working with a test'; only the full suite. See {F} N-0115 table, row 'Parity'."),
    (None, f"R3 independence not reached for N-0114/N-0115/N-0116 and the shipment fixes: same model family as the writer; another model or attested consult is needed before any closure. No node can close on current evidence. See {F} section 3."),
    ("N-0116", f"Starters: cover, restock, value and open-case measures still refuse (ASSERTED from E10; not re-run by the review); quality dimensions on N-0116 all still pending. See {F} N-0116 table."),
    ("N-0116", f"Scheduled delivery: no delivery and no failure row on 5 Oct and 26 Oct for the only enabled schedule on cip (cause not established); delivered on 2 Nov 09:00. See {F} N-0116 table, row 'Scheduled reports keep sending'."),
    ("N-0119", f"Migration 20261101_0049 downgrade drops port_condition with its history. See {F} On the water, row 'Voyage columns (0049) and backfill'."),
    ("N-0119", f"Closed-line reader grep for B1 covered apps/api/app only; scripts, packages and web-side readers were not searched. See {F} B1 and {B1} reader list."),
    (None, f"Clones still in Postgres (the guard denies DROP DATABASE): cip_otw, cip_retire, cip_retire2, cip_retire3 and any later clones; Warren to drop by hand. Not verified tonight. See docs/memory/CURRENT.md (2 Nov entries) and {F} section 'Audit events'."),
    ("N-0119", f"Deploy of 2 Nov: no authenticated API call or logged-in render after the restart (unauthenticated GETs return 401); the brief's route /shipping/one does not exist in apps/web/src/app (only /shipping, /supply/shipments, /supply/shipments/[id]); tracked changes outside the commit (apps/web/next-env.d.ts, apps/web/tsconfig.builder-e2e.json) and untracked ops probes remain. See {DP} Steps 0 and 4."),
    (None, "EIF runtime: the programme node id counter lags the real ids (state ids.node = 5), so an event node.add with no id fails NODE_EXISTS on N-0006; ids N-0117 to N-0119 were assigned by hand. Fix in the EIF repo, not CIP. Found by RUN-20261102-OVERNIGHT."),
]

for i, (node, note) in enumerate(items, 1):
    payload = {"code": "DOES_NOT_FIT", "note": note}
    if node:
        payload["node"] = node
    (root / f"f_{i:02d}.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
print(len(items))
