# Channel Intelligence Platform — Current Context

## Branch
`main`

## Alembic Head
`20260517_0037`

## What Is Working (latest)
- **DSI revalidate** (`POST .../revalidate-distributor-sales-inventory`): dispatches `imports.process_job` to Celery (same as validate); stores `celery_task_id` in `staged_metadata`; frontend polls `/api/v1/imports/jobs/{id}/dsi-progress` via `pollDsiImportPipelineUntilDone` — no 300s HTTP block.
- **DSI steward UX (Option A)**: slim `DsiResolutionPlanToolbar` (refresh, summary chips, plan options ⋮ menu); fourth tab **Region & channel** with flat `DsiRegionChannelTabPanel` (no nested accordions); geo count on tab badge; entity tabs unchanged for distributor/customer/product.
- **DSI region evidence + ISO fallback (D→A→B→C→E)**: `region_evidence` on resolution-plan rows (`dsi_customer_region_evidence.py`); channel values are geographic **hints only** (no channel→region FK); `GET /api/v1/reference/countries` + `POST .../regions/ensure-from-country`; Customers tab **Operating region fallback** (`DsiCountryRegionFallback`, default off); geo tab prefill + register-from-hint; bulk **Apply suggested region** (plan overrides); `docs/DSI_REGION_EVIDENCE_AND_FALLBACK_PLAN.md`.
- **Region & channel tab UX**: `GeoStewardRegisterFromFile` (prefilled code/name from normalized token, one-click register); `DsiChannelGeographicEvidenceSection` (job-level channel→geo hint table with row counts); plan drawer lists per-customer channel hint tokens.
- **Global background tasks** (nav bell): `GET /api/v1/imports/background-tasks` returns only Celery `PENDING`/`STARTED`/`PROGRESS`; terminal states clear `celery_task_id` / `dsi_bulk_task` from `staged_metadata` (pipeline + poll path); `useGlobalBackgroundTasks` stops polling when task list empty; shared progress fetchers for DSI/shipment/bulk.
- **Import jobs list**: `GET /api/v1/imports/jobs` paginated (`items`, `total`, `limit`, `offset`, `has_more`), default `limit=50`, column projection only — no `inferred_schema` / `field_mapping` / `staged_metadata` JSONB.

## What Is Working
- DSI upload: jobs reach `dsi_mapping_ready` with column headers (runs `infer_dsi_job_sync` inline)
- DSI validate: dispatches `imports.process_job` to Celery worker via Redis
- Celery worker receives DSI validate tasks and now processes them end-to-end
- Shipment evidence steward panel: entity resolution for inbound shipment imports
- DSI import job resolution: `ImportStewardCandidateWorkspace` + extracted hooks (`useDsiResolutionPlan`, `useDsiBulkSteward`) and accordions (`DsiResolutionPlanAdvancedAccordion`, `DsiGeoStewardAccordion`, `DsiBulkStewardSection`); orchestration ~430 lines in `DsiImportJobResolutionSection.tsx`; `ShipmentEntityStewardPanel` unchanged
- DSI steward query keys centralised on `DSI_STEWARD_CONFIG` + `invalidateDsiImportJobStewardQueries` / `invalidateDsiCatalogQueries`
- Mappings queue (`/admin/mappings?import_job_id=`) deep-links to import job DSI workspace when candidates exist (no duplicate AG Grid steward)
- Barrel fix: filter logic in `dsiStewardCandidateFilterLogic.ts` (avoids Windows case clash with `DsiStewardCandidateFilters.tsx`)
- All other import flows (shipment evidence, product master, etc.)

## What Was Fixed This Session
**DSI validation was processing 168K rows at ~11 rows/sec (estimated 4+ hours).**
Root cause: 6 per-row DB round-trips + unindexed corroboration scans.

