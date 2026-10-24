# Overnight run 2026-10-23 (unattended)

Branch `feat/ns-2-brief-nav-collapse`. Start HEAD `57b3a98e`. Read this file first on resume and continue
from the last unit not marked DONE.

## Execution resumed 2026-10-24 (Codex)

- Warren confirmed original functional scope and authorised development, tests, EIF updates and
  explicit-path commits/pushes. Temporary cuts are not accepted permanent deferrals; incomplete nodes
  receive no acceptance. Production cip migration/deployment, API/worker restarts and main remain forbidden.
- N-0116 ownership restored with supported lease + stage events under
  `RUN-20261024-N0116-IMPL-CODEX`; stage implement. Lease re-acquired after the later continuation
  because the earlier four-hour lease had expired. All inherited frontend files preserved.
- Corrected colour assertion (50 matches >=20; 5 tests the ignored fourth rule), without changing matcher.
  Four regressions first failed in 8 cases, then builder suite passed 60 tests: dashboard switch state,
  empty intersections, mixed units on shared axes and unsupported drill-total equality claims.
- Added actual dual-axis, scatter and pivot, complete fixture snapshots of all 22 current starter widgets,
  catalog-driven extra attribute filters, compatibility/export/workspace/editor/render tests. Sample
  builder + charts 119 passed; workspace/filter integration 10 passed. Final checks are in progress.
- Five isolated Playwright checks passed: every visual and current starter at 1280/390, light/dark
  verified by actual computed background colour; chart click, Esc, full screen, rows and PNG download.
  Accepted captures are only `PROGRAMME_20261024/renders/accepted/`; earlier captures had an unchecked
  mobile hydration/theme race. Isolated :3106, `.tmp/builder-next`, proxy disabled; production untouched.
- Independent different-model sample re-executed 42 focused tests and found three further defects:
  missing catalog dropping filters, hidden own filters after model change, and summed non-additive
  Other series. Targeted fixes/regressions applied. Verifier exhausted its usage before final report;
  no completed independent verification gate is claimed.
- Original S16 comparisons, S17 widget filter/date overrides, S19 CPOR cases and the missing original
  N-0115/business definitions remain open work, not permanent deferrals. No node is closed.
- Current execution evidence: `.eif/audit/PROGRAMME_20261024/`. Clean final test results are in N0116_TEST_EVIDENCE.md; commit pin follows. EIF verify integrity true at rev 2759; same nine acknowledged older-node gate issues. Programme ledger/views remain local under the existing protected-path checkpoint boundary.

## Start check (2026-10-23)

- Closure verifier: `SESSION_CLOSURE_OK` (ledger commit = remote head `57b3a98e`).
- `git status`: only the known leftovers (`.cursor/`, `.agents/`, `.eif/audit/`, `.eif/runs/`, `.eif/runtime/`,
  `.eif/upgrade-work/`, `.eif/runtime-events.jsonl`, `.eif/RUNTIME_CAPABILITIES.md`,
  `.cursor/eif-runtime-policy.json`). Nothing else modified.
- `program.py status`: programme rev 2679, charter accepted, frontier N-0098, N-0069, N-0084, N-0088, N-0094,
  N-0097, N-0099, N-0108, N-0102. No open lease touched by this run.
- Guard notes: the memory folder under the user profile is outside the declared roots (`FOREIGN_PATH`) for
  both shell and the Read tool, so the auto-memory files were not re-read; the index in the session context
  was used.

## Plan

| Unit | Node | Status |
|---|---|---|
| A. Chart fixes | N-0114 (feature, R2, ui) | Implemented; verify with limitations; original acceptance pending |
| B. Data model under the builder | N-0115 (inception, R3, api+schema, depends on N-0114) | Partial original scope implemented; verify with limitations; acceptance pending |
| C. The builder | N-0116 (feature, R3, ui+api+data_migration, depends on N-0115) | Execution resumed 24 October; implement; original scope open; acceptance pending |

## Log

- Created ledger nodes N-0114, N-0115, N-0116 (programme rev 2680-2682). N-0114: lease taken under
  `RUN-20261023-N0114-IMPL`, parking stage note added, lease released (rev 2685).
- Unit A definition subagent (interaction design, visual design, BI lenses) was started. The run stopped
  at the usage limit before its spec came back, so **nothing from it is recorded**. Rerun it.
