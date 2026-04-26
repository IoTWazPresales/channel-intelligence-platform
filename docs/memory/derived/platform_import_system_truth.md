# Platform Import System Truth

## Template/source model
- Import behavior is template-driven (`import_template`) and source-bound (`source_definition`).
- Template flags control visibility, admin-only constraints, file types, and destructive-confirm requirements.
- Source can carry parser hints, expected template overrides, and optional target product catalog linkage.

## Generic import lifecycle
- `POST /api/v1/imports/jobs` stores file and creates `import_job`.
- For non-Product-Master templates, sync processing can run in-process (`process_import_job_sync`).
- Pipeline stages include uploaded/raw/schema/mapped/validated/loaded/failed semantics.

## Product Master constrained lifecycle
- Dedicated endpoints under `/api/v1/imports/product-master/jobs/*`.
- Stages:
  - upload/infer headers
  - mapping decisions save
  - validate (staged metadata + row results)
  - commit (background, async status model)
- Mapping allows canonical targets plus explicit dispositions (`ignore`, `stage_raw`, `attribute_candidate`).

## Persistence behavior
- Validation pass writes staging snapshot (`staged_metadata`) and messages in `import_row_result`.
- Commit writes canonical product updates and optional catalog/EAV materialization.
- Commit-level state and diagnostics persist in `pm_commit_meta` and `error_summary`.

## Notable import truths/quirks
- Product Master bypasses legacy generic one-shot processing once constrained workflow metadata exists.
- Descriptor-row stripping, scalar normalization, and mapper-memory behavior are explicitly tested in API suite.
- Generic async import task exists in worker but is not the dominant API-triggered runtime path today.

## Operationally meaningful risk notes
- Import outcomes are observable via rows + progress metadata, but cross-job lineage reporting is still mostly per-job/manual.
- Product Master has stronger state machine controls than many other import templates, which are still lighter-weight.

---

## Checkpoint: `historical_lineup` (as of 2026-04-26)

Compact record of governed **historical lineup** import work shipped on `main` in this period. Broader repo init may include earlier foundation (template, handler, models, migrations); the commits below are the **discrete follow-on** slices that landed after that baseline.

### Commits completed (newest first)