### Round 1 — Corroboration cache (previous session)
**`ShipmentCorroborationCache`** added to `dsi_shipment_corroboration.py`:
Pre-loads all resolved `shipment_evidence_line` data for the file's evidence months
in 2 batch queries. Eliminates N×6 per-row unindexed full-table scans (0.234s each).
Cache load: ~1.2s one-time. Per-row lookup: <1ms.

### Round 2 — Resolution cache (this session)
After the corroboration fix, 6 per-row DB queries remained:
1. `DistributorSourceTokenAlias` alias query (1 query/row)
2. `DimDistributor` full table scan (1 query/row)
3. `CustomerSourceTokenAlias` alias query (1 query/row)
4. `DimCustomer` OPEN_CHANNEL id query (0–1 query/row)
5. `DimCustomer` code lookup (1 query/row)
6. `DimCustomer` name lookup (1 query/row)

**Fix: `DSIResolutionCache`** added to `distributor_sales_inventory.py`:
- Pre-loads `DimDistributor`, `DistributorSourceTokenAlias`, `DimCustomer`,
  `CustomerSourceTokenAlias`, and OPEN_CHANNEL id in ~5 queries before the loop.
- `_resolve_distributor_from_cache(raw, source_id, res_cache)` — zero DB queries
- `_resolve_customer_from_cache(*, source_id, distributor_id, ..., res_cache)` — zero DB queries
- `_shipment_disambiguate_product_id` now accepts optional `corr_cache` — uses in-memory
  lookup for ambiguous product resolution (no more DB scans on the disambig path)
- `_resolve_product` threads `corr_cache` through to `_shipment_disambiguate_product_id`
- `_col(mapping, X)` calls (22/row) replaced with 12 pre-computed variables before the loop
- Steward single-row refresh (`refresh_dsi_staging_line_resolution`) unchanged — still uses DB

**Expected throughput after both caches**: near-zero DB queries per row → ~500+ rows/sec
(from ~11 rows/sec before).

## Previous Session Fixes (still in place)
- `process_import_job_task` wrapped in try/except with `_write_task_level_failure`
- `RawFileMetadata` fetch + `storage.read()` moved inside the main try block in pipeline
- `run_dsi_validate_post_import_orchestration` is a no-op (removed asyncio.run() hang)
- `post_dsi_validate` dispatches `imports.process_job` asynchronously, returns `{async: true}`
- DSI upload always runs `infer_dsi_job_sync` inline (Celery dispatch for infer deferred)
- Frontend DSI validate polling: stops at `validated` or `failed`
- Progress logging every 100 rows in `process_distributor_sales_inventory`

## Known Outstanding
- **No index on `shipment_evidence_line.distributor_id`**: migration ticket needed —
  `CREATE INDEX CONCURRENTLY ix_sel_distributor_id ON shipment_evidence_line(distributor_id)`.
  The caches eliminate per-row scans, but the cache pre-load itself does a full-table scan.
- Customer corroboration cache now includes steward-applied rows (`customer_resolution_status` `resolved` or `resolved_unique`).
- DSI upload Celery dispatch (`imports.infer_dsi`) deferred — currently runs inline.

## Runtime (local dev, no Docker)
- Web: http://localhost:3000 (Next.js, `pnpm dev:web`)
- API: http://localhost:8001 (`pnpm dev:api`)
- Worker: `pnpm dev:worker` (Celery solo pool, Redis on :6379)
- Redis: localhost:6379, Celery broker: redis://localhost:6379/1
- DB: localhost:5432, database `cip`

## DSI Validate Real-Time Progress (this session, continued)

DSI validate now reports detailed progress to the frontend via Celery task state (Redis).

**How it works end-to-end:**
1. `post_dsi_validate` dispatches `imports.process_job` via `send_task`, captures the returned
   `task_id`, and stores it in `job.staged_metadata.celery_task_id` (committed immediately via
   a separate sync session before the worker starts).
2. `process_import_job_task` (now `bind=True`) creates an `_on_progress` closure that calls
   `self.update_state(state='PROGRESS', meta={phase, phase_label, current_row, total_rows, pct})`
   and passes it to `process_import_job_sync`.
