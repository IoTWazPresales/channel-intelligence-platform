# Current state

**Last updated:** 2026-06-29 (PO↔lineup Unit 0 discovery approved; fresh chat for Unit 1)
**Verify git:** `git branch --show-current` · `git rev-parse --short HEAD`

---

## Branch and delivery

| Field | Value |
|-------|--------|
| **Branch** | `feat/unit-6-unified-lineup-import-centre` (now also carries Session C; cut from `feat/dsi-async-topology` + BACKLOG-051 docs) |
| **HEAD** | PO↔lineup Unit 0 discovery approved · Unit A/B lineup work on branch · next = **Unit 1 build** |
| **PR** | None open |
| **Alembic (code)** | `20260628_0057` (commercial_lineup_case_po) |
| **Alembic (DB)** | **`20260628_0057`** on local `cip` (`commercial_lineup_case_po` applied 2026-06-28) |

---

## Database and environment

| Field | Value |
|-------|--------|
| **Active DB** | Local Postgres `cip` @ `127.0.0.1:5432` (topology B) |
| **Bitemporal flags** | `CIP_SHIPMENT_BITEMPORAL_DUAL_WRITE` / `_READ` — **off** by default |
| **Celery dispatch** | `broker` (apps/api/.env) — DSI apply runs in worker, not API process |

---

## Dev topology

Local desktop (no Docker): `pnpm dev:api` :8001 · `pnpm dev:web` :3000 · `pnpm dev:worker` (Redis :6379) or `CIP_DEV_CELERY_DISPATCH=in_process_thread`.

| Preflight | Script | Skip env |
|-----------|--------|----------|
| API port / stale uvicorn | `scripts/dev-api.js` | `CIP_SKIP_API_PORT_PREFLIGHT=1` |
| Redis TCP | `scripts/dev-worker.js` | `CIP_SKIP_REDIS_PREFLIGHT=1` |
| Duplicate Celery consumers | `scripts/dev-worker.js` | `CIP_SKIP_WORKER_PREFLIGHT=1` |

**Ops note:** On Windows, the **node wrappers** for API and worker can exit after ~30 min or host sleep/resume (exit code -1). Restart `pnpm dev:api` / `pnpm dev:worker`. Worker preflight auto-kills orphan `app.worker.celery_app` processes on restart (proven: killed PIDs 23376+5032 after wrapper death). Uvicorn `--reload` does **not** reload the Celery worker — restart worker after API-side apply fixes.

---

## What is working

### Session B — Unified lineup import path (Units 1-5, 7-8) — backend done, e2e-proven on `cip`
Goal: one unified, multi-file lineup importer that supersedes the embedded Commercial-Planner
upload and the admin `historical_lineup` workbook, with full pricing chain + negotiation tracking.

- **Unit 1 — backwards pricing calc** (`lineup_pricing.py`): SRP→DAP chain (SRP/(1+VAT) → dealer →
  net(rebate) → disti_cost → /(1+import_tax) → /ROE = DAP cost-ccy; profit = DAP − controlled_cost).
- **Unit 2 — model + migration `20260628_0055`**: case `product_line` / `inferred_period_start` /
  `iteration_number`; line `customer_feedback` / `internal_notes` / `pricing_chain_json` /
  `calc_dap_cost_currency` / `calc_profit_total`.
- **Unit 3 — pricing alias map + resolution** (`lineup_pricing_resolution.py`): file evidence over
  trade-term defaults (customer/distributor terms + `commercial_sku_assumption`); stores calc_* +
  `pricing_chain_json` (inputs/sources/outputs/flags); `missing_pm_bottom` flag when no PM bottom.
- **Unit 4 — period/product-line inference** (`lineup_period_inference.py`): `26Q1`/month-column →
  `inferred_period_start`; product line from majority column. User-supplied values win.
- **Unit 5 — first-class `unified_lineup` importer** (`693efb9`): own template + `unified_lineup_system`
  source (seed migration `20260628_0056`, applied to `cip`). Lineup seed generalized over
  (template_slug, source_code); threaded through parser/dispatch/worker/Celery task so jobs are
  audited `template_slug='unified_lineup'`. `unified_lineup_import.dispatch_unified_lineup_import`
  fans out **one CommercialLineupCase + one always-async parse job per file** (per-file activity-feed
  progress, per-file failure isolation). Endpoint `POST /commercial-planner/lineup/unified-import`
  (multipart, N files + shared period/country/currency/plan). **Real e2e on cip:** job tagged
  unified_lineup, DAP 39.6622, period 2026-01-01, `missing_pm_bottom`, chain persisted.