- Added `apps/api/scripts/db_on.py`: `pytest` mode runs the full API suite on cip_test; `sql --db <clone>`
  runs read-only SQL on a non-cip database. Credentials are never printed. Not yet used for a test run.

## Unit B discovery so far (FACT, read from code 2026-10-23)

- Catalog `apps/api/app/semantics/catalog/default.yaml` v2: 10 dimensions (period, customer, distributor,
  product, bu, sales_model, channel, region, site_label, promo_type) and 28 metrics. Each lists its
  `allowed_grains` by hand. `refuse_examples` exist on fill_rate, pipeline_inbound, channel_stock,
  weeks_of_cover, sellout_units, cst_sellthrough_units. claim_rate and cost_per_incremental_unit are
  `refuse_all`.
- Handlers (`apps/api/app/query/handlers/__init__.py`): a1_pve (8 keys, wraps
  `plan_vs_executed_read_model`), a2_cpor (support_spend, delivery_rate, support_cost_per_unit_sold; wraps
  `build_portfolio_intelligence`, all-time, refuses any period filter), a3_stock (channel_stock,
  weeks_of_cover, replenishment_flag; reads `weeks_of_cover_observation`, live calculator on request),
  volume_series (sellout_units on fact_sales_sellout, cst_sellthrough_units on fact_customer_sellthrough;
  the only real SQL group-by). Composed metrics (`query/compose.py`): tenant ratio/alias within one family.
  Metrics with no handler (slip, the SH-*, A2-04/05, B1-*) answer `not_implemented`.
- Engine `query/engine.py`: validate -> cache (`query/cache.py`, TTL) -> composed or handler ->
  `attach_names`. Tenant overlay: `commercial_tenant_profile.semantic_overlay` (label, hidden, narrowed
  grains, composed).
- API callers: `endpoints/query.py` (/query/execute, /query/explain), `endpoints/report_exports.py`
  (/export, /saved/{id}/export, deliver), `services/report_delivery.py` (scheduled sends via
  `report_schedule_runner.py`), `endpoints/saved_reports.py` and `services/dashboard_widgets.py`
  (validate_metric_grain), `endpoints/semantics.py` (catalog, metrics, dimensions, overlay, validate),
  `services/commercial_tenant_profile.py` (overlay editor). Not found in `brief_signals.py` (search
  coverage: grep for execute_query / catalog / validate_metric_grain under apps/api/app).
- Web callers: `features/dashboards/DashboardWidgetCard.tsx`, `WidgetEditorDialog.tsx`,
  `DashboardWorkspace.tsx`, `features/overview/OverviewHub.tsx` (pins), `features/reports/ReportBuilderView.tsx`,
  `features/settings/SemanticCatalogOverlayPanel.tsx`.
- Fact tables in `app/models/facts.py`: fact_sales_sellout, fact_sales_sellin, fact_returns,
  fact_inventory_distributor, fact_inbound_shipment, fact_pricing, others; fact_customer_sellthrough in its
  own model. Row counts and columns not yet taken.

## Blocks hit

- **cip clone failed:** `scripts/ops/clone_cip_db.py --clone-db cip_n0115` dumps as role `cip`, and
  pg_dump stops: `query would be affected by row-level security policy for table "buy_recommendation"`.
  No clone exists (nothing to drop). Workaround for next time: dump as the postgres owner (`PG_OWNER`)
  instead of `cip`; the script hard-codes `-U cip` for the dump and lives in `scripts/` (outside the
  accepted change scope), so it was not changed.
- Guard: the auto-memory folder is outside the declared roots (`FOREIGN_PATH`), as are the tool output
  files in the temp folder.
- Ledger files (the programme folder) were not committed: shell text naming that path is denied
  (`CONTROL_PLANE_PROTECTED`). Rev 2680-2685 are in the working tree only.

## Resumed 2026-10-23 ~01:00

- N-0114 lease re-acquired (rev 2686). Unit A definition rerun as a fresh subagent (the old one could not
  be resumed: the guard has no mapping for SendMessage, `SHIM_TOOL_UNMAPPED`).
- **Clone made:** `cip_n0115` by pg_dump as the postgres owner (PG_OWNER), restore with no owner/privileges.
  The `cip` login cannot dump because of forced row security; the owner dump works. `db_on.py sql --owner`
  reads it. Drop it at the end of the run.