3. `process_import_job_sync` passes `on_progress` to `process_distributor_sales_inventory` (only
   for the DSI handler — other handlers unchanged).
4. `process_distributor_sales_inventory` calls `on_progress` at:
   - `"loading_caches"` before corroboration + resolution cache loads
   - `"processing_rows"` after caches load, and every 3 s during the row loop
   - `"building_candidates"` after the loop ends
5. `GET /api/v1/imports/jobs/{job_id}/dsi-progress` reads `staged_metadata.celery_task_id`,
   queries `AsyncResult(task_id).info` from Redis (via `asyncio.to_thread`), and returns the
   current phase/row/pct. Overrides to `phase="complete"` when `stage="validated"`.
6. `staged_metadata` is now included in `GET /jobs/{job_id}` response (`get_job` endpoint).
7. `total_rows` is written to `staged_metadata.dsi_validate_total_rows` before the loop
   (before the row lock) so the progress endpoint has it even without Celery state.

**Frontend:**
- New `DsiValidateProgressPanel.tsx`: PM-style panel with 4-step phase rail, determinate
  LinearProgress (% from Celery), elapsed timer, "In progress" pulsing chip, row count accordion.
- `page.tsx`: New `dsiProgress` query polls `/dsi-progress` at 1500ms while `dsiValidateAsync`.
  Replaces the old plain `Alert + LinearProgress` in step 6 with `DsiValidateProgressPanel`.
  Falls back to `<LinearProgress />` for the brief `dsiValidate.isPending` window.

## P2 DSI intelligence (this branch)
- Duplicate bulk-apply alert removed from `DsiImportJobResolutionSection` (bulk summary only in `DsiBulkStewardSection`; plan apply summary in plan accordion).
- Customer shipment corroboration: cache query accepts `resolved` + `resolved_unique` (steward sets `resolved`).
- Plan rows expose `plan_why` (blockers, rule_path, corroboration_hits); workspace Match column shows shipment corroboration chip.
- Ambiguous product steward uses `DsiEligibleProductPicker` instead of JSON dump.

## P1 DSI Steward Componentisation (web, this branch)
- Renamed `dsiStewardCandidateFilters.ts` → `dsiStewardCandidateFilterLogic.ts`
- New: `dsiSteward.types.ts`, `dsiSteward.config.ts`, `useDsiResolutionPlan.ts`, `useDsiBulkSteward.ts`, `dsiResolutionPlanDisplay.tsx`, `dsiBulkStewardDisplay.ts`, `UnresolvedGeoStewardPanel.tsx`, `DsiGeoStewardAccordion.tsx`, `DsiResolutionPlanAdvancedAccordion.tsx`, `DsiBulkStewardSection.tsx`
- Slimmed `DsiImportJobResolutionSection.tsx`; mappings page deep-link; tests updated (14 resolution section, 2 workspace, 2 mappings)

## DSI resolution tabs + steward drawer (latest)

- **Entity tabs:** Distributors → Customers → Products; lazy-loaded paginated candidates per tab; tab labels show open total + needs-review count; soft upstream nudge on Customers/Products.
- **Steward drawer:** row click toggles selection (shift-click range); Actions column Map/Open/Resolve opens drawer; bottom `DsiMappingStewardPanel` strip removed.
- **Candidates API:** paginated `GET .../distributor-si-candidates` with `entity` filter per tab.
- **Plan:** scoped to current tab page via `candidate_ids`; see `DSIPlanBuildContext` in `docs/DSI_RESOLUTION_PERFORMANCE.md`.

## DSI steward UX + intelligence (main, uncommitted)

- **Bulk form inline:** toolbar → `DsiBulkActionInlineForm` → filters → table; Bulk map/provisional preset action; cancel/apply returns focus to toolbar.
- **Customer name normalisation:** `dsi_customer_name_normalization.py` at validate; evidence norms use cleaned tokens.
- **Duplicate hints:** text similarity (not embeddings) — see `docs/DSI_RESOLUTION_PERFORMANCE.md` flagged section.
- **Historical + distributor-scoped resolution:** `dsi_customer_intelligence.py` + plan build preload; previously resolved → `needs_review` / not auto-applied.