- **Unit 7 — negotiation iterations + annotations** (`4d195e0`): `iteration_number` advances on
  `pending_review→validated` (customer bounce-back = new round; first send = round 1).
  `customer_feedback`/`internal_notes` editable through review loop (draft/validated/pending_review);
  pricing/qty edits stay draft-only. Case payload exposes iteration/product_line/inferred_period_start.
- **Unit 8 — per-customer XLSX export** (`4d195e0`): `GET /commercial-planner/lineup-cases/{id}/export?customer_id=`
  streams one customer's slice with the full persisted pricing chain (recomputes nothing; DAP =
  calculated cost-ccy, **not** PM bottom). `lineup_customer_export.py`.
- **Tests:** 113 unit/API pass; Units 5/7/8 also proven by real `cip` e2e (scripts cleaned up).

### Unit 6 (frontend) — DONE (wired + unit-tested; not yet browser-soaked)
Import-Centre multi-file uploader for the unified lineup importer + embedded upload made read-only.
- **New `UnifiedLineupImportDialog`** (`apps/web/src/app/(app)/admin/imports/UnifiedLineupImportDialog.tsx`):
  multi-file dropzone + plan/period/country/currency fields → `POST /api/v1/commercial-planner/lineup/unified-import`
  via `apiPostFormData` (repeated `files` field + form fields). On 202 it registers each returned
  `task_id` with the nav-bell activity feed (kind `commercial_planner_lineup_parse`) so progress is
  visible per file, and renders a per-file dispatch outcome table. Plan dropdown reads
  `GET /commercial-planner/plans`; selecting a plan prefills country/currency.
- **Import-Centre page** (`admin/imports/page.tsx`): added explicit primary card
  (`unified-lineup-import-card`) opening the dialog; `ImportTemplate` type gained `hidden?`; the
  `visibleTemplates` filter now excludes `hidden` templates so `unified_lineup` stays out of the
  generic wizard (it has its own surface).
- **`CurrentLineupSection`** read-only: new `allowUpload` prop (default **false**). When read-only the
  "Upload current lineup" button is replaced by an "Import lineups in Import Centre" link (→
  `/admin/imports`), the per-case "Upload file to this case" retry is hidden, and the
  `UploadLineupDialog`/`RetryParseDialog` are not mounted. Legacy upload retained behind `allowUpload`.
- **Tests:** new `UnifiedLineupImportDialog.test.tsx` (3) proves multipart `files` wiring +
  task registration + disabled-until-valid-file; existing `CurrentLineupSection.test.tsx` (7) and
  `commercial-planner/page.test.tsx` (83) still green. Lint clean for touched files.