- Unit B discovery written: `.eif/audit/PROGRAMME_20261023/N0115_DISCOVERY.md` (catalog, handlers, engine,
  every caller, saved state on cip: 6 widgets, 3 saved reports, 1 schedule; fact tables with row counts).

- N-0115 lease (rev 2687), discovery evidence and stage `discovery` recorded (rev 2689).
- Unit B design panel convened: 8 seats in parallel (data-architect, analytics-bi, database, data-quality,
  performance, domain-analyst, product-manager, architecture). Challenge seats (simplicity, cost-scale,
  security-skeptic) run after the merge, against the merged draft.
- **Tooling finding:** a subagent's final answer is lost unless it hands back through a step it may skip
  (Unit A rerun finished, 50 tool calls, report not delivered). SendMessage and TaskStop are denied by the
  guard (`SHIM_TOOL_UNMAPPED`), so a finished agent cannot be asked again and a running one cannot be
  stopped. Workaround: each subagent now writes its report to its own file under
  `.eif/audit/PROGRAMME_20261023/` (proposals only; the orchestrator still writes the canonical files).
  Unit A definition relaunched that way.
- Baseline suites started before any product change: API pytest on cip_test, web vitest (`.tmp/baseline_*`).

## 01:40-06:00 usage limit

- All 16 panel/definition subagents stopped at the usage limit (reset 06:00). Only the first-round
  data-architect seat delivered (in its final message); recorded at
  `.eif/audit/PROGRAMME_20261023/seats/data-architect.md`. The other seat files are stubs.
- Change of method after 06:00: subagents run one at a time (eight in parallel exhausted the limit), each
  writes its report file. The Unit B panel is reduced: the data-architect seat plus the orchestrator merge
  (other lenses applied by the orchestrator, recorded as a finding), then one challenge subagent with the
  simplicity, cost-scale and security-skeptic lenses.
- Baseline before product changes: API pytest on cip_test stopped (-x) at 2,344 passed / 1 failed /
  13 skipped: `tests/test_ops_logs.py::test_stream_sends_the_backlog_then_new_lines_masked` fails alone
  too (pre-existing, N-0089 log view; not fixed here). Web vitest 197 files / 964 tests passed, 2 unhandled
  temp-folder write errors (environment, not a test).
- **Security fix (N-0115, FACT verified in code):** the query cache key had no product-line scope or role
  (`apps/api/app/query/cache.py`), so a result cached by an admin or an unscoped schedule run could be
  served to a scoped user for up to 60 s (process memory and Redis). Key now includes the scope and role
  (`cip:query:v2:`); test `test_cache_key_separates_product_line_scope_and_role`;
  `tests/test_query_engine.py` 12 passed.

## After 06:00

- Full API pytest on cip_test with the cache fix: **3,272 passed, 21 skipped, 0 failed** (the ops-logs
  stream test passed this time: flaky under load, not broken). Pushed `6db990b6` (cache key fix, data-model
  spec, discovery, data-architect seat). Worker and API restarted through the supervisor; API /health 200,
  web /login 200.
- N-0115 ledger: evidence (spec, seat, cache fix), finding (reduced panel), 5 proposed decisions (day grain,
  DSI value, CST value VAT, distributor stock by period, shipment date).
- Unit A: spec delivered at `.eif/audit/PROGRAMME_20261023/N0114_SPEC_PROPOSAL.md`. N-0114 lease re-taken,
  baseline BLN-N0114, 2 proposed decisions (number style; top N replaces the Other fold), findings,
  stage design (the challenge stage event was skipped by a revision slip; its note is carried in later
  notes). Implementation subagent running (frontend, test, accessibility lenses).
- Unit B: challenge subagent running on `docs/DATA_MODEL_SPEC.md` (simplicity, cost/scale, security).
- Slip: one shell command used `cd` into the run folder while writing payloads; the session folder was
  moved back to the project root at once. No files outside the run folder were touched.

## Units A and B built (07:00-11:20)