| Commit | Summary |
|--------|---------|
| `0d6f50d` | **Apply post-success (web):** On successful `historical_lineup` **apply**, clear `historicalValidatedJobId` and `lastGenericFile` so “Apply validated file” hides immediately; dedicated success `Alert` (“Apply job #N completed…”) with `data-testid="apply-success-alert"`; generic “Job created / Refresh preview” alert suppressed when `upload.data.import_mode === 'apply'`. **Also:** generic upload mutation only requires `source_id` when `selectedTemplate.requires_provider` is true (fixes impossible guard for no-provider templates). Vitest: `apps/web/src/app/(app)/admin/imports/page.test.tsx` (8 tests). |
| `8dd2972` | **Job revisit (web):** `?job=<id>` loads job via `GET /imports/jobs/{id}`; wizard sync (revisit mode, step 4 for non-PM); revisit banner; jobs grid ID links to `/admin/imports?job=`; Start over / template change clears revisit + URL. |
| `5f3cc06` | **Phase 1A (API):** `historical_lineup.py` — cross-field `model_name` vs `sales_model_name` ambiguity guard; ILIKE fallback extended to `part_number` / model fields; test hardening + positive paths / apply persistence tests. |
| `0588973` | **Phase 1 (API):** `historical_lineup.py` — product resolution (SKU, `part_number`, `model_name`, `sales_model_name`, unique ILIKE); `invalid_quantity`; severity/diagnostic behavior; stability/apply-focused tests in `test_historical_lineup_*`. |

*(Local dev port/proxy alignment and `historical_lineup_workbook` dispatch fixes were done in-session; if not visible as separate commits on your branch, treat them as environment/config truth in `platform_runtime_truth.md` rather than duplicating here.)*

### Current verified behavior (automated / design intent)

- **Template:** `historical_lineup` with validate-then-apply workflow; pipeline handler `historical_lineup_workbook` (sync job path).
- **Backend:** Workbook parse → sheet/header detection → row diagnostics → normalized `HistoricalLineupImportHeader` / `HistoricalLineupImportLine` on apply; row results on `import_row_result` with first token as `code`, full list in `message`.
- **Product match:** Exact fields + guarded ILIKE; `ambiguous_product_match` / `unknown_product` / `product_matched_by_ilike` etc. as designed in Phase 1/1A.
- **Web:** Validate upload sets validation job + enables Apply when file still in session; apply clears gate + shows apply-only success alert; revisit via `?job=` without mutating old jobs.

### Manual testing result (this checkpoint)

- **Not re-executed** while writing this doc-only checkpoint.
- **Recommended checklist** (from prior gated specs): validate real workbook → Apply appears → Apply → success alert + button gone → diagnostics still visible → hard refresh `?job=<apply_job_id>` still loads rows.

### Remaining deferred items

- Diagnostics UX: `code` vs `message` / severity mismatch (e.g. first diagnostic vs max severity); optional `diagnostic_codes JSONB` — **not** implemented.
- Backend: duplicate-apply guard for `historical_lineup` — **deferred**.
- Mapping review UI, column mapping drafts, `match_strategy` JSONB, generic mapping framework — **deferred**.
- Commercial Planner candidate ranking / planner UI tied to lineup — **out of scope** for import Phase 1–2.

### Recommended next phase

- **Small, gated “Phase 2B”** (pick one): either (a) minimal diagnostics display clarification without JSONB, or (b) backend idempotent / duplicate-apply policy for `historical_lineup`, or (c) first slice of mapping review — each as its own short prompt; avoid bundling.

### Cost-control note

- Prefer **small scoped prompts** (single concern, explicit allowed files, explicit non-goals). Avoid **broad implementation** passes that mix UI + API + schema + refactors; they inflate review surface and regression risk.

---

## Checkpoint: `historical_lineup` Phase 3A–3C (2026-04-26)

Compact record of Phase 3A, 3B, and 3C implementation covering column mapping review, alias fixes, duplicate-column guards, runtime hardening, and the Import Quality Review panel.

### Commits (oldest first within this phase)

| Commit | Summary |
|--------|---------|
| `cbf63a2` | **Phase 3A (API + web):** `parse_historical_workbook` accepts `mapping_override` from `job.mapping_decisions`; `source_columns` added to `inferred_schema.selected_sheet_details`; customer ILIKE fallback (unique → resolve, multiple → `ambiguous_customer_match`, none → `unknown_customer`); mapping override merges over auto-detect; `mapping_decisions` overwritten with final effective mapping for audit. Web: Column mapping review panel (collapsible); field/detected/override table; confidence chip; re-validate with corrections flow; `mapping_override` sent in `FormData`. |
| `3d21972` | **Phase 3B (API + web):** Removed `base_unit` from `sku_raw` aliases; added `buyer`/`sold to`/`reseller` to `customer_token`; added `sales part number` to `part_number_raw`; `_ERROR_LEVEL_CODES` frozenset drives `ImportRowResult.code` selection (error-level diagnostic wins over first-diagnostic order); `HL_DIAGNOSTIC_ERROR_CODES` set in frontend; confidence chip on mapping panel; `diagnosticSummary` useMemo; diagnostic summary chips above row table; `base_unit_raw` added to `HL_MAPPING_DISPLAY_FIELDS`. |
| `500e4cd` | **Duplicate-column fix (API + tests):** `_build_header_map` now tracks `claimed_sources`; first canonical in `_CANONICAL_ALIASES` insertion order claims a source column; prevents "Base Unit" appearing under both `sku_raw` and `base_unit_raw`. Backend regression test `test_base_unit_not_dual_mapped_with_realistic_columns`; frontend regression test `regression: Product identity (SKU) shows not-detected when field_mapping has no sku_raw`. |
| `0458d70` | **Post-override dedupe + full parse-path regression (API):** Deduplication guard added after `mapping_override` application in `parse_historical_workbook` — override-claimed source columns are removed from auto-detected mapping to prevent stale override reintroducing duplicates. Full ASUS-style workbook parse regression test `test_parse_historical_workbook_asus_style_base_unit_not_in_sku_raw` verifies the entire pipeline path, not just `_build_header_map`. |
| `f47bcea` | **Phase 3C — Import Quality Review (API + web):** Backend: `_invalid_numeric_fields` list collected per row; single `invalid_numeric` diagnostic appended after loop; field names embedded in `ImportRowResult.raw_payload` as `_invalid_numeric_fields`. Frontend: `HL_APPLY_BLOCKING_CODES` (excludes `unknown_customer`); `qualityReview` useMemo (blocking count, ok count, commercial warning count, distinct `unknownCustomerTokens` map, `invalidNumericExamples`, `isApplyReady`); Import Quality Review panel between mapping review and apply button (apply-ready/blocking badge, unresolved customer chips with row counts, commercial warning count, invalid numeric field examples); apply button disabled when `blockingCount > 0`; inline `apply-confirm-alert` shown when `unknownCustomerCount > 0` before mutating; `hlShowApplyConfirm` state cleared on success and Start over. Tests: `test_invalid_numeric_fields_in_raw_payload`; 3 Phase 3C frontend tests. |

### Full commit sequence for `historical_lineup` work on `main`

```
f47bcea  Phase 3C import quality review
0458d70  Post-override dedupe + ASUS parse-path regression
500e4cd  Prevent same source column mapping to multiple canonicals
3d21972  Phase 3B alias/code/UI clarity
cbf63a2  Phase 3A mapping override + customer ILIKE fallback
8fadc26  Checkpoint doc (Phase 1–2 recap)
0d6f50d  Apply button gate + success alert
8dd2972  Phase 2 job revisit UI (?job= URL param)
5f3cc06  Phase 1A cross-field ambiguity + ILIKE extension
0588973  Phase 1 backend hardening - product resolution + severity split
```

### Current verified behavior (as of f47bcea)

- **ASUS workbook:** NB sheet selected, header row 4 detected, ~16 mapped fields.
- **Base Unit:** Maps exclusively to `base_unit_raw` ("Base unit (descriptor)"), never to `sku_raw` ("Product identity (SKU)"). Invariant enforced in `_build_header_map` (claimed_sources) and after override application.
- **Product resolution:** Working via Part Number / model_name paths. No `unknown_product` in latest manual run with ASUS workbook.
- **Import Quality Review panel:** Shows apply-ready badge, unresolved customer chips (by distinct token with row counts), commercial warning count, and invalid numeric field examples from `raw_payload._invalid_numeric_fields`.
- **Apply readiness:** `unknown_customer` rows do NOT hard-block apply — they trigger a soft inline confirmation. `unknown_product`, `missing_key_fields`, `invalid_quantity` are hard blockers (Apply button disabled).
- **Apply success:** Button disappears immediately; `apply-success-alert` shows job ID; diagnostics remain visible.
- **Previous job revisit:** `/admin/imports?job=<id>` loads any job, non-PM jobs restore to step 4 with diagnostics visible.
- **Latest manual run result (ASUS NB workbook):**
  - `unknown_product`: 0
  - `historical_lineup_row_ok`: 28
  - `unknown_customer`: 121
  - `partial_margin_stack`: 17
  - `invalid_numeric`: 2
  - `historical_lineup_sheet_summary`: 1
  - `historical_lineup_processed`: 1

### Operational lessons learned (process quality)

- **Rogue processes:** Cursor-triggered service restarts created multiple rogue Python/Node processes that held ports and served stale code. **User should control API/web terminals manually** in separate PowerShell windows.
- **WatchFiles trap:** Do NOT trust `WatchFiles Reloading…` log lines as proof of successful restart. Only trust `Application startup complete` on the API and `Ready — started server on http://localhost:3000` on web.
- **Stale job data:** When an API restart is in-flight and a new validate job runs, the database may store a mapping computed by the old code. Always trigger a fresh validate job AFTER confirming the new API is fully started. Do not interpret the UI of an old job as a regression.
- **Port contract:** Web 3000, API 8001. `CIP_SKIP_API_PORT_PREFLIGHT=1` env var bypasses the port preflight check when needed.
- **Test sentinel values:** Avoid pandas NaN sentinels (`N/A`, `NA`, `NaN`) as test workbook cell values — pandas reads them as null. Use opaque strings like `TBD` or `BADVALUE` to trigger string-present-but-unparseable conditions.

### Deferred items (as of f47bcea)

- **Customer token resolution:** Operator mapping of distinct unknown customer tokens → existing `DimCustomer` records. `EntityMappingQueue` write workflow — not yet implemented.
- **Loaded historical lineup view:** UI to inspect `HistoricalLineupImportHeader` / `HistoricalLineupImportLine` records written by apply. No backend endpoint for this yet.
- **Post-apply navigation:** After apply success, offer link / auto-navigate to `/admin/imports?job=<apply_job_id>` so the operator can bookmark and revisit the apply job.
- **Jobs list performance:** No pagination yet; may become unwieldy as job count grows.
- **ProductAlias lookup:** `EntityMappingQueue` and `ProductAlias` model exist but are not written to by `historical_lineup` import.
- **Distributor/channel resolution:** `unknown_distributor` and `unknown_channel` diagnostics exist but no mapping UI.
- **`diagnostic_codes` JSONB:** Not implemented; `ImportRowResult.message` holds the full diagnostic list as `;`-joined string. Defer unless server-side diagnostic filtering becomes necessary.
- **Duplicate-apply guard:** No backend guard prevents applying the same workbook twice. Defer; each apply creates a new immutable job.
- **Commercial planner / candidate ranking:** Out of scope until historical lineup data is reliably inspectable. `commercial_plan`, `commercial_plan_line`, and related models exist but are not wired to lineup data yet.
- **`match_strategy` JSONB / generic mapping framework:** Not implemented; mapping is alias-driven via `_CANONICAL_ALIASES`.
- **Multi-sheet mapping:** Only the best-scored sheet is selected per workbook. Multiple sheet support deferred.

### Recommended next phase

See PART C of the 2026-04-26 checkpoint prompt for the full next-phase plan. Short summary:

1. **Customer token resolution + EntityMappingQueue:** Let operator map distinct unknown tokens → existing customers without auto-creation.
2. **Loaded lineup records view:** Endpoint + UI to inspect `HistoricalLineupImportLine` records for an apply job (product, customer, qty, price/margin).
3. **UX polish:** Post-apply navigation, keep Quality Review visible on revisit, faster job list.
4. **Commercial planner entry point:** Smallest useful query proving lineup data supports planning (lineup by customer/product/month or promo warning summary).
5. **Data quality:** `invalid_numeric` and `partial_margin_stack` narrative improvements.