- **NOT verified:** browser soak of the dialog against a running API (per-file progress in the bell,
  cases landing under the plan's Current lineups).

### Session C Unit 2d — Confirm-with-PO + `commercial_lineup_case_po` — code done, migration pending
- **Migration `20260628_0057`** (`commercial_lineup_case_po`): m2m join (one lineup→many POs, one
  PO→many lineups). `case_id` FK `commercial_lineup_case` CASCADE; `purchase_order_id` FK
  `purchase_order`; `UniqueConstraint(case_id, purchase_order_id)` for idempotency. **Applied to cip
  (2026-06-28).** Model `CommercialLineupCasePo` + `models/__init__`.
- **Service** `lineup_case_po_confirm.py`: `confirm_case_with_po` validates status (accepted/po_pending/
  po_issued), normalizes+dedups PO numbers, infers distributor from case lines, lookup/upsert
  `purchase_order` (status `raised`, source `lineup_declared`), inserts `case_po` links idempotently,
  sets `commercial_status='po_issued'`. `list_case_pos` / `list_case_pos_bulk` (no N+1).
- **API** `POST /commercial-planner/lineup-cases/{id}/confirm-with-po {po_numbers[], notes?}`
  (404/409/400). `_case_payload` now returns `linked_pos` + `po_count`.
- **UI** `CurrentLineupSection`: "Confirm lineup"/"Add PO" button → `ConfirmWithPoDialog` (multi-value
  PO input + chips + notes); status chip → po_issued; PO-count chip + iteration "Round N".
- **Tests:** `test_lineup_case_po_confirm.py` (mock) — 2 POs, idempotent re-confirm, append; + UI test.

### Session C Unit 3 — Reconciliation + gap worklist + PO Management — code done (derived; no migration)
- **Reconciliation** `lineup_po_reconciliation.py` `reconcile_case` (derived on read): per (case×product)
  aggregate `shipment_evidence_line` where `purchase_order_id IN {case POs}` & `product_id` matches a
  lineup line. PRIMARY **units** flag — matched/short/over/unshipped/unplanned/amended/po_no_match.
  SECONDARY **value** bridged via `commercial_sku_assumption.fx_plan_currency_per_cost_currency`
  (display only; `fx_unavailable` when no bridge — never errors). UoM eaches assertion → warning.
  API `GET /commercial-planner/lineup/po-reconciliation?case_id`.
- **Gap worklist** `lineup_po_gap.py`: shipment (PO,product) not covered by any confirmed case →
  grouped by quarter (from `ship_confirm_date`/`schedule_ship_date`). Dismiss-with-reason reuses
  `purchase_order.dismiss_reason_code`. APIs `GET .../lineup/po-gap-worklist`, `POST .../dismiss`,
  `POST .../restore`.
- **PO Management** `po_management.py` + endpoints `/po-management/coverage` & `/backlog`: observed POs
  (from shipment evidence) grouped by quarter→product line; coverage meter (observed vs linked,
  `first_run`); linked groups roll up reconciliation summary; unlinked groups get an upload prompt.
- **UI:** new `/admin/po-management` page + `PoManagementView` (coverage meter, backlog groups with
  recon chips / upload prompt, gap worklist table with dismiss/restore + "Show dismissed"); nav entry
  under Data Imports. Lineup case card shows inline `CaseReconciliationInline` when POs linked.
  `/shipping` grid: **Customer PO column** (click → filter) + `?purchase_order_id=&po_label=` deep-link
  banner; backend `/shipping/lines` + commercial-summary accept `purchase_order_id` filter. Upload
  prompts deep-link `/admin/imports?unified=1&period=` → `UnifiedLineupImportDialog` `initialPeriodLabel`.
  Shipment-evidence page cross-links to PO Management.
- **Tests:** `test_lineup_po_reconciliation.py` (all 7 flags + FX-missing + UoM), `test_lineup_po_gap.py`,
  `PoManagementView.test.tsx` (first-run/linked/dismiss), `buildShippingLinesUrl.test.ts` (+PO filter).
  22 backend + 3 PO-mgmt UI + 3 shipping-url + 3 dialog green; lint clean for touched files.
- **Real-DB e2e:** migration `0057` applied to `cip`; browser soak still open.

### Plan-optional lineup browse + pct evidence guard (2026-06-28)
- **Problem:** Uploaded lineup cases (e.g. historical periods) were invisible in Commercial Planner
  when no plan was selected — UI gated `GET /lineup-cases` on `activePlanId`.
- **Fix:** `CurrentLineupSection` always fetches cases; optional **Show all (ignore plan)** toggle when
  a plan is selected; cases grouped by period → product line with Linked/Unlinked chips; workbench
  line grid + column metadata open for unlinked cases. `PATCH /lineup-cases/{id}/plan` attach/detach.
- **Parser guard:** `sanitize_pct_evidence` in `lineup_pricing_resolution.py` — currency amounts
  mapped to pct columns (case #6 corrupt file) dropped with `pct_evidence_out_of_range` diagnostic
  instead of `Numeric(8,4)` overflow. Margin **amount** columns deferred → **BACKLOG-052**.
- **Tests:** +3 API (list-all, attach, detach) · +3 UI (grouped unlinked list, plan filter, unlinked
  workbench) · pct sanitize unit tests. 100 API + 11 CurrentLineupSection vitest green.

### Direct confirm-with-PO + suggested POs (2026-06-28)
- **Confirm with PO** on case card at **any status except cancelled** — no forward ladder required;
  reuses `confirm_case_with_po` → `po_issued` + `commercial_lineup_case_po` links (idempotent).
- **GET `/lineup-cases/{id}/suggested-pos`** — observed POs ranked by product overlap (distributor +
  `shipment_evidence_line`); modal shows selectable suggestions + manual entry.
- Workbench hides "Ready to sync" alert when case is `po_issued` / fulfillment terminal.
- Tests: 11 PO API + 13 CurrentLineupSection vitest green.

### PO↔lineup auto-alignment — Unit 0 discovery APPROVED (2026-06-29); Unit 1 next
**Spec:** ONE SPEC, five units (0–5), build/commit/push **one unit at a time** on current branch.
**cip is read-only** for agents except migrations Warren approves; never run alembic/validate/apply/backfill
against cip — Warren runs those. Data-mapping gate applies.

**Unit 0 findings (cip evidence, 49,981 `shipment_evidence_line` rows):**
- No `resolved_customer_id` / `resolved_distributor_id` today — shipment uses `customer_id` /
  `distributor_id` on line + raw `customer_dealer_token` / `bill_to_raw`. Customer stamped via steward
  (`_mark_customer_lines_resolved`); distributor at validate via `_resolve_distributor_strict` +
  `distributor_source_token_alias`. DSI staging has `resolved_*`; shipment does not.
- Branch suffixes: **no automatic root collapse** in resolver. MUSTEK-ZA-BB + MUSTEK-ZA-C both →
  `distributor_id=21` (TMP-DIST Mustek) via **separate approved aliases** (`mustek-za-bb`, `mustek-za-c`).
- **CRAD:** only in `raw_source_row['CRAD']` (49,793/49,981 ≈99.6%); **not** a typed column. Typed
  dates: `schedule_ship_date` 99.6%, `ship_confirm_date` 96%, etc. Current coalesce is pod-first (no CRAD).
- **PO duplication root cause:** `purchase_order` unique on `(po_number_norm, distributor_id)` but
  materialize uses `line.distributor_id` — when NULL, Postgres allows unlimited dup rows. cip: 11,088 PO
  rows / 2,265 distinct norms / **8,822 rows with NULL distributor** covering **1,634 norms** (~Warren's
  ~1,645). When `distributor_id` set: 2,266 rows = 2,266 unique pairs (zero dup pairs).

**Warren approvals (all four + Unit 2 addition):**
1. Add `resolved_customer_id` + `resolved_distributor_id`; **keep in sync** with existing `customer_id` /
   `distributor_id`.
2. Root = **alias-target collapse**; **no** `parent_id` on `dim_distributor` in this build.
3. **`crad_date`** in Unit 1 migration (parse from `"CRAD"` header).
4. Unit 2 primary scope = **NULL-dist preview-first merge** (not branch-variant merge — nearly absent on cip).
5. **Unit 2 materialize rule (approved):** when `resolved_distributor_id` is null, **do NOT mint** a
   NULL-keyed `purchase_order` — defer materialization until steward resolves distributor (prevents
   duplication regenerating after cleanup).

**Unit 1 scope (NEXT — fresh chat):** migration adds `resolved_customer_id`, `resolved_distributor_id`,
`crad_date` to `shipment_evidence_line` + `fact_inbound_shipment`; populate at validate/steward/apply
using **same** alias resolution paths (no second resolver); preserve raw tokens; backfill script
(dry-run default, `--confirm`); tests. **STOP/report migration revision before Warren runs upgrade.**

**Units 2–5 (deferred):** PO dedup + deferred materialize · auto-link engine (CRAD-primary) · review
surface · period-derived importer.

**Limiter:** 23 TMP-DIST / 4,960 TMP-CUST on cip — auto-link match rate capped; unmatched → exception queue.

### Unit A — case-level distributor assignment (tokenless lines) (2026-06-28) — code done, browser soak open
- **Gap closed:** entity resolution is token-keyed, so lineup lines with no `distributor_token_raw`
  (e.g. an Amazon file that simply has no distributor column) could never be assigned a distributor —
  they showed **Unassigned** forever. Unit A adds a **case-level** assign path that does not need a token.
- **Suggest** `lineup_case_suggested_pos.py::suggest_distributors_for_case`: ranks distributors from
  **shipment-evidence product corroboration** (which distributors actually shipped the case's resolved
  products) → `{converged, converged_distributor_id, distinct_count, suggested_distributors[],
  already_assigned_distributor_ids[]}`. `converged` = exactly one distinct distributor across evidence.
- **Assign** `lineup_case_distributor_assign.py::assign_case_distributor`: sets `distributor_id` on the
  case's lines (`only_unassigned=True` by default). Either links an **existing** `dim_distributor` OR
  creates one — but **only** via steward-confirmed path (`new_code` + `new_name` + `confirm_create`);
  rejects duplicate code / unknown id / non-resolvable case status. **No silent master creation** —
  governance boundary preserved. Tags a diagnostic on touched lines.
- **API:** `GET /commercial-planner/lineup-cases/{id}/suggested-distributors` ·
  `POST /commercial-planner/lineup-cases/{id}/assign-distributor`
  (`AssignDistributorBody`: `distributor_id` | `new_code`+`new_name`+`confirm_create`; `only_unassigned`).
- **UI** `CurrentLineupSection`: "Assign distributor" button on the case card (guarded by
  `RESOLUTION_UI_STATUSES`) → `AssignDistributorDialog`: shows evidence suggestions (converged auto-pick
  vs ambiguous pick-list), `EntitySearchAutocomplete` to find an existing dim, or a create-new form
  requiring confirm. Invalidates cases/lines/suggested-distributors/suggested-pos on success.
- **Tests:** `test_lineup_case_distributor_suggest_assign.py` (10: suggest not-found/no-products/
  converged/ambiguous; assign existing/create-new/reject dup-code/unknown-id/bad-status/not-found) +
  3 UI tests (converged assign, ambiguous pick, create-new confirm). Read-only suggest e2e run against
  real `cip`. **Not soaked:** live click-through assign in browser.

### Unit B — lineup workbench migrated to EnterpriseDataGrid (AG Grid) (2026-06-28) — code done, browser soak open
- **Replaces** the bespoke MUI `<Table>` workbench with the repo-standard `EnterpriseDataGrid`
  (AG Grid wrapper used by Plans/admin grids) → native **movable / resizable / sortable / filterable**
  columns, matching the rest of the app. (The read-only `CaseLinesDialog` and the suggested-PO table
  stay plain MUI tables — out of scope.)
- **Column model:** `wbColumnDefs` maps `visibleColsFiltered` → `ColDef[]`. `wbCellValue` extracts a
  primitive (string|number|null) for sort/filter; rich display reuses existing `wbCellContent` as a
  `cellRenderer`. Editable numeric cells (`units`→`quantity_units`, `msrp`→`msrp_local`,
  `promo`→`promo_price_evidence_local`) only when `activeCase.commercial_status === 'draft_imported'`
  (`type: 'numericColumn'`, `singleClickEdit`).
- **Edit persistence:** `onCellValueChanged` ignores null/invalid/no-op commits (mirrors prior inline
  editor) then `patchLineMutation.mutate`. **Column-order persistence:** `onDragStopped` writes the new
  order back into `visibleCols` (localStorage v4 per case).
- **Typing note:** `EnterpriseDataGrid` is a `forwardRef` fixing `T=unknown`, so defs are typed
  `ColDef[]` / `GridOptions` (not `<CommercialLineupLine>`) with `as CommercialLineupLine` casts in
  getters/renderers — same pattern as the Plans grid.
- **Tests:** `CurrentLineupSection.test.tsx` 16/16 green (grid mocked the repo-standard way, asserting
  columnheaders + cell content via cellRenderer/valueFormatter/valueGetter). Lint clean; tsc clean for
  the file. **Not proven in jsdom:** real AG Grid inline-edit → `onCellValueChanged` → PATCH, and
  drag-reorder persistence — needs a quick browser smoke.

### Lineup workbench + catalogue product_line (2026-06-28)
- **product_line inference:** catalogue-majority PRIMARY (`dim_product.product_line`, row-weighted);
  filename fallback ONLY when &lt;25% rows resolved; sheet category/BU column removed as signal.
  Steward-set `product_line` never overwritten. **Warren:** re-parse cases 3/4/5 to fix mislabels
  (Gaming NR→Gaming, Consumer/NB/NV per catalogue).
- **Workbench grid:** default columns = identity (part #, model, series, processor) + qty/SRP +
  margin % (display ×100) + **calculated** pricing chain (`pricing_chain_json` / calc_*); no dead
  raw upload price columns; `sku_raw` out of defaults (still in picker). localStorage v4 per case.
  Plan-optional workbench always requests `include_product_specs` + `include_line_uploaded`.
- **API:** lines expose `pricing_chain_json`, `calc_dap_cost_currency`, `calc_profit_total`;
  `calc_fields` in workbench-column-metadata. Tests: 16 inference + 12 CurrentLineupSection vitest.

### DSI apply — proven fresh E2E on job #199 (`b2b81ea`, 2026-06-27)
- `import_job 199` → `completed` / `loaded` / `apply`.
- Facts (`source_import_job_id=199`): `fact_sales_sellout`=2 · `fact_inventory_distributor`=2.
- Full derive chain in worker: SOH reconciliation · velocity (3,369 rows) · forecasting.
- UI: DSI Apply step shows `ImportJobLoadedSuccessCallout` when loaded (parity with shipment).

### staged_metadata deadlock — FIXED (BACKLOG-050 resolved, `b2b81ea`)
- **Root cause:** dual-writer on `import_job.staged_metadata` — caller-session `set_task_slot_on_job` (uncommitted row lock) + `enqueue_*` own committed session → self-deadlock on one worker thread.
- **Fix:** `enqueue_*` is sole writer; derivation dispatch wrapped in try/except (loaded job never reverts to `failed`); idempotent re-apply sets `completed` when already `loaded`. Test asserts `session.flush` not called on dispatch.

### dev-worker duplicate-consumer preflight (`b2b81ea`)
- Kills stray `app.worker.celery_app` before spawn; fresh start logs `mingle: all alone`.

### Job #96 — large-volume apply PROVEN LIVE (`loaded`, channel operations)
- Full **178k-row** RAW workbook applied; facts visible in channel operations (Warren confirmed 2026-06-28).
- `fact_sales_sellout`=35,582 · `fact_inventory_distributor`=47,411 · `fact_returns`=3,175 (unique `source_key` grain — multiple Excel rows collapse per key).
- Apply path: async worker + poll; `staged_metadata` deadlock fix (`b2b81ea`) holds at volume.

### DSI apply pipeline (prior commits on branch)
- **No re-validate on apply** (`e4c30bc`): skip Step 1 when job already `validated` with staging.
- **Finalize → async** (`page.tsx`): Finalize button POSTs async `dsi-apply` (worker + poll), not sync in-request.
- **Gate-key revisit** (`468c239`): mapping-draft sync at `activeStep < 5`.
- **Customer alias resolution-key:** dealer-group token alignment; job #96 remediated → 0 blocking rows.

### Shipment import wizard (DSI-aligned — wired + unit-tested)
- 7-step wizard; `ImportJobLoadedSuccessCallout` on loaded; steward workspace parity.

---

## In progress / not proven live
- **PO↔lineup Unit 1** — resolved columns + `crad_date` migration + backfill script (approved; fresh chat).
- **Pre-existing lint** — 7 `rules-of-hooks` errors in `dsi-mapping-steward-panel.tsx` block clean `pnpm lint` (not introduced by DSI apply work).
- **Billiard quirk** — solo worker spawns one child under system Python (single logical consumer; interpreter mismatch latent).
- Warren **actively working through** ACZA shipment upload (BOM tab deferred per BACKLOG-046).
- Shipment wizard browser soak, Rectron mapping, Import Centre URL reset — **not re-verified** this session.

---

## Next (recommended)

1. **PO↔lineup Unit 1 (fresh chat)** — migration `resolved_customer_id`, `resolved_distributor_id`,
   `crad_date` on evidence + fact lines; populate via existing alias paths; backfill script; tests;
   commit + push. See handover prompt in latest chat.
2. **Warren smoke-test (lineup Unit A + B)** — assign distributor + workbench grid (optional parallel).
3. **Open PR** for `feat/unit-6-unified-lineup-import-centre` when lineup + PO units are ready.
4. Fix `dsi-mapping-steward-panel.tsx` rules-of-hooks lint (unblocks `pnpm lint`).
5. Finish ACZA upload (trim to **Shipped + Unship** until BACKLOG-046).

---

## Blockers requiring Warren

- Business sign-off: should **BOM Not Ready** enter shipment facts? (BACKLOG-046)
- Main promotion — explicit instruction only

---

## Key references

| Topic | Doc |
|-------|-----|
| Memory index | `docs/memory/MEMORY_PALACE.md` |
| Import contract | `docs/IMPORT_FLOW_CAPABILITY_CONTRACT.md` |
| Dev topology | `docs/DEV_TOPOLOGY.md` |
| Backlog 045–050 | `docs/BACKLOG.md` |
