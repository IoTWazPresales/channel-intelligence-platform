# Overnight run 2026-10-23 (unattended)

Branch `feat/ns-2-brief-nav-collapse`. Start HEAD `57b3a98e`. Read this file first on resume and continue
from the last unit not marked DONE.

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
| A. Chart fixes | N-0114 (feature, R2, ui) | PARKED at definition, no code changed, lease released |
| B. Data model under the builder | N-0115 (inception, R3, api+schema, depends on N-0114) | DISCOVERY STARTED (read only), no ledger events |
| C. The builder | N-0116 (feature, R3, ui+api+data_migration, depends on N-0115) | NOT STARTED |

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

## Morning handoff

- **Done:** start check, three nodes, Unit B discovery of catalog, handlers, engine and callers (above),
  the `db_on.py` helper.
- **Not done:** all of Unit A (spec, code, renders), Unit B design panel, compiler, parity and timings,
  all of Unit C. No product code changed, no migrations, nothing waiting for "apply to cip", no tests
  run, no services restarted (nothing to deploy).
- **Proposed decisions:** none yet.
- **Where it stopped:** Unit A at definition, before the spec. Resume: rerun the Unit A definition
  subagent, then implementation, then verification under `RUN-20261023-N0114-VER`.