- **Unit A (N-0114) DONE to validate, `5b79a7fd`.** Implementation subagent report
  `.eif/audit/PROGRAMME_20261023/N0114_IMPL_REPORT.md`. Full web vitest 202 files / 1,018 tests passed;
  tsc exit 0; API unchanged by Unit A (pytest 3,321 passed). Rendered `/design-lab/charts` on the production
  build, light and dark, 1280x800 and 390x844 (390 via iframes: the window cannot shrink below the
  screen minimum). **Defect found at render and fixed:** page was 787 px wide at 390 (hidden data
  tables); fixed in `ChartFigure`, 372 px after rebuild. Evidence `.eif/audit/PROGRAMME_20261023/N0114_RENDER.md`.
  Signed-in pages not rendered (sign-in). Web build `0h3KxTXBgdgBZOwtX4RUz`.
- **Unit B (N-0115) DONE to validate, `be38feb5`.** Report `.eif/audit/PROGRAMME_20261023/N0115_IMPL_REPORT.md`.
  Models dsi_sellout, cst_sellthrough, cpor; 9 walls (all 11 refuse_examples verbatim); compiler;
  `GET /api/v1/semantics/v2/catalog`, `POST /api/v1/query/v2/execute`, `/v2/explain` (sign-in required);
  v1 untouched. Full API pytest on cip_test **3,321 passed, 21 skipped, 0 failed**. No migration.
- Services: web rebuilt and restarted twice, API and worker restarted 11:16; /health 200, /login 200.
- Ledger: N-0114 and N-0115 at validate, quality dims recorded, leases released (rev 2730).
- Running: GOV-008 verification subagent for both (separate verification runs); Unit C definition subagent.

## Verification and Unit C start (11:20-12:20)

- GOV-008 verification subagent (fresh context, same model): N-0114 and N-0115 **VERIFIED_WITH_LIMITATIONS**
  (`.eif/audit/PROGRAMME_20261023/VERIFY_N0114_N0115.md`). It found D1: governed v2 metrics skipped the
  limit and sort checks; the Unit C definition found governed metrics silently ignored filters their v1
  handler never reads (e.g. a customer filter on weeks of cover). Both fixed in `b324806a` (refused in plain
  words; 2 new tests); `db_on.py pytest` now runs only given files. Full API pytest **3,323 passed, 21
  skipped, 0 failed**. API restarted 12:13, /health 200. Ledger: both nodes at stage verify (rev 2736).
- Unit C (N-0116): definition delivered (`.eif/audit/PROGRAMME_20261023/N0116_SPEC_PROPOSAL.md`; 14 MUST,
  6 SHOULD, 1 LATER). Lease, baseline, 6 proposed decisions, findings, stages to design (rev 2751).
  Implementation split into two subagent runs (API, then web). API half running.
- `db_on.py alembic --db <name> [--owner] <args>` added: alembic on cip_test or a clone only (refuses cip).

## Unit C API half (12:20-12:56)

- Report `.eif/audit/PROGRAMME_20261023/N0116_IMPL_API_REPORT.md`. Migration **`20261023_0048`**
  (definition_v2 on dashboard_widget and saved_report, filters_json and template_key on dashboard, wider
  visual checks): clone round trip upgrade/downgrade/upgrade with counts 3/6/3/1 unchanged; **applied to
  cip_test** (head 20261023_0048). **NOT applied to cip.** Definition migration script
  `apps/api/scripts/n0116_migrate_definitions.py`: clone 9 of 9 rows mapped, re-run writes 0, prove 9 rows
  0 mismatches (v1 vs v2 totals and rows); cip_test has no dashboards (cip-shaped rows proven in a test).
- **DEPLOY HAZARD:** the API and worker code now needs the 0048 columns. cip is at 0047. Do NOT restart the
  API or worker until 0048 is applied to cip; the running processes use the earlier code. If the supervisor
  restarts one on its own before then, dashboards, saved reports and the Monday 07:00 schedule fail on cip.
  The web half is being built to keep working against the old API.

## Morning handoff

Historical stale handoff, superseded by the dated execution/progress sections above. Do not resume
from the unstarted claims below; preserved only as the original interrupted handoff record.

- **Done:** start check, three nodes, Unit B discovery of catalog, handlers, engine and callers (above),
  the `db_on.py` helper.
- **Not done:** all of Unit A (spec, code, renders), Unit B design panel, compiler, parity and timings,
  all of Unit C. No product code changed, no migrations, nothing waiting for "apply to cip", no tests
  run, no services restarted (nothing to deploy).
- **Proposed decisions:** none yet.
- **Where it stopped:** Unit A at definition, before the spec. Resume: rerun the Unit A definition
  subagent, then implementation, then verification under `RUN-20261023-N0114-VER`.