## DSI steward UX + performance (main, uncommitted)

- **Filter chips:** always visible in resolution workspace (`filtersSlot` no longer gated on `candidatesTotal` / default filters); table shows rows or empty-filter message (`keepTableWhenFilterEmpty`).
- **Bulk provisional customers:** Celery task `imports.dsi_bulk_provisional_customers` — single commit batch; `POST .../dsi-steward-bulk-provisional-customers/apply-async` + poll `GET .../dsi-steward-bulk-task/{task_id}`; sync `dsi-steward-bulk-apply` rejects `create_provisional_customer`; frontend polls then one steward invalidation.
- **Unresolved geo tokens:** `DSIGeoResolutionCache` preloads dim catalogs + batch alias lookups; see `docs/DSI_RESOLUTION_PERFORMANCE.md` for index recommendations (no migration run).
- **Revisit deep-link:** validated/failed DSI jobs open wizard step 6 (Validate) when using `?job=` — not step 4 upload.
- **Loading spinners:** plan/geo use `fetchStatus === 'fetching'` (not bare `isPending`) so disabled queries do not stick loading.
- **Plan/geo accordion:** hidden only when both `unresolvedGeoCount === 0` and `candidatesCount === 0`; geo sub-accordion hidden when no unresolved tokens; plan apply summary inline above table (`dsi-plan-apply-summary`).
- **Helper:** `dsiUnresolvedGeoCount.ts` — `countUnresolvedGeoTokens()`; `dsiStewardFiltersAreDefault` exported from barrel.
- **Tests:** `DsiImportJobResolutionSection.test.tsx` — 14/14 pass.

## DSI resolution loading UX (prior)
- Candidate table: skeleton rows while `distributor-si-candidates` loads; section mounts during fetch
- Slow calls: `DsiStewardLoadingCallout` for resolution plan (~30s) and unresolved geo tokens (~15–30s)
- Actions: `DsiPendingButton` + row-level pending spinner; optimistic candidate cache updates on steward/bulk/plan apply
- Removed full-page `Backdrop` overlay; in-table overlay shows contextual busy message
- Shared: `DsiPendingButton`, `DsiStewardLoadingCallout`, `ImportStewardCandidateWorkspaceSkeleton`, `dsiStewardCacheUpdates.ts`

## Files Changed This Session
- `apps/api/app/services/imports/dsi_shipment_corroboration.py` — `ShipmentCorroborationCache`
- `apps/api/app/services/imports/distributor_sales_inventory.py` — `DSIResolutionCache`,
  cached resolver functions, `corr_cache` threading, pre-computed `_col` lookups, progress
  logging, `on_progress` callback (phase + time-based row updates every 3 s),
  `total_rows` in `staged_metadata`
- `apps/api/app/worker/tasks.py` — `process_import_job_task` now `bind=True`; `_on_progress`
  closure calls `self.update_state`; passes `on_progress` to `process_import_job_sync`
- `apps/api/app/ingestion/pipeline.py` — `process_import_job_sync` accepts `on_progress`;
  threads it to the DSI handler
- `apps/api/app/api/v1/endpoints/imports.py` — `_enqueue_import_worker_task` /
  `_enqueue_import_pipeline_job` return `(bool, str|None)` with task_id; `post_dsi_validate`
  stores `celery_task_id` in `staged_metadata`; `get_job` returns `staged_metadata`;
  new `GET /jobs/{id}/dsi-progress` endpoint
- `apps/web/src/app/(app)/admin/imports/DsiValidateProgressPanel.tsx` — new component
- `apps/web/src/app/(app)/admin/imports/page.tsx` — `Job` type gets `staged_metadata`;
  import + `dsiProgress` query; step 6 uses `DsiValidateProgressPanel`
